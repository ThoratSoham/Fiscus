"""Market-data fetching for the paper-trading engine.

Reality check (from the Phase 6 spec): no free, legal API offers true
real-time NSE ticks from a datacenter IP. Verified empirically here:

- NSE's public endpoints block server IPs outright (403 Access Denied).
- Yahoo Finance's chart endpoint works with a browser User-Agent and
  returns near-real-time (often 15-min delayed) prices for Indian
  tickers — so Yahoo is the primary source, with NSE as a documented
  non-option for now.

Design:
- `latest_price()` serves the freshest snapshot within a TTL (60s) and
  only hits the upstream when the cache is cold — so a page load refreshes
  prices without hammering Yahoo on every request.
- On fetch failure we fall back to the last known snapshot, then to the
  instrument's seeded `default_price`. The app degrades, never crashes.
- `refresh_all()` fans out across instruments with a small thread pool,
  which is what the cron endpoint and the page's lazy refresh call.
"""
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Instrument, PriceSnapshot

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
FETCH_TIMEOUT = 8  # seconds, per symbol
DEFAULT_TTL_SECONDS = 60

_IST = ZoneInfo("Asia/Kolkata")


class QuoteError(Exception):
    """Raised when the upstream feed is unreachable or returns junk."""


def fetch_quote(yahoo_symbol):
    """Fetch the latest price for a Yahoo symbol.

    Returns (price: float, epoch_ts: int|None). Raises QuoteError on any
    failure so callers can degrade to stored/default prices.
    """
    url = CHART_URL.format(symbol=urllib.parse.quote(yahoo_symbol))
    request = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network, timeout, JSON — all the same outcome
        raise QuoteError(f"fetch failed for {yahoo_symbol}: {exc}") from exc

    try:
        meta = payload["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        epoch = meta.get("regularMarketTime")
    except (KeyError, IndexError, TypeError) as exc:
        error = payload.get("chart", {}).get("error")
        raise QuoteError(f"bad payload for {yahoo_symbol}: {error}") from exc

    return float(price), epoch


def refresh_instrument(instrument):
    """Fetch + store a fresh snapshot. Returns the snapshot or None on failure."""
    try:
        price, _epoch = fetch_quote(instrument.yahoo_symbol)
    except QuoteError:
        return None
    return PriceSnapshot.objects.create(
        instrument=instrument,
        price=Decimal(str(price)),
        source="yahoo",
        fetched_at=timezone.now(),
    )


def refresh_all(active_only=True):
    """Fetch fresh snapshots for every active instrument (threaded).

    Returns {instrument_id: PriceSnapshot|None} so callers can build price
    maps without extra queries.
    """
    queryset = Instrument.objects.filter(is_active=True) if active_only else Instrument.objects.all()
    instruments = list(queryset)
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(refresh_instrument, inst): inst for inst in instruments}
        for future, inst in futures.items():
            results[inst.id] = future.result()
    return results


def latest_price(instrument, max_age_seconds=DEFAULT_TTL_SECONDS, refresh=True):
    """Best-known price for an instrument.

    Returns (price: Decimal, as_of: datetime|None, source: str, stale: bool).
    Uses a fresh-enough snapshot if present, otherwise tries a live fetch,
    otherwise falls back to the last snapshot, then to default_price.
    """
    snapshot = (
        PriceSnapshot.objects.filter(instrument=instrument).order_by("-fetched_at").first()
    )
    if snapshot and (timezone.now() - snapshot.fetched_at).total_seconds() <= max_age_seconds:
        return snapshot.price, snapshot.fetched_at, snapshot.source, False
    if refresh:
        new = refresh_instrument(instrument)
        if new:
            return new.price, new.fetched_at, new.source, False
    if snapshot:
        return snapshot.price, snapshot.fetched_at, snapshot.source, True
    return instrument.default_price, None, "default", True


def is_market_open(at=None):
    """NSE equity hours: 9:15–15:30 IST, Monday–Friday."""
    at = at or timezone.now()
    local = at.astimezone(_IST)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return (9 * 60 + 15) <= minutes < (15 * 60 + 30)
