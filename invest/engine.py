"""The simulated market engine (Phase 6 spec 6.1–6.3).

Every price is a deterministic function of (seed, instrument, elapsed time):
a seeded random walk (Geometric-Brownian-Motion style) plus scripted
volatility events. Because the path is a pure function of the clock, there
is **nothing running in the background** — no polling, no external API, no
connection churn (this also removes the connection-pool exhaustion that
the old live-feed pipeline caused). Prices are computed on demand.

Design notes:
- Ticks are 15 simulated minutes; within a tick the price interpolates
  linearly in log space so it feels continuous and "ticking" when the
  frontend re-queries every few seconds. The 15-min buckets also become
  the natural OHLC buckets for candlestick charts later (spec 6.8).
- Each instrument has a personality (base_price, volatility, drift) from
  its row — some steady blue chips, some volatile growth names.
- Per-tick randomness uses splitmix64 (fast, deterministic) and cumulative
  log values are memoized per (instrument, seed, tick), so the 5-second
  ticker re-uses the same tick's walk instead of recomputing it — a fresh
  tick costs only ~10-20ms per instrument.
- Scripted events (crash/rally windows, spec 6.3) are derived from the
  seed alone: the same student always relives the same sequence, but
  students differ — a genuine "your market, your decisions" lesson.
"""
import hashlib
import math
from datetime import timezone as dt_timezone
from decimal import Decimal
from functools import lru_cache

from django.utils import timezone

TICK_SECONDS = 900            # one simulated tick = 15 real minutes
TICK_DAYS = TICK_SECONDS / 86400.0
EVENT_WINDOW_TICKS = 8        # a crash/rally lasts ~2 simulated hours
EVENT_SLOTS = 8               # ~8 scripted events per student's first month

# Prices are only defined from this point onward; the student's market
# "starts" at the epoch so t=0 prices equal each instrument's base price.
EPOCH = timezone.datetime(2026, 1, 1, tzinfo=dt_timezone.utc)

_MASK = (1 << 64) - 1


def _mix(x):
    """splitmix64 finalizer — fast deterministic avalanche."""
    x = (x ^ (x >> 30)) & _MASK
    x = (x * 0xBF58476D1CE4E5B9) & _MASK
    x = (x ^ (x >> 27)) & _MASK
    x = (x * 0x94D049BB133111EB) & _MASK
    x = (x ^ (x >> 31)) & _MASK
    return x


def _rand(seed, instrument_id, tick):
    """Deterministic pseudo-random in [0, 1) for a given tick."""
    x = (
        seed * 0x9E3779B97F4A7C15
        ^ instrument_id * 0xBF58476D1CE4E5B9
        ^ tick * 0x94D049BB133111EB
    ) & _MASK
    return _mix(x) / 2**64


def event_schedule(seed):
    """Deterministic per-student list of scripted events.

    Returns [{"start": tick, "magnitude": float, "slot": int}, ...].
    magnitude < 0 is a crash, > 0 a rally (4–10% over the window).
    """
    events = []
    for slot in range(EVENT_SLOTS):
        h = hashlib.sha256(f"fiscus-event|{seed}|{slot}".encode()).digest()
        day = 1 + int.from_bytes(h[0:4], "big") % 30     # sometime in month one
        hour = int.from_bytes(h[4:6], "big") % 24
        start = day * 1440 + hour * 60                   # in ticks (15-min units)
        crash = int.from_bytes(h[6:8], "big") % 2 == 0
        strength = 0.04 + 0.06 * (int.from_bytes(h[8:10], "big") / 2**16)
        events.append(
            {"start": start, "magnitude": -strength if crash else strength, "slot": slot}
        )
    return events


def _affected(seed, slot, symbol):
    """Whether event `slot` hits instrument `symbol` (deterministic ~40%)."""
    h = hashlib.sha256(f"fiscus-affect|{seed}|{slot}|{symbol}".encode()).digest()
    return (int.from_bytes(h[:8], "big") % 100) < 40


def _shock_log(seed, symbol, tick, events):
    """Log-space price shock from scripted events at a given tick."""
    total = 0.0
    for event in events:
        if not _affected(seed, event["slot"], symbol):
            continue
        offset = tick - event["start"]
        if 0 <= offset < EVENT_WINDOW_TICKS:
            # triangle fade: ramp in, peak mid-window, ramp out
            fade = 1.0 - abs(offset - EVENT_WINDOW_TICKS / 2) / (EVENT_WINDOW_TICKS / 2)
            total += event["magnitude"] * fade
    return total


@lru_cache(maxsize=65536)
def _walk_log(instrument_id, seed, tick, volatility, drift):
    """Cumulative log return of the random walk up to tick `t` (no events).

    Memoized per (instrument, seed, tick) so the 5-second ticker re-uses the
    current tick's walk instead of recomputing it on every poll.
    """
    total = 0.0
    for i in range(tick):
        r = _rand(seed, instrument_id, i)
        total += drift * TICK_DAYS + volatility * (2 * r - 1) * math.sqrt(TICK_DAYS)
    return total


def price_series(instrument, seed, from_tick, to_tick):
    """Deterministic list of Decimal prices for ticks [from_tick, to_tick]
    inclusive, events included. Used by the lazy limit/stop crossing check
    (spec 6.4): the path between placement and now is walked once, cheaply,
    instead of running any background job.
    """
    if to_tick < from_tick:
        return []
    events = event_schedule(seed)

    def shock(k):
        return _shock_log(seed, instrument.symbol, k, events)

    start = max(from_tick - 1, 0)
    prev_log = _walk_log(instrument.id, seed, start, instrument.volatility, instrument.drift) + shock(start)
    prices = []
    for k in range(from_tick, to_tick + 1):
        if k >= 1:
            increment = (
                instrument.drift * TICK_DAYS
                + instrument.volatility * (2 * _rand(seed, instrument.id, k - 1) - 1) * math.sqrt(TICK_DAYS)
            )
            prev_log += increment + (shock(k) - shock(k - 1))
        prices.append(
            Decimal(str(float(instrument.base_price) * math.exp(prev_log))).quantize(Decimal("0.01"))
        )
    return prices


def price_at(instrument, seed, at=None):
    """Deterministic simulated price for (instrument, seed, time).

    Returns a Decimal quantized to 2dp (cash precision). Pure function of
    the clock — no DB writes, no network, no background jobs.
    """
    at = at or timezone.now()
    elapsed = max((at - EPOCH).total_seconds(), 0.0)
    ticks = int(elapsed // TICK_SECONDS)
    frac = (elapsed % TICK_SECONDS) / TICK_SECONDS
    events = event_schedule(seed)

    walk0 = _walk_log(instrument.id, seed, ticks, instrument.volatility, instrument.drift)
    walk1 = _walk_log(instrument.id, seed, ticks + 1, instrument.volatility, instrument.drift)
    shock0 = _shock_log(seed, instrument.symbol, ticks, events)
    shock1 = _shock_log(seed, instrument.symbol, ticks + 1, events)

    log_value = (walk0 + shock0) + ((walk1 + shock1) - (walk0 + shock0)) * frac
    price = float(instrument.base_price) * math.exp(log_value)
    return Decimal(str(price)).quantize(Decimal("0.01"))


def latest_price(instrument, seed, at=None):
    """(price, as_of, source, stale) — the interface the views use.

    The simulated market is 24/7: always fresh, always available.
    """
    at = at or timezone.now()
    return price_at(instrument, seed, at=at), at, "simulated", False
