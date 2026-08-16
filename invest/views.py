from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.auth import SupabaseJWTAuthentication
from streaks.models import Profile
from .engine import latest_price, ohlc_series
from .models import Holding, Instrument, Order, VirtualPortfolio
from .serializers import OrderSerializer
from .trading import (
    SHORT_MARGIN_RATE,
    apply_fill,
    available_cash,
    check_pending_orders,
    margin_reserve,
    portfolio_history,
)

AUTH = [SupabaseJWTAuthentication]
PERM = [permissions.IsAuthenticated]


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

    Runs the lazy pending-order check first so any limit/stop that crossed
    fills before the student reads prices. 24/7 — always open.
    """
    check_pending_orders(request.user.id)
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    now = timezone.now()
    rows = []
    for instrument in Instrument.objects.filter(is_active=True):
        price, as_of, source, _stale = latest_price(instrument, portfolio.seed, at=now)
        rows.append(
            {
                "id": instrument.id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "kind": instrument.kind,
                "price": str(price),
                "as_of": as_of.isoformat(),
                "source": source,
            }
        )
    return Response({"market_open": True, "instruments": rows, "as_of_utc": now.isoformat()})


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

def _portfolio_payload(portfolio, at=None):
    """Aggregate cash, invested value, P&L and open holdings at engine prices.

    Shorts (spec 6.5): negative quantity, invested/value shown as gross
    absolutes, P&L flipped ((avg − price) × |qty|, green when price falls),
    and a margin reserve locked out of available cash.
    """
    at = at or timezone.now()
    invested = Decimal("0")
    current_value = Decimal("0")
    signed_market = Decimal("0")  # Σ qty × price — shorts subtract (spec 6.5)
    holdings = []
    for holding in portfolio.holdings.select_related("instrument"):
        price, _as_of, _source, _stale = latest_price(holding.instrument, portfolio.seed, at=at)
        is_short = holding.quantity < 0
        qty_abs = abs(holding.quantity)
        cost = (holding.avg_price * qty_abs).quantize(Decimal("0.01"))
        value = (price * qty_abs).quantize(Decimal("0.01"))
        # short P&L = (avg − price) × qty; long P&L = (price − avg) × qty
        pnl = (value - cost) if not is_short else (cost - value)
        invested += cost
        current_value += value
        signed_market += price * holding.quantity
        holdings.append(
            {
                "instrument_id": holding.instrument_id,
                "symbol": holding.instrument.symbol,
                "name": holding.instrument.name,
                "quantity": str(holding.quantity),
                "short": is_short,
                "avg_price": str(holding.avg_price),
                "last_price": str(price),
                "invested": str(cost),
                "current_value": str(value),
                "pnl": str(pnl.quantize(Decimal("0.01"))),
                "pnl_pct": str((pnl / cost * 100).quantize(Decimal("0.01")) if cost else Decimal("0")),
                "spark": [str(c["close"]) for c in ohlc_series(holding.instrument, portfolio.seed, days=15, end=at)],
            }
        )

    reserve = margin_reserve(portfolio, at)
    total = (portfolio.current_balance + signed_market).quantize(Decimal("0.01"))
    starting = portfolio.starting_balance
    return {
        "starting_balance": str(starting),
        "cash": str(portfolio.current_balance),
        "available_cash": str(available_cash(portfolio, at)),
        "margin_reserve": str(reserve),
        "margin_rate": str(SHORT_MARGIN_RATE),
        "invested": str(invested.quantize(Decimal("0.01"))),
        "portfolio_value": str(total),
        "return_amount": str((total - starting).quantize(Decimal("0.01"))),
        "return_pct": str(((total - starting) / starting * 100).quantize(Decimal("0.01")) if starting else Decimal("0")),
        "holdings": holdings,
        "recent_orders": OrderSerializer(
            portfolio.orders.select_related("instrument")[:10], many=True
        ).data,
        "history": portfolio_history(portfolio, days=30, at=at),
    }


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def portfolio(request):
    check_pending_orders(request.user.id)
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    return Response(_portfolio_payload(portfolio))


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def chart_data(request, pk):
    """Everything the instrument chart needs (spec 6.8): daily candles from
    the engine's OHLC buckets, the student's position + pending triggers on
    this instrument (for entry/trigger lines), and trade history (markers)."""
    instrument = get_object_or_404(Instrument, pk=pk, is_active=True)
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    now = timezone.now()

    holding = Holding.objects.filter(
        portfolio=portfolio, instrument=instrument
    ).first()

    pending = list(
        Order.objects.filter(
            user_id=request.user.id,
            instrument=instrument,
            status=Order.Status.PENDING,
        ).order_by("created_at")
    )
    fills = list(
        Order.objects.filter(
            user_id=request.user.id,
            instrument=instrument,
            status=Order.Status.FILLED,
        ).order_by("-filled_at")[:50]
    )

    return Response(
        {
            "symbol": instrument.symbol,
            "name": instrument.name,
            "current": str(latest_price(instrument, portfolio.seed, at=now)[0]),
            "candles": ohlc_series(instrument, portfolio.seed, days=30, end=now),
            "holding": {
                "quantity": str(holding.quantity),
                "avg_price": str(holding.avg_price),
            }
            if holding
            else None,
            "pending": [
                {
                    "id": o.id,
                    "side": o.side,
                    "order_type": o.order_type,
                    "trigger_price": str(o.trigger_price),
                }
                for o in pending
            ],
            "fills": [
                {
                    "side": o.side,
                    "price": str(o.price),
                    "quantity": str(o.quantity),
                    "filled_at": o.filled_at.isoformat() if o.filled_at else None,
                }
                for o in fills
            ],
        }
    )


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def order_list(request):
    """All of the user's orders (filled + pending), newest first."""
    check_pending_orders(request.user.id)
    orders = Order.objects.filter(user_id=request.user.id).select_related("instrument")[:50]
    return Response(OrderSerializer(orders, many=True).data)


