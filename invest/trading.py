"""Order execution for the simulated market (Phase 6 spec 6.4).

Market orders fill instantly at the engine price. Limit and stop-loss
orders stay **pending**; because every price is a computable function of
(seed, instrument, time), they fill **lazily** — when the student next
looks at their portfolio (or places another order), we walk the
deterministic price path between placement and now and fill at the first
tick that crossed the trigger. No polling, no background jobs.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .engine import EPOCH, TICK_SECONDS, price_at, price_series
from .models import Holding, Order, VirtualPortfolio

PENNY = Decimal("0.01")


def _q2(value):
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def _q4(value):
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def tick_of(dt):
    return max(int((dt - EPOCH).total_seconds() // TICK_SECONDS), 0)


def crossing_mode(order):
    """Which side of the trigger fills the order.

    buy limit   → price falls to/under the trigger ("below")
    sell limit  → price rises to/over the trigger ("above")
    stop-loss   → price falls to/under the stop   ("below")
    """
    if order.order_type == Order.Type.STOP_LOSS:
        return "below"
    if order.side == Order.Side.BUY:
        return "below"
    return "above"


def first_crossing(prices, trigger, mode):
    """Index of the first price that satisfies the trigger, or None."""
    for i, price in enumerate(prices):
        if mode == "below" and price <= trigger:
            return i
        if mode == "above" and price >= trigger:
            return i
    return None


def apply_fill(portfolio, instrument, side, quantity, fill_price, user_id, at, note="", order=None):
    """Debit/credit cash and update the holding — the shared buy/sell core.

    Caller owns the transaction. When `order` is given (a pending limit/stop
    being filled lazily), that row is marked filled; otherwise a new market
    order row is created. Returns the Order or None if the fill cannot be
    satisfied (insufficient cash / holdings).
    """
    fill_price = _q4(fill_price)
    cost = _q2(fill_price * quantity)

    if side == Order.Side.BUY:
        if cost > portfolio.current_balance:
            return None
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
            return None
        portfolio.current_balance += cost
        holding.quantity -= quantity
        if holding.quantity == 0:
            holding.delete()
        else:
            holding.save(update_fields=["quantity", "updated_at"])

    portfolio.save(update_fields=["current_balance", "updated_at"])
    if order is not None:
        order.status = Order.Status.FILLED
        order.price = fill_price
        order.filled_at = at
        order.save(update_fields=["status", "price", "filled_at"])
        return order
    return Order.objects.create(
        user_id=user_id,
        portfolio=portfolio,
        instrument=instrument,
        side=side,
        quantity=quantity,
        order_type=Order.Type.MARKET,
        status=Order.Status.FILLED,
        price=fill_price,
        note=note,
        filled_at=at,
    )


def check_pending_orders(user_id, at=None):
    """Fill any of the user's pending orders whose trigger was crossed.

    Walks the deterministic price path from each order's placement tick to
    the current tick. Returns the list of orders that filled (or were
    cancelled for lack of cash/holdings) in this pass.
    """
    at = at or timezone.now()
    portfolio = VirtualPortfolio.get_or_create_for(user_id)
    changed = []
    with transaction.atomic():
        portfolio = VirtualPortfolio.objects.select_for_update().get(pk=portfolio.pk)
        pending = list(
            Order.objects.filter(user_id=user_id, status=Order.Status.PENDING)
            .select_related("instrument")
            .order_by("created_at")
        )
        for order in pending:
            mode = crossing_mode(order)
            from_tick = tick_of(order.created_at)
            to_tick = tick_of(at)
            prices = price_series(order.instrument, portfolio.seed, from_tick, to_tick)
            idx = first_crossing(prices, order.trigger_price, mode)

            if idx is None:
                # the tick endpoints missed — check the current interpolated price
                current = price_at(order.instrument, portfolio.seed, at=at)
                if (mode == "below" and current <= order.trigger_price) or (
                    mode == "above" and current >= order.trigger_price
                ):
                    fill_price = current
                else:
                    continue  # still pending
            else:
                fill_price = prices[idx]

            filled = apply_fill(
                portfolio, order.instrument, order.side, order.quantity, fill_price,
                user_id, at, note=order.note, order=order,
            )
            if filled is None:
                order.status = Order.Status.CANCELLED
                order.note = (order.note + " — cancelled: " + (
                    "insufficient cash" if order.side == Order.Side.BUY
                    else "insufficient holdings"
                )).strip()
                order.save(update_fields=["status", "note"])
                changed.append(order)
                continue
            changed.append(filled)

    if changed:
        # mark daily activity + re-evaluate badges for fills
        from streaks.models import Profile
        profile = Profile.get_or_create_for(user_id)
        profile.record_activity(at=at)
        profile.evaluate_badges()
    return changed
