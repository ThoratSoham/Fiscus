import uuid
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from core.auth import SupabaseUser
from streaks.models import Profile
from .models import Holding, Instrument, Order, VirtualPortfolio

# Deterministic quotes — the market-data feed is always mocked in tests.
PRICES = {
    "RELIANCE.NS": 1310.0,
    "INFY.NS": 1169.2,
}


class InvestApiTests(TestCase):
    def setUp(self):
        self.user_a = str(uuid.uuid4())
        self.user_b = str(uuid.uuid4())
        # Instruments are seeded by migration 0003 — reuse those rows.
        self.reliance = Instrument.objects.get(yahoo_symbol="RELIANCE.NS")
        self.infy = Instrument.objects.get(yahoo_symbol="INFY.NS")

        self.client = APIClient()
        self.client.force_authenticate(user=SupabaseUser(id=self.user_a))

        # Never touch the network: serve fixed quotes for the feeds, and
        # short-circuit the eager refresh that the list/portfolio views do.
        self.feed_patch = mock.patch(
            "invest.prices.fetch_quote",
            side_effect=lambda symbol: (PRICES[symbol], 1786701670),
        )
        self.feed_patch.start()
        self.refresh_patch = mock.patch("invest.views.refresh_all", return_value={})
        self.refresh_patch.start()
        self.addCleanup(self.feed_patch.stop)
        self.addCleanup(self.refresh_patch.stop)

    def _buy(self, instrument, quantity, side="buy"):
        return self.client.post(
            "/api/invest/orders/",
            {"instrument_id": instrument.id, "side": side, "quantity": quantity},
            format="json",
        )

    def test_buy_creates_holding_and_debits_cash(self):
        res = self._buy(self.reliance, 10)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        self.assertEqual(portfolio.current_balance, Decimal("86900.00"))  # 100k − 10×1310

        holding = Holding.objects.get(portfolio=portfolio, instrument=self.reliance)
        self.assertEqual(holding.quantity, Decimal("10"))
        self.assertEqual(holding.avg_price, Decimal("1310.0000"))

        order = Order.objects.get(user_id=self.user_a)
        self.assertEqual(order.side, "buy")
        self.assertEqual(order.status, "filled")
        self.assertEqual(order.price, Decimal("1310.0000"))

    def test_insufficient_cash_rejected(self):
        res = self._buy(self.reliance, 1000)  # ₹1,310,000 > ₹100,000
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient cash", res.data["detail"])
        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        self.assertEqual(portfolio.current_balance, Decimal("100000.00"))
        self.assertEqual(Holding.objects.count(), 0)

    def test_avg_price_math_across_buys(self):
        self._buy(self.reliance, 10)
        res = self._buy(self.reliance, 5)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

        holding = Holding.objects.get(
            portfolio=VirtualPortfolio.objects.get(user_id=self.user_a),
            instrument=self.reliance,
        )
        self.assertEqual(holding.quantity, Decimal("15"))
        # (10×1310 + 5×1310) / 15 — same price, so avg stays 1310
        self.assertEqual(holding.avg_price, Decimal("1310.0000"))
        # cash: 100k − 15×1310
        self.assertEqual(
            VirtualPortfolio.objects.get(user_id=self.user_a).current_balance,
            Decimal("80350.00"),
        )

    def test_sell_credits_cash_and_reduces_holding(self):
        self._buy(self.reliance, 10)
        res = self._buy(self.reliance, 4, side="sell")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

        holding = Holding.objects.get(
            portfolio=VirtualPortfolio.objects.get(user_id=self.user_a),
            instrument=self.reliance,
        )
        self.assertEqual(holding.quantity, Decimal("6"))
        # cash: 100k − 10×1310 + 4×1310
        self.assertEqual(
            VirtualPortfolio.objects.get(user_id=self.user_a).current_balance,
            Decimal("92140.00"),
        )

    def test_oversell_rejected(self):
        self._buy(self.reliance, 2)
        res = self._buy(self.reliance, 5, side="sell")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("don't hold enough", res.data["detail"])

    def test_sell_without_position_rejected(self):
        res = self._buy(self.reliance, 1, side="sell")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_portfolio_aggregation(self):
        self._buy(self.reliance, 10)
        self._buy(self.infy, 2)

        res = self.client.get("/api/invest/portfolio/")
        self.assertEqual(res.status_code, 200)
        data = res.data
        self.assertEqual(Decimal(data["starting_balance"]), Decimal("100000.00"))
        # cash = 100k − (10×1310 + 2×1169.2)
        self.assertEqual(Decimal(data["cash"]), Decimal("84561.60"))
        # invested = 13100 + 2338.4
        self.assertEqual(Decimal(data["invested"]), Decimal("15438.40"))
        # value at the (mocked) snapshot price = same as invested
        self.assertEqual(Decimal(data["portfolio_value"]), Decimal("100000.00"))
        self.assertEqual(Decimal(data["return_amount"]), Decimal("0.00"))
        self.assertEqual(len(data["holdings"]), 2)
        symbols = {h["symbol"] for h in data["holdings"]}
        self.assertEqual(symbols, {"RELIANCE", "INFY"})

    def test_ownership_isolation(self):
        self._buy(self.reliance, 5)
        other = APIClient()
        other.force_authenticate(user=SupabaseUser(id=self.user_b))
        res = other.get("/api/invest/portfolio/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["holdings"], [])
        self.assertEqual(res.data["cash"], "100000.00")

    def test_reset_restores_starting_balance(self):
        self._buy(self.reliance, 5)
        res = self.client.post("/api/invest/reset/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(res.data["cash"]), Decimal("100000.00"))
        self.assertEqual(res.data["holdings"], [])
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Holding.objects.count(), 0)

    def test_first_trade_badge_unlocks(self):
        res = self._buy(self.reliance, 1)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["unlocked_badges"], ["First Trade"])
        profile = Profile.objects.get(user_id=self.user_a)
        self.assertTrue(profile.badge_first_trade)

    def test_instruments_are_public(self):
        res = APIClient().get("/api/invest/instruments/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("market_open", res.data)
        symbols = {i["symbol"] for i in res.data["instruments"]}
        self.assertIn("NIFTY 50", symbols)
        self.assertIn("RELIANCE", symbols)

    def test_unauthorized_requests_are_401(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/invest/portfolio/").status_code, 401)
        self.assertEqual(
            anon.post(
                "/api/invest/orders/",
                {"instrument_id": self.reliance.id, "side": "buy", "quantity": 1},
                format="json",
            ).status_code,
            401,
        )

    def test_invalid_instrument_404(self):
        res = self.client.post(
            "/api/invest/orders/",
            {"instrument_id": 999999, "side": "buy", "quantity": 1},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(DEBUG=False, CRON_SECRET="sekret-test")
class CronPricesTests(TestCase):
    def setUp(self):
        self.refresh_patch = mock.patch("invest.views.refresh_all", return_value={})
        self.refresh_patch.start()
        self.addCleanup(self.refresh_patch.stop)

    def test_cron_requires_secret(self):
        res = self.client.get("/api/cron/prices/")
        self.assertEqual(res.status_code, 401)

    def test_cron_with_secret_succeeds(self):
        res = self.client.get(
            "/api/cron/prices/", HTTP_AUTHORIZATION="Bearer sekret-test"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn("at", res.data)

    @override_settings(CRON_SECRET="")
    def test_cron_refused_without_configured_secret(self):
        res = self.client.get("/api/cron/prices/")
        self.assertEqual(res.status_code, 500)
