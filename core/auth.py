"""Supabase JWT authentication for the Fiscus API.

The frontend (supabase-js) sends `Authorization: Bearer <access_token>`.
We verify the token's RS256 signature against Supabase's public JWKS
endpoint (cached by PyJWT's PyJWKClient), check exp/aud, and attach the
Supabase user id to the request as a lightweight ``SupabaseUser``.
"""
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        base = settings.SUPABASE_URL.rstrip("/")
        if not base or "<project-ref>" in base:
            raise AuthenticationFailed("SUPABASE_URL is not configured.")
        _jwks_client = jwt.PyJWKClient(base + "/auth/v1/.well-known/jwks.json")
    return _jwks_client


class SupabaseUser:
    """Lightweight stand-in for Django's auth user; a Supabase identity."""

    def __init__(self, id, email=None, claims=None):
        self.id = id
        self.email = email
        self.claims = claims or {}
        self.is_authenticated = True
        self.is_anonymous = False

    @property
    def pk(self):
        return self.id

    def __str__(self):
        return self.email or self.id


class SupabaseJWTAuthentication(BaseAuthentication):
    """DRF authentication backend for Supabase access tokens."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword + " "):
            return None  # no credentials — permission classes decide
        token = header[len(self.keyword) + 1:].strip()
        if not token:
            return None
        return (self._verify(token), token)

    def authenticate_header(self, request):
        return self.keyword

    def _verify(self, token):
        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                # Supabase signs access tokens with RS256 or ES256 depending
                # on the project's active signing key — accept both.
                algorithms=["RS256", "ES256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        except AuthenticationFailed:
            raise
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("Invalid or expired token.") from exc
        return SupabaseUser(id=payload["sub"], email=payload.get("email"), claims=payload)