@api_view(["POST"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def cancel_order(request, pk):
    """Cancel a pending order. Filled orders cannot be cancelled."""
    order = get_object_or_404(Order, pk=pk, user_id=request.user.id)
    if order.status != Order.Status.PENDING:
        return Response({"detail": "Only pending orders can be cancelled."}, status=400)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])
    return Response(OrderSerializer(order).data)


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------

@api_view(["POST"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def place_order(request):
    """Place an order.

    market    → fills instantly at the engine price
    limit     → pending; fills when price crosses the trigger (buy below /
                sell above)
    stop_loss → pending sell; fills when price falls to the trigger

    Pending orders are checked lazily — the path from placement to now is
    walked on the next portfolio/instruments/order-list read.
    """
    instrument = Instrument.objects.filter(
        id=request.data.get("instrument_id"), is_active=True
    ).first()
    if instrument is None:
        return Response({"detail": "Unknown instrument."}, status=status.HTTP_404_NOT_FOUND)

    side = request.data.get("side")
    if side not in ("buy", "sell"):
        return Response({"detail": "side must be 'buy' or 'sell'."}, status=status.HTTP_400_BAD_REQUEST)

    order_type = request.data.get("order_type", "market")
    if order_type not in ("market", "limit", "stop_loss"):
        return Response({"detail": "order_type must be market, limit or stop_loss."}, status=status.HTTP_400_BAD_REQUEST)
    if order_type != "market" and side == "buy" and order_type == "stop_loss":
        return Response({"detail": "Stop-loss orders must be sells."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        quantity = Decimal(str(request.data.get("quantity", "")))
    except Exception:
        return Response({"detail": "quantity must be a number."}, status=status.HTTP_400_BAD_REQUEST)
    if quantity <= 0:
        return Response({"detail": "Quantity must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

    trigger_price = None
    if order_type != "market":
        try:
            trigger_price = Decimal(str(request.data.get("trigger_price", "")))
        except Exception:
            return Response({"detail": "trigger_price must be a number for limit/stop orders."}, status=status.HTTP_400_BAD_REQUEST)
        if trigger_price <= 0:
            return Response({"detail": "trigger_price must be greater than zero."}, status=status.HTTP_400_BAD_REQUEST)

    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)
    now = timezone.now()

    if order_type == "market":
        fill_price = latest_price(instrument, portfolio.seed, at=now)[0]
        with transaction.atomic():
            portfolio = VirtualPortfolio.objects.select_for_update().get(pk=portfolio.pk)
            filled = apply_fill(
                portfolio, instrument, side, quantity, fill_price,
                request.user.id, now, note=request.data.get("note", "")[:120],
            )
            if filled is None:
                reason = "Insufficient available cash" if side == "buy" else "Short too large: the short's value must fit in your available cash (50% margin reserve)."
                return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)
            order = filled
    else:
        order = Order.objects.create(
            user_id=request.user.id,
            portfolio=portfolio,
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type=order_type,
            status=Order.Status.PENDING,
            trigger_price=trigger_price,
            note=request.data.get("note", "")[:120],
        )
        # Lazy check: if the current price already crossed the trigger (or
        # the path from placement did), the order fills right here.
        check_pending_orders(request.user.id, at=now)
        order.refresh_from_db()

    profile = Profile.get_or_create_for(request.user.id)
    profile.record_activity()
    newly_unlocked = profile.evaluate_badges()

    response = {
        "order": OrderSerializer(order).data,
        "cash": str(portfolio.current_balance),
        "unlocked_badges": newly_unlocked,
    }
    if order.status == Order.Status.CANCELLED:
        response["detail"] = order.note or "Order cancelled."
        return Response(response, status=status.HTTP_400_BAD_REQUEST)
    return Response(response, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def reset_portfolio(request):
    """Reset: wipe positions + orders, restore (or set) the starting balance,
    and re-roll the market seed — a genuinely fresh private market.

    Accepts an optional `starting_balance` (spec 6.7: chosen at creation or
    on reset). Default stays ₹1,00,000 when omitted.
    """
    portfolio = VirtualPortfolio.get_or_create_for(request.user.id)

    starting = request.data.get("starting_balance")
    if starting is not None:
        try:
            starting = Decimal(str(starting))
        except Exception:
            return Response(
                {"detail": "starting_balance must be a number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if starting < Decimal("100") or starting > Decimal("10000000"):
            return Response(
                {"detail": "Starting balance must be between ₹100 and ₹10,000,000."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        portfolio.starting_balance = starting
        portfolio.save(update_fields=["starting_balance", "updated_at"])

    old_seed = portfolio.seed
    portfolio.reset()
    return Response(
        {**_portfolio_payload(portfolio), "seed_changed": old_seed != portfolio.seed}
    )
