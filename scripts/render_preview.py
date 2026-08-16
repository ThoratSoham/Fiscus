"""Render templates into self-contained preview.html files for visual QA.

Inlines each page's own CSS/JS so the files can be served standalone (e.g.
in a preview pane) with no Django server. CDN scripts (three.js,
supabase-js, Chart.js) are left as-is. Development tool only — the files
it produces are not committed.

Outputs:
  preview.html          — landing page
  preview-learn.html    — lesson list
  preview-lesson.html   — lesson detail (first lesson, playable quiz)
"""
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
    return html


def real_config():
    return {
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
    }


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

    for name, html in targets:
        out = os.path.join(ROOT, name)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print("wrote", out)


if __name__ == "__main__":
    main()
