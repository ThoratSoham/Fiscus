from django.http import HttpResponse


def index(request):
    """Skeleton landing page — proves Django is serving end to end."""
    return HttpResponse(
        "<h1>It works!</h1><p>Fiscus is running on Django + Supabase Postgres.</p>"
    )
