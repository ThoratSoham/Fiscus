import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.auth import SupabaseUser
from streaks.models import Profile
from . import engine, trading
from .models import Holding, Instrument, Order, VirtualPortfolio

SEED_A = 424242
SEED_B = 777001


class EngineTests(TestCase):
    def setUp(self):
        self.orbit = Instrument.objects.get(yahoo_symbol="SIM-04")  # Orbit Motors
        self.t0 = timezone.now()

    def test_price_at_epoch_equals_base(self):
        at = engine.EPOCH
        self.assertEqual(engine.price_at(self.orbit, SEED_A, at=at), self.orbit.base_price)

    def test_price_is_deterministic_for_same_seed(self):
        p1 = engine.price_at(self.orbit, SEED_A, at=self.t0)
        p2 = engine.price_at(self.orbit, SEED_A, at=self.t0)
        self.assertEqual(p1, p2)

    def test_prices_differ_between_students(self):
        p_a = engine.price_at(self.orbit, SEED_A, at=self.t0)
        p_b = engine.price_at(self.orbit, SEED_B, at=self.t0)
        self.assertNotEqual(p_a, p_b)  # private per-student market

    def test_price_moves_over_time(self):
        later = self.t0 + timedelta(hours=2)  # several 15-min ticks later
        self.assertNotEqual(
            engine.price_at(self.orbit, SEED_A, at=self.t0),
            engine.price_at(self.orbit, SEED_A, at=later),
        )

    def test_event_schedule_is_deterministic_and_private(self):
        s1 = engine.event_schedule(SEED_A)
        s2 = engine.event_schedule(SEED_A)
        s3 = engine.event_schedule(SEED_B)
        self.assertEqual(s1, s2)
        self.assertNotEqual([e["start"] for e in s1], [e["start"] for e in s3])

    def test_events_shock_affected_instruments_only(self):
        """Every student has some event hitting some instruments — verify the
        shock applies to a subset and leaves others untouched at the peak."""
        seed = SEED_A
        events = engine.event_schedule(seed)
        # pick the strongest crash/rally
        event = max(events, key=lambda e: abs(e["magnitude"]))
        peak_tick = event["start"] + engine.EVENT_WINDOW_TICKS // 2

        instruments = list(Instrument.objects.filter(is_active=True))
        shocked = []
        untouched = []
        for inst in instruments:
            shock = engine._shock_log(seed, inst.symbol, peak_tick, events)
            (shocked if shock != 0 else untouched).append(inst.symbol)
        self.assertTrue(shocked, "expected some instruments to be shocked")
        self.assertTrue(untouched, "expected some instruments to be untouched")

    def test_engine_never_writes_to_db(self):
        before = Order.objects.count()
        engine.price_at(self.orbit, SEED_A, at=self.t0)
        self.assertEqual(Order.objects.count(), before)


