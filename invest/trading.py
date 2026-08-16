"""Order execution for the simulated market (Phase 6 spec 6.4).

Market orders fill instantly at the engine price. Limit and stop-loss
orders stay **pending**; because every price is a computable function of
(seed, instrument, time), they fill **lazily** — when the student next
looks at their portfolio (or places another order), we walk the
deterministic price path between placement and now and fill at the first
tick that crossed the trigger. No polling, no background jobs.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .engine import EPOCH, TICKS_PER_DAY, TICK_SECONDS, latest_price, price_at, price_series, tick_of
from .models import Holding, Instrument, Order, VirtualPortfolio

PENNY = Decimal("0.01")

# Short-selling (spec 6.5): a fraction of every open short's current value is
# locked out of available cash as margin, mirroring real margin requirements.
# 50% keeps a short capped at 2× the student's available capital while still
# teaching that shorting ties up capital and can lose more than it gains.
SHORT_MARGIN_RATE = Decimal("0.5")


def _q2(value):
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


def _q4(value):
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def margin_reserve(portfolio, at=None):
    """Sum of the margin locked by every open short (spec 6.5).

    Reserve = SHORT_MARGIN_RATE × Σ |short quantity × current price|, priced
    at engine prices so a rally against the short grows the reserve and
    shrinks available cash — the "shorting ties up capital" lesson.
    """
    from django.utils import timezone
    at = at or timezone.now()
    reserve = Decimal("0")
    for holding in portfolio.holdings.select_related("instrument").filter(quantity__lt=0):
        price = latest_price(holding.instrument, portfolio.seed, at=at)[0]
        reserve += SHORT_MARGIN_RATE * abs(holding.quantity) * price
    return _q2(reserve)


def available_cash(portfolio, at=None):
    """Cash not locked by short margin — what new orders can actually use."""
    return _q2(portfolio.current_balance - margin_reserve(portfolio, at))


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

    Supports short-selling (spec 6.5): a sell beyond the long holding opens
    or extends a short (negative quantity); a buy against a short covers it.
    Margin checks keep available cash (cash − margin reserve) ≥ 0 after any
    voluntary order, and cap a new short at the available capital. P&L for a
    short is (avg − price) × qty — profits when the price falls.

    Caller owns the transaction. When `order` is given (a pending limit/stop
    being filled lazily), that row is marked filled; otherwise a new market
    order row is created. Returns the Order or None if the fill cannot be
    satisfied (insufficient available cash).
    """
    fill_price = _q4(fill_price)
    cost = _q2(fill_price * quantity)
    holding = Holding.objects.select_for_update().filter(
        portfolio=portfolio, instrument=instrument
    ).first()
    old_qty = holding.quantity if holding else Decimal("0")

    if side == Order.Side.BUY:
        # covering part of a short releases its margin reserve, which funds
        # the cover; the rest must come from available cash
        short_qty = -old_qty if old_qty < 0 else Decimal("0")
        released = SHORT_MARGIN_RATE * fill_price * min(short_qty, quantity)
        if _q2(cost - released) > available_cash(portfolio, at):
            return None
        portfolio.current_balance -= cost
        new_qty = old_qty + quantity
        if holding is None:
            Holding.objects.create(
                portfolio=portfolio, instrument=instrument,
                quantity=quantity, avg_price=fill_price,
            )
        elif new_qty == 0:
            holding.delete()
        elif old_qty < 0 <= new_qty:
            # cover exceeded the short → residual long entered at cover price
            holding.quantity = new_qty
            holding.avg_price = fill_price
            holding.save(update_fields=["quantity", "avg_price", "updated_at"])
        elif old_qty < 0:
            # partial cover — avg entry price unchanged
            holding.quantity = new_qty
            holding.save(update_fields=["quantity", "updated_at"])
        else:
            holding.quantity = new_qty
            holding.avg_price = _q4(
                (holding.avg_price * old_qty + fill_price * quantity) / new_qty
            )
            holding.save(update_fields=["quantity", "avg_price", "updated_at"])
    else:  # sell
        long_qty = old_qty if old_qty > 0 else Decimal("0")
        short_portion = quantity - long_qty
        if short_portion > 0:
            # opening a short: the new short's value must fit in available cash
            if _q2(fill_price * short_portion) > available_cash(portfolio, at):
                return None
        portfolio.current_balance += cost
        new_qty = old_qty - quantity
        if holding is None:
            Holding.objects.create(
                portfolio=portfolio, instrument=instrument,
                quantity=-quantity, avg_price=fill_price,
            )
        elif new_qty == 0:
            holding.delete()
        elif new_qty > 0:
            # long reduced — avg entry price unchanged
            holding.quantity = new_qty
            holding.save(update_fields=["quantity", "updated_at"])
        elif old_qty > 0:
            # flipped long → short: the short portion entered at fill price
            holding.quantity = new_qty
            holding.avg_price = fill_price
            holding.save(update_fields=["quantity", "avg_price", "updated_at"])
        else:
            # extended short — weighted avg across negative quantities
            holding.quantity = new_qty
            holding.avg_price = _q4(
                (holding.avg_price * old_qty - fill_price * short_portion) / new_qty
            )
            holding.save(update_fields=["quantity", "avg_price", "updated_at"])

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


