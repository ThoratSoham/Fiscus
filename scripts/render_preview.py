"""Render templates into self-contained preview.html files for visual QA.

Inlines each page's own CSS/JS so the files can be served standalone (e.g.
in a preview pane) with no Django server. CDN scripts (three.js,
supabase-js, Chart.js) are left as-is. Development tool only — the files
it produces are not committed.

Outputs:
  preview.html          — landing page
  preview-learn.html    — lesson list
  preview-lesson.html   — lesson detail (first lesson, playable quiz)
  preview-invest.html   — invest page (mock data, no session)
"""
import json
import os
import sys

import django

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fiscus.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.template.loader import render_to_string  # noqa: E402

from learn.models import Lesson  # noqa: E402


def read_static(relpath):
    with open(os.path.join(ROOT, relpath), encoding="utf-8") as f:
        return f.read()


def inline(html, css_assets, js_assets):
    """Replace {% static %} tags with inlined content.

    Each asset is a tuple (url_path, disk_path) where url_path is the path
    Django renders after STATIC_URL and disk_path is relative to ROOT.
    After inlining, the JS is patched so the preview never redirects to
    the login page (the static preview has no session).
    """
    for url_path, disk_path in css_assets:
        html = html.replace(
            f'<link rel="stylesheet" href="/static/{url_path}">',
            "<style>\n" + read_static(disk_path) + "\n</style>",
        )
    for url_path, disk_path, is_module in js_assets:
        if is_module:
            html = html.replace(
                f'<script type="module" src="/static/{url_path}"></script>',
                '<script type="module">\n' + read_static(disk_path) + "\n</script>",
            )
        else:
            html = html.replace(
                f'<script src="/static/{url_path}" defer></script>',
                "<script>\n" + read_static(disk_path) + "\n</script>",
            )
    html = html.replace(
        'var previewMode = new URLSearchParams(window.location.search).has("preview");',
        "var previewMode = true;",
    )
    html = html.replace(
        'const force3d = new URLSearchParams(location.search).has("force3d");',
        "const force3d = true;",
    )
    return html


def real_config():
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
    }


def _mock_walk(start, n, vol, seed=7):
    """Deterministic pseudo-random walk for preview data."""
    x = seed
    out = []
    value = start
    for _ in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        value *= 1 + (vol * ((x / 0x7FFFFFFF) - 0.5))
        out.append(value)
    return out


