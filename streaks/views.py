from django.conf import settings
from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.auth import SupabaseJWTAuthentication
from .models import Profile

AUTH = [SupabaseJWTAuthentication]
PERM = [permissions.IsAuthenticated]


def serialize_profile(profile):
    return {
        "user_id": str(profile.user_id),
        "streak_count": profile.streak_count,
        "last_activity_date": (
            profile.last_activity_date.isoformat() if profile.last_activity_date else None
        ),
        "badges": profile.badges_dict(),
    }


@api_view(["GET"])
@authentication_classes(AUTH)
@permission_classes(PERM)
def profile_view(request):
    profile = Profile.get_or_create_for(request.user.id)
    return Response(serialize_profile(profile))


@api_view(["GET", "POST"])
def cron_streaks(request):
    """Vercel Cron entrypoint (daily midnight): reset stale streaks.

    Vercel sends the cron secret as `Authorization: Bearer <CRON_SECRET>`.
    With DEBUG=False a configured CRON_SECRET is mandatory.
    """
    secret = settings.CRON_SECRET
    auth = request.headers.get("Authorization", "")
    if secret and auth != f"Bearer {secret}":
        return Response({"detail": "Unauthorized"}, status=401)
    if not secret and not settings.DEBUG:
        return Response({"detail": "CRON_SECRET is not configured"}, status=500)
    reset = Profile.reset_stale_streaks()
    return Response({"reset": reset, "at": timezone.now().isoformat()})