class InvestApiTests(TestCase):
    def setUp(self):
        self.user_a = str(uuid.uuid4())
        self.user_b = str(uuid.uuid4())
        self.orbit = Instrument.objects.get(yahoo_symbol="SIM-04")  # Orbit Motors
        self.pixel = Instrument.objects.get(yahoo_symbol="SIM-11")  # Pixelworks Tech

        # Fixed seeds so tests are fully deterministic — no random market.
        VirtualPortfolio.objects.create(
            user_id=self.user_a, seed=SEED_A,
            starting_balance=Decimal("100000.00"), current_balance=Decimal("100000.00"),
        )
        VirtualPortfolio.objects.create(
            user_id=self.user_b, seed=SEED_B,
            starting_balance=Decimal("100000.00"), current_balance=Decimal("100000.00"),
        )

        self.client = APIClient()
        self.client.force_authenticate(user=SupabaseUser(id=self.user_a))

    def _buy(self, instrument, quantity, side="buy"):
        return self.client.post(
            "/api/invest/orders/",
            {"instrument_id": instrument.id, "side": side, "quantity": quantity},
            format="json",
        )

    def test_buy_creates_holding_and_debits_cash(self):
        res = self._buy(self.orbit, 10)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        fill = Decimal(res.data["order"]["price"])
        expected_cost = (fill * 10).quantize(Decimal("0.01"))

        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        self.assertEqual(portfolio.current_balance, Decimal("100000.00") - expected_cost)

        holding = Holding.objects.get(portfolio=portfolio, instrument=self.orbit)
        self.assertEqual(holding.quantity, Decimal("10"))
        self.assertEqual(holding.avg_price, fill)

        order = Order.objects.get(user_id=self.user_a)
        self.assertEqual(order.side, "buy")
        self.assertEqual(order.status, "filled")

    def test_insufficient_cash_rejected(self):
        res = self._buy(self.orbit, 1000000)  # way over ₹100k
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Insufficient cash", res.data["detail"])
        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        self.assertEqual(portfolio.current_balance, Decimal("100000.00"))
        self.assertEqual(Holding.objects.count(), 0)

    def test_avg_price_math_across_buys(self):
        self._buy(self.orbit, 10)
        res = self._buy(self.orbit, 5)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        holding = Holding.objects.get(
            portfolio=VirtualPortfolio.objects.get(user_id=self.user_a),
            instrument=self.orbit,
        )
        self.assertEqual(holding.quantity, Decimal("15"))

    def test_sell_credits_cash_and_reduces_holding(self):
        self._buy(self.orbit, 10)
        res = self._buy(self.orbit, 4, side="sell")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        holding = Holding.objects.get(
            portfolio=VirtualPortfolio.objects.get(user_id=self.user_a),
            instrument=self.orbit,
        )
        self.assertEqual(holding.quantity, Decimal("6"))
        # cash = 100k − 10×fill + 4×fill — recompute from the recorded fills
        fills = list(Order.objects.filter(user_id=self.user_a).order_by("id"))
        expected_cash = Decimal("100000.00")
        for order in fills:
            delta = order.price * order.quantity
            expected_cash += -delta if order.side == "buy" else delta
        self.assertEqual(
            VirtualPortfolio.objects.get(user_id=self.user_a).current_balance,
            expected_cash.quantize(Decimal("0.01")),
        )

    def test_oversell_rejected(self):
        self._buy(self.orbit, 2)
        res = self._buy(self.orbit, 5, side="sell")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("don't hold enough", res.data["detail"])

    def test_sell_without_position_rejected(self):
        res = self._buy(self.orbit, 1, side="sell")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_portfolio_aggregation_is_internally_consistent(self):
        self._buy(self.orbit, 10)
        self._buy(self.pixel, 2)
        res = self.client.get("/api/invest/portfolio/")
        self.assertEqual(res.status_code, 200)
        data = res.data
        self.assertEqual(Decimal(data["starting_balance"]), Decimal("100000.00"))

        invested = sum(Decimal(h["invested"]) for h in data["holdings"])
        current = sum(Decimal(h["current_value"]) for h in data["holdings"])
        self.assertEqual(Decimal(data["invested"]), invested)
        self.assertEqual(
            Decimal(data["portfolio_value"]),
            (Decimal(data["cash"]) + current).quantize(Decimal("0.01")),
        )
        self.assertEqual(
            Decimal(data["return_amount"]),
            (Decimal(data["portfolio_value"]) - Decimal("100000.00")).quantize(Decimal("0.01")),
        )
        self.assertEqual(len(data["holdings"]), 2)

    def test_ownership_isolation(self):
        self._buy(self.orbit, 5)
        other = APIClient()
        other.force_authenticate(user=SupabaseUser(id=self.user_b))
        res = other.get("/api/invest/portfolio/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["holdings"], [])
        self.assertEqual(res.data["cash"], "100000.00")

    def test_reset_restores_balance_and_rerolls_seed(self):
        self._buy(self.orbit, 5)
        before_seed = VirtualPortfolio.objects.get(user_id=self.user_a).seed
        res = self.client.post("/api/invest/reset/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(res.data["cash"]), Decimal("100000.00"))
        self.assertEqual(res.data["holdings"], [])
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Holding.objects.count(), 0)
        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        self.assertNotEqual(portfolio.seed, before_seed)  # fresh private market
        self.assertTrue(res.data["seed_changed"])

    def test_reset_with_custom_starting_balance(self):
        self._buy(self.orbit, 5)
        res = self.client.post(
            "/api/invest/reset/", {"starting_balance": "50000"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["starting_balance"]), Decimal("50000.00"))
        self.assertEqual(Decimal(res.data["cash"]), Decimal("50000.00"))
        self.assertEqual(
            VirtualPortfolio.objects.get(user_id=self.user_a).starting_balance,
            Decimal("50000.00"),
        )

    def test_reset_rejects_invalid_starting_balance(self):
        for bad in ("-5", "0", "50", "abc", "99999999999"):
            res = self.client.post(
                "/api/invest/reset/", {"starting_balance": bad}, format="json"
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.assertEqual(
            VirtualPortfolio.objects.get(user_id=self.user_a).starting_balance,
            Decimal("100000.00"),  # untouched
        )

    def test_first_trade_badge_unlocks(self):
        res = self._buy(self.orbit, 1)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["unlocked_badges"], ["First Trade"])
        profile = Profile.objects.get(user_id=self.user_a)
        self.assertTrue(profile.badge_first_trade)

    def test_instruments_require_auth(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/invest/instruments/").status_code, 401)
        res = self.client.get("/api/invest/instruments/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["market_open"])
        symbols = {i["symbol"] for i in res.data["instruments"]}
        self.assertIn("NIFTY-SIM", symbols)
        self.assertIn("ORBIT", symbols)
        # prices are per-student
        anon_price = {i["symbol"]: i["price"] for i in res.data["instruments"]}

        other = APIClient()
        other.force_authenticate(user=SupabaseUser(id=self.user_b))
        other_res = other.get("/api/invest/instruments/").data
        other_price = {i["symbol"]: i["price"] for i in other_res["instruments"]}
        self.assertNotEqual(anon_price["ORBIT"], other_price["ORBIT"])

    def test_unauthorized_requests_are_401(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/invest/portfolio/").status_code, 401)
        self.assertEqual(
            anon.post(
                "/api/invest/orders/",
                {"instrument_id": self.orbit.id, "side": "buy", "quantity": 1},
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


class LimitStopOrderTests(TestCase):
    """Limit + stop-loss orders: lazy path-crossing fills (spec 6.4)."""

    def setUp(self):
        self.user_a = str(uuid.uuid4())
        self.orbit = Instrument.objects.get(yahoo_symbol="SIM-04")
        self.pixel = Instrument.objects.get(yahoo_symbol="SIM-11")
        VirtualPortfolio.objects.create(
            user_id=self.user_a, seed=SEED_A,
            starting_balance=Decimal("100000.00"), current_balance=Decimal("100000.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=SupabaseUser(id=self.user_a))

    def _place(self, instrument, side, order_type, quantity, trigger=None):
        payload = {
            "instrument_id": instrument.id, "side": side,
            "order_type": order_type, "quantity": quantity,
        }
        if trigger is not None:
            payload["trigger_price"] = str(trigger)
        return self.client.post("/api/invest/orders/", payload, format="json")

    def _market_buy(self, instrument, quantity=10):
        return self._place(instrument, "buy", "market", quantity)

    def _current_price(self, instrument):
        return engine.price_at(instrument, SEED_A)

    def _future_crossing(self, instrument, trigger, mode, max_ticks=8000):
        """A future time at which the deterministic path first crosses the
        trigger, plus the crossing price. Deterministic — the engine is a
        pure function of time."""
        from_tick = trading.tick_of(timezone.now())
        prices = engine.price_series(instrument, SEED_A, from_tick, from_tick + max_ticks)
        idx = trading.first_crossing(prices, trigger, mode)
        if idx is None:
            self.fail(f"path never crossed trigger {trigger} ({mode}) — adjust the test")
        future = engine.EPOCH + timedelta(seconds=(from_tick + idx) * engine.TICK_SECONDS)
        return future, prices[idx]

    # -- immediate fills (already crossed at placement) --

    def test_buy_limit_above_current_fills_immediately(self):
        trigger = self._current_price(self.orbit) * 2
        res = self._place(self.orbit, "buy", "limit", 10, trigger=trigger)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["order"]["status"], "filled")
        fill = Decimal(res.data["order"]["price"])
        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        self.assertEqual(
            portfolio.current_balance,
            (Decimal("100000.00") - (fill * 10).quantize(Decimal("0.01"))),
        )

    def test_sell_limit_below_current_fills_immediately(self):
        self._market_buy(self.orbit)
        trigger = self._current_price(self.orbit) * Decimal("0.5")
        res = self._place(self.orbit, "sell", "limit", 10, trigger=trigger)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["order"]["status"], "filled")

    def test_stop_loss_above_current_fills_immediately(self):
        self._market_buy(self.orbit)
        trigger = self._current_price(self.orbit) * 2  # price already below stop
        res = self._place(self.orbit, "sell", "stop_loss", 10, trigger=trigger)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["order"]["status"], "filled")

    # -- pending + cancel --

    def test_limit_below_current_stays_pending_then_cancels(self):
        res = self._place(self.orbit, "buy", "limit", 10, trigger=Decimal("0.0001"))
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["order"]["status"], "pending")

        order_id = res.data["order"]["id"]
        listed = self.client.get("/api/invest/orders/list/").data
        pending = [o for o in listed if o["id"] == order_id][0]
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(Decimal(pending["trigger_price"]), Decimal("0.0001"))

        cancelled = self.client.post(f"/api/invest/orders/{order_id}/cancel/").data
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(
            Order.objects.get(id=order_id).status, Order.Status.CANCELLED
        )

    def test_filled_order_cannot_be_cancelled(self):
        res = self._place(self.orbit, "buy", "limit", 10, trigger=self._current_price(self.orbit) * 2)
        self.assertEqual(res.data["order"]["status"], "filled")
        cancel = self.client.post(f"/api/invest/orders/{res.data['order']['id']}/cancel/")
        self.assertEqual(cancel.status_code, 400)

    def test_stop_loss_must_be_a_sell(self):
        res = self._place(self.orbit, "buy", "stop_loss", 10, trigger=100)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # -- lazy path-crossing fills --

    def test_buy_limit_fills_lazily_when_path_crosses(self):
        trigger = (self._current_price(self.orbit) * Decimal("0.995")).quantize(Decimal("0.01"))
        res = self._place(self.orbit, "buy", "limit", 10, trigger=trigger)
        self.assertEqual(res.data["order"]["status"], "pending")

        future, crossing = self._future_crossing(self.orbit, trigger, "below")
        changed = trading.check_pending_orders(self.user_a, at=future)
        self.assertEqual(len(changed), 1)
        order = changed[0]
        self.assertEqual(order.status, Order.Status.FILLED)
        self.assertEqual(order.price, crossing)

        portfolio = VirtualPortfolio.objects.get(user_id=self.user_a)
        holding = Holding.objects.get(portfolio=portfolio, instrument=self.orbit)
        self.assertEqual(holding.quantity, Decimal("10"))
        self.assertEqual(holding.avg_price, crossing)

    def test_sell_limit_fills_lazily_when_price_rises(self):
        self._market_buy(self.orbit)
        trigger = (self._current_price(self.orbit) * Decimal("1.005")).quantize(Decimal("0.01"))
        res = self._place(self.orbit, "sell", "limit", 10, trigger=trigger)
        self.assertEqual(res.data["order"]["status"], "pending")

        future, _ = self._future_crossing(self.orbit, trigger, "above")
        changed = trading.check_pending_orders(self.user_a, at=future)
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].status, Order.Status.FILLED)
        # holding closed out
        self.assertFalse(
            Holding.objects.filter(
                portfolio=VirtualPortfolio.objects.get(user_id=self.user_a),
                instrument=self.orbit,
            ).exists()
        )

    def test_stop_loss_triggers_on_dip(self):
        self._market_buy(self.orbit)
        trigger = (self._current_price(self.orbit) * Decimal("0.995")).quantize(Decimal("0.01"))
        res = self._place(self.orbit, "sell", "stop_loss", 10, trigger=trigger)
        self.assertEqual(res.data["order"]["status"], "pending")

        future, crossing = self._future_crossing(self.orbit, trigger, "below")
        changed = trading.check_pending_orders(self.user_a, at=future)
        self.assertEqual(len(changed), 1)
        order = changed[0]
        self.assertEqual(order.status, Order.Status.FILLED)
        self.assertEqual(order.price, crossing)
        # sold out at the stop
        self.assertFalse(
            Holding.objects.filter(
                portfolio=VirtualPortfolio.objects.get(user_id=self.user_a),
                instrument=self.orbit,
            ).exists()
        )

    def test_insufficient_cash_cancels_pending_buy(self):
        trigger = self._current_price(self.orbit) * 2  # crossed instantly
        res = self._place(self.orbit, "buy", "limit", 1000000, trigger=trigger)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["order"]["status"], "cancelled")
        self.assertIn("insufficient cash", res.data["order"]["note"])

    # -- engine consistency --

    def test_price_series_matches_price_at(self):
        from_tick = trading.tick_of(timezone.now())
        series = engine.price_series(self.orbit, SEED_A, from_tick, from_tick + 5)
        for i, price in enumerate(series):
            at = engine.EPOCH + timedelta(seconds=(from_tick + i) * engine.TICK_SECONDS)
            self.assertEqual(price, engine.price_at(self.orbit, SEED_A, at=at))