def invest_mock():
    """Build the full preview mock: static base (instruments/portfolio) merged
    with generated chart + history data, plus per-holding sparklines."""
    base = json.loads(INVEST_MOCK)
    history = _mock_walk(100000.0, 31, 0.004)
    history[30] = 100130.0  # pin the last point to the portfolio value
    closes = _mock_walk(480.0, 31, 0.02, seed=11)
    candles = []
    prev_close = 480.0
    for i, close in enumerate(closes):
        open_ = prev_close
        high = max(open_, close) * (1 + 0.004 * ((i * 7) % 3))
        low = min(open_, close) * (1 - 0.004 * ((i * 5) % 3))
        candles.append(
            {
                "date": f"2026-07-{(i % 28) + 1:02d}",
                "open": round(open_, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
            }
        )
        prev_close = close
    # per-holding sparklines: deterministic walk around each avg price
    holdings = base["portfolio"]["holdings"]
    for idx, h in enumerate(holdings):
        avg = float(h["avg_price"])
        walk = _mock_walk(avg, 14, 0.015, seed=3 + idx)
        walk[-1] = float(h["last_price"])  # end at the live price
        h["spark"] = [round(v, 2) for v in walk]
    base["portfolio"]["history"] = [
        {"date": f"day-{i:02d}", "value": f"{v:.2f}"} for i, v in enumerate(history)
    ]
    base.update(
        {
            "chart": {
                "symbol": "ORBIT",
                "name": "Orbit Motors",
                "current": f"{closes[-1]:.2f}",
                "candles": candles,
                "holding": {"quantity": "10", "avg_price": f"{closes[20]:.2f}"},
                "pending": [
                    {"id": 1, "side": "buy", "order_type": "limit", "trigger_price": f"{closes[-1] * 0.98:.2f}"},
                    {"id": 2, "side": "sell", "order_type": "stop_loss", "trigger_price": f"{closes[15]:.2f}"},
                ],
                "fills": [
                    {"side": "buy", "price": f"{closes[20]:.2f}", "quantity": "10", "filled_at": "2026-08-14T10:02:00Z"},
                    {"side": "buy", "price": f"{closes[12]:.2f}", "quantity": "5", "filled_at": "2026-08-11T09:30:00Z"},
                    {"side": "sell", "price": f"{closes[15]:.2f}", "quantity": "5", "filled_at": "2026-08-12T11:00:00Z"},
                ],
            },
        }
    )
    return base


INVEST_MOCK = """{
  "instruments": [
    {"id": 1, "symbol": "NIFTY-SIM", "name": "Nifty Sim Index", "kind": "index", "price": "24531.75", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false},
    {"id": 2, "symbol": "BANKNIFTY-SIM", "name": "Bank Nifty Sim Index", "kind": "index", "price": "52108.40", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false},
    {"id": 3, "symbol": "SENSEX-SIM", "name": "Sensex Sim Index", "kind": "index", "price": "80211.90", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false},
    {"id": 4, "symbol": "ORBIT", "name": "Orbit Motors", "kind": "stock", "price": "493.60", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false},
    {"id": 5, "symbol": "PIXEL", "name": "Pixelworks Tech", "kind": "stock", "price": "1472.10", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false},
    {"id": 6, "symbol": "DUNE", "name": "Dune Metals", "kind": "stock", "price": "594.30", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false},
    {"id": 7, "symbol": "SOLARIS", "name": "Solaris Energy", "kind": "stock", "price": "101.85", "as_of": "2026-08-16T10:15:00+05:30", "source": "simulated", "stale": false}
  ],
  "portfolio": {
    "starting_balance": "100000.00",
    "cash": "36107.00",
    "invested": "63893.00",
    "portfolio_value": "100130.00",
    "return_amount": "130.00",
    "return_pct": "0.13",
    "holdings": [
      {"instrument_id": 4, "symbol": "ORBIT", "name": "Orbit Motors", "quantity": "10", "avg_price": "480.0000", "last_price": "493.60", "invested": "4800.00", "current_value": "4936.00", "pnl": "136.00", "pnl_pct": "2.83", "stale": false},
      {"instrument_id": 1, "symbol": "NIFTY-SIM", "name": "Nifty Sim Index", "quantity": "0.5", "avg_price": "24500.0000", "last_price": "24531.75", "invested": "12250.00", "current_value": "12265.88", "pnl": "15.88", "pnl_pct": "0.13", "stale": false},
      {"instrument_id": 5, "symbol": "PIXEL", "name": "Pixelworks Tech", "quantity": "10", "avg_price": "1450.0000", "last_price": "1472.10", "invested": "14500.00", "current_value": "14721.00", "pnl": "221.00", "pnl_pct": "1.52", "stale": false},
      {"instrument_id": 6, "symbol": "DUNE", "name": "Dune Metals", "quantity": "20", "avg_price": "610.0000", "last_price": "594.30", "invested": "12200.00", "current_value": "11886.00", "pnl": "-314.00", "pnl_pct": "-2.57", "stale": false}
    ],
    "recent_orders": [
      {"id": 1, "instrument_symbol": "ORBIT", "side": "buy", "quantity": "10", "order_type": "limit", "status": "pending", "trigger_price": "470.0000", "price": null, "created_at": "2026-08-16T10:05:00Z"},
      {"id": 2, "instrument_symbol": "PIXEL", "side": "sell", "quantity": "10", "order_type": "stop_loss", "status": "pending", "trigger_price": "1380.0000", "price": null, "created_at": "2026-08-16T10:02:00Z"},
      {"id": 3, "instrument_symbol": "ORBIT", "side": "buy", "quantity": "10", "order_type": "market", "status": "filled", "price": "480.0000", "created_at": "2026-08-16T09:41:00Z"},
      {"id": 4, "instrument_symbol": "NIFTY-SIM", "side": "buy", "quantity": "0.5", "order_type": "market", "status": "filled", "price": "24500.0000", "created_at": "2026-08-16T09:20:00Z"},
      {"id": 5, "instrument_symbol": "PIXEL", "side": "buy", "quantity": "10", "order_type": "market", "status": "filled", "price": "1450.0000", "created_at": "2026-08-15T12:20:00Z"},
      {"id": 6, "instrument_symbol": "DUNE", "side": "buy", "quantity": "20", "order_type": "market", "status": "filled", "price": "610.0000", "created_at": "2026-08-15T11:05:00Z"}
    ]
  }
}"""


def main():
    targets = []

    # ---- landing page ----
    landing = render_to_string(
        "core/index.html",
        {
            "config": {
                "supabase_url": "https://demo.supabase.co",
                "supabase_anon_key": "demo-anon-key",
            }
        },
    )
    landing = inline(
        landing,
        [("core/css/brutalist.css", "core/static/core/css/brutalist.css")],
        [
            ("core/js/hero3d.js", "core/static/core/js/hero3d.js", True),
            ("core/js/landing.js", "core/static/core/js/landing.js", False),
        ],
    )
    targets.append(("preview.html", landing))

    # ---- learn pages ----
    lessons = list(Lesson.objects.all().order_by("order"))
    if not lessons:
        print("No lessons seeded yet — skipping Learn previews. Run: manage.py seed_lessons")
    else:
        lesson_list = inline(
            render_to_string("learn/lesson_list.html", {"lessons": lessons, "config": real_config()}),
            [("learn/css/learn.css", "learn/static/learn/css/learn.css")],
            [("learn/js/learn.js", "learn/static/learn/js/learn.js", False)],
        )
        targets.append(("preview-learn.html", lesson_list))

        lesson = lessons[0]
        next_lesson = lessons[1] if len(lessons) > 1 else None
        detail = inline(
            render_to_string(
                "learn/lesson_detail.html",
                {"lesson": lesson, "next_lesson": next_lesson, "config": real_config()},
            ),
            [("learn/css/learn.css", "learn/static/learn/css/learn.css")],
            [("learn/js/learn.js", "learn/static/learn/js/learn.js", False)],
        )
        targets.append(("preview-lesson.html", detail))

    # ---- invest page (preview mode: mock data injected, no session) ----
    invest_html = render_to_string(
        "invest/invest.html",
        {"config": {"supabase_url": "https://demo.supabase.co", "supabase_anon_key": "demo-anon-key"}},
    )
    invest_html = invest_html.replace(
        '<link rel="stylesheet" href="/static/core/css/brutalist.css">',
        "<style>\n" + read_static("core/static/core/css/brutalist.css") + "\n</style>",
    )
    invest_html = invest_html.replace(
        '<link rel="stylesheet" href="/static/invest/css/invest.css">',
        "<style>\n" + read_static("invest/static/invest/css/invest.css") + "\n</style>",
    )
    mock = json.dumps(invest_mock())
    invest_html = invest_html.replace(
        '<script src="/static/invest/js/invest.js" defer></script>',
        "<script>window.FISCUS_MOCK = " + mock + ";</script>"
        + "\n<script>\n"
        + read_static("invest/static/invest/js/invest.js")
        + "\n</script>",
    )
    invest_html = invest_html.replace(
        "var PREVIEW = !!window.FISCUS_PREVIEW;",
        "var PREVIEW = true;",
    )
    targets.append(("preview-invest.html", invest_html))

    for name, html in targets:
        out = os.path.join(ROOT, name)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print("wrote", out)


if __name__ == "__main__":
    main()
