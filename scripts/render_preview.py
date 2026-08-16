"""Render the landing template into a self-contained preview.html for visual QA.

Inlines the page's own CSS/JS (from core/static) so the file can be served
standalone (e.g. in a preview pane) with no Django server. CDN scripts
(three.js, supabase-js) are left as-is. Development tool only — the file
it produces is not committed.
"""
import os
import sys

import django

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fiscus.settings")
django.setup()

from django.template.loader import render_to_string  # noqa: E402


def read_static(relpath):
    with open(os.path.join(ROOT, "core/static/core", relpath), encoding="utf-8") as f:
        return f.read()


def main():
    html = render_to_string(
        "core/index.html",
        {
            "config": {
                "supabase_url": "https://demo.supabase.co",
                "supabase_anon_key": "demo-anon-key",
            }
        },
    )

    html = html.replace(
        '<link rel="stylesheet" href="/static/core/css/brutalist.css">',
        "<style>\n" + read_static("css/brutalist.css") + "\n</style>",
    )
    html = html.replace(
        '<script type="module" src="/static/core/js/hero3d.js"></script>',
        '<script type="module">\n' + read_static("js/hero3d.js") + "\n</script>",
    )
    html = html.replace(
        '<script src="/static/core/js/landing.js" defer></script>',
        "<script>\n" + read_static("js/landing.js") + "\n</script>",
    )

    out = os.path.join(ROOT, "preview.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", out)


if __name__ == "__main__":
    main()
