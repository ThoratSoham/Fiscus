from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.shortcuts import render
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.auth import SupabaseJWTAuthentication
from streaks.models import Profile
from .engine import latest_price
from .models import Holding, Instrument, Order, VirtualPortfolio
from .serializers import OrderSerializer

AUTH = [SupabaseJWTAuthentication]
PERM = [permissions.IsAuthenticated]

PENNY = Decimal("0.01")


def _q2(value):
    """Quantize a Decimal to cash precision (2dp, half-up)."""
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def _q4(value):
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _config():
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
    }


def invest_page(request):
    """HTML shell — all data comes from the API via the browser's JWT."""
    return render(request, "invest/invest.html", {"config": _config()})


# ---------------------------------------------------------------------------
# Instruments (auth required — prices are per-student, seeded by portfolio)
# ---------------------------------------------------------------------------

@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def instruments(request):
    """Active simulated instruments with their current engine price.

    The market is private per student: every price is computed from the
    user's portfolio seed at the current time. 24/7 — always open.
    """
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    now = timezone.now()
    rows = []
    for instrument in Instrument.objects.filter(is_active=True):
        price, as_of, source, stale = latest_price(instrument, portfolio.seed, at=now)
        rows.append(
            {
                "id": instrument.id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "kind": instrument.kind,
                "price": str(price),
                "as_of": as_of.isoformat(),
                "source": source,
                "stale": stale,
            }
        )
    return Response({"market_open": True, "instruments": rows, "as_of_utc": now.isoformat()})


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

def _portfolio_payload(portfolio, at=None):
    """Aggregate cash, invested value, P&L and open holdings at engine prices."""
    at = at or timezone.now()
    invested = Decimal("0")
    current_value = Decimal("0")
    holdings = []
    for holding in portfolio.holdings.select_related("instrument"):
        price, _as_of, _source, _stale = latest_price(holding.instrument, portfolio.seed, at=at)
        cost = _q2(holding.avg_price * holding.quantity)
        value = _q2(price * holding.quantity)
        pnl = _q2(value - cost)
        invested += cost
        current_value += value
        holdings.append(
            {
                "instrument_id": holding.instrument_id,
                "symbol": holding.instrument.symbol,
                "name": holding.instrument.name,
                "quantity": str(holding.quantity),
                "avg_price": str(holding.avg_price),
                "last_price": str(price),
                "invested": str(cost),
                "current_value": str(value),
                "pnl": str(pnl),
                "pnl_pct": str(_q2(pnl / cost * 100) if cost else Decimal("0")),
            }
        )

    total = _q2(portfolio.current_balance + current_value)
    starting = portfolio.starting_balance
    return {
        "starting_balance": str(starting),
        "cash": str(portfolio.current_balance),
        "invested": str(_q2(invested)),
        "portfolio_value": str(total),
        "return_amount": str(_q2(total - starting)),
        "return_pct": str(_q2((total - starting) / starting * 100) if starting else Decimal("0")),
        "holdings": holdings,
        "recent_orders": OrderSerializer(
            portfolio.orders.select_related("instrument")[:10], many=True
        ).data,
    }


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def portfolio(request):
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    return Response(_portfolio_payload(portfolio))


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------

@api_view(["POST"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def place_order(request):
    """Market order: fill instantly at the current engine price.

    Buy:  debit cash, average into the holding. Sell: credit cash, reduce
    the holding (rejects overselling). The First Trade badge unlocks on the
    user's first buy.
    """
    instrument = Instrument.objects.filter(
        id=request.data.get("instrument_id"), is_active=True
    ).first()
    if instrument is None:
        return Response({"detail": "Unknown instrument."}, status=status.HTTP_404_NOT_FOUND)

    side = request.data.get("side")
    if side not in ("buy", "sell"):
        return Response({"detail": "side must be 'buy' or 'sell'."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        quantity = Decimal(str(request.data.get("quantity", "")))
    except Exception:
        return Response({"detail": "quantity must be a number."}, status=status.HTTP_400_BAD_REQUEST)
    if quantity <= 0:
        return Response({"detail": "Quantity must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    now = timezone.now()
    fill_price = _q4(latest_price(instrument, portfolio.seed, at=now)[0])

    with transaction.atomic():
        portfolio = VirtualPortfolio.objects.select_for_update().get(pk=portfolio.pk)
        cost = _q2(fill_price * quantity)

        if side == "buy":
            if cost > portfolio.current_balance:
                return Response(
                    {"detail": f"Insufficient cash. You have ₹{portfolio.current_balance}, the order costs ₹{cost}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            portfolio.current_balance -= cost
            holding, created = Holding.objects.select_for_update().get_or_create(
                portfolio=portfolio,
                instrument=instrument,
                defaults={"quantity": quantity, "avg_price": fill_price},
            )
            if not created:
                new_quantity = holding.quantity + quantity
                holding.avg_price = _q4(
                    (holding.avg_price * holding.quantity + fill_price * quantity) / new_quantity
                )
                holding.quantity = new_quantity
                holding.save(update_fields=["avg_price", "quantity", "updated_at"])
        else:  # sell
            holding = Holding.objects.select_for_update().filter(
                portfolio=portfolio, instrument=instrument
            ).first()
            if holding is None or holding.quantity < quantity:
                return Response(
                    {"detail": "You don't hold enough of this instrument to sell."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            portfolio.current_balance += cost
            holding.quantity -= quantity
            if holding.quantity == 0:
                holding.delete()
            else:
                holding.save(update_fields=["quantity", "updated_at"])

        portfolio.save(update_fields=["current_balance", "updated_at"])
        order = Order.objects.create(
            user_id=request.user.id,
            portfolio=portfolio,
            instrument=instrument,
            side=side,
            quantity=quantity,
            price=fill_price,
            note=request.data.get("note", "")[:120],
            filled_at=now,
        )

    profile = Profile.get_or_create_for(request.user.id)
    profile.record_activity()
    newly_unlocked = profile.evaluate_badges()

    return Response(
        {
            "order": OrderSerializer(order).data,
            "cash": str(portfolio.current_balance),
            "unlocked_badges": newly_unlocked,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def reset_portfolio(request):
    """Reset: wipe positions + orders, restore the starting balance, and
    re-roll the market seed — a genuinely fresh private market."""
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    old_seed = portfolio.seed
    portfolio.reset()
    return Response(
        {**_portfolio_payload(portfolio), "seed_changed": old_seed != portfolio.seed}
    )