def portfolio_history(portfolio, days=30, at=None):
    """Daily portfolio value for the last `days` simulated days (spec 6.8).

    Reconstructed deterministically from the order fill ledger + the engine:
    start at the starting balance, replay fills chronologically (using their
    recorded prices), then mark holdings to market at each day boundary with
    the engine price. No snapshot table, no background job.
    """
    at = at or timezone.now()
    end_tick = tick_of(at)
    start_tick = max(end_tick - days * TICKS_PER_DAY, 0)
    start_time = EPOCH + timedelta(seconds=start_tick * TICK_SECONDS)

    orders = list(
        Order.objects.filter(portfolio=portfolio)
        .select_related("instrument")
        .order_by("filled_at", "id")
    )
    instruments = {i.id: i for i in Instrument.objects.all()}

    cash = portfolio.starting_balance
    holdings = {}  # instrument_id -> Decimal quantity
    history = []
    oi = 0

    for d in range(days + 1):
        if d == days:
            t = at  # final point is "now", so today's fills are included
        else:
            tick = start_tick + d * TICKS_PER_DAY
            t = EPOCH + timedelta(seconds=tick * TICK_SECONDS)

        while oi < len(orders) and orders[oi].filled_at and orders[oi].filled_at <= t:
            order = orders[oi]
            qty = holdings.get(order.instrument_id, Decimal("0"))
            if order.side == Order.Side.BUY:
                cash -= (order.price * order.quantity).quantize(PENNY)
                holdings[order.instrument_id] = qty + order.quantity
            else:
                cash += (order.price * order.quantity).quantize(PENNY)
                holdings[order.instrument_id] = qty - order.quantity
            oi += 1

        value = cash
        for instrument_id, qty in holdings.items():
            if not qty:
                continue
            instrument = instruments.get(instrument_id)
            if instrument is None:
                continue
            price = price_at(instrument, portfolio.seed, at=t)
            value += (price * qty).quantize(PENNY)

        history.append({"date": t.date().isoformat(), "value": str(value.quantize(PENNY))})
    return history


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
                if order.side == Order.Side.BUY:
                    reason = "insufficient cash"
                else:
                    holding = Holding.objects.filter(
                        portfolio=portfolio, instrument=order.instrument
                    ).first()
                    would_open_short = holding is None or holding.quantity < order.quantity
                    reason = (
                        "insufficient available cash (short margin)" if would_open_short
                        else "insufficient holdings"
                    )
                order.note = (order.note + " — cancelled: " + reason).strip()
                order.save(update_fields=["status", "note"])
                changed.append(order)
                continue
            changed.append(filled)

    # Margin calls (spec 6.5): force-close any short the student can no
    # longer cover (its current value exceeds cash on hand) — the honest
    # outcome of a short that ran away, and the Rohan-lesson mechanic.
    changed.extend(enforce_margin(portfolio, at))

    if changed:
        # mark daily activity + re-evaluate badges for fills
        from streaks.models import Profile
        profile = Profile.get_or_create_for(user_id)
        profile.record_activity(at=at)
        profile.evaluate_badges()
    return changed


def enforce_margin(portfolio, at=None):
    """Force-close shorts whose current value exceeds the cash on hand.

    Closes the largest short first, then re-scans (closing one short reduces
    cash, which can expose another). The close is recorded as a filled
    buy-back order with a "margin call" note; cash may go negative — that is
    the loss, and the reset panel is the way back. Returns the new orders.
    """
    from django.utils import timezone
    at = at or timezone.now()
    changed = []
    while True:
        shorts = list(
            portfolio.holdings.select_related("instrument").filter(quantity__lt=0)
        )
        if not shorts:
            return changed
        valued = []
        for holding in shorts:
            price = latest_price(holding.instrument, portfolio.seed, at=at)[0]
            valued.append((holding, price, _q2(abs(holding.quantity) * price)))
        valued.sort(key=lambda item: item[2], reverse=True)
        closed = False
        for holding, price, value in valued:
            if value > portfolio.current_balance:
                portfolio.current_balance -= value
                changed.append(
                    Order.objects.create(
                        user_id=portfolio.user_id,
                        portfolio=portfolio,
                        instrument=holding.instrument,
                        side=Order.Side.BUY,
                        quantity=abs(holding.quantity),
                        order_type=Order.Type.MARKET,
                        status=Order.Status.FILLED,
                        price=price,
                        note="margin call — short exceeded available cash",
                        filled_at=at,
                    )
                )
                holding.delete()
                portfolio.save(update_fields=["current_balance", "updated_at"])
                closed = True
                break  # cash changed — re-scan remaining shorts
        if not closed:
            return changed
