from django.conf import settings
from django.shortcuts import render


def index(request):
    """Brutalist landing page with 3D hero and client-side Supabase auth."""
    return render(
        request,
        "core/index.html",
        {
            "config": {
                "supabase_url": settings.SUPABASE_URL,
                "supabase_anon_key": settings.SUPABASE_ANON_KEY,
            }
        },
    )
