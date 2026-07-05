"""Session and optional OIDC OAuth authentication for the web API.

Configuration (environment):

* ``UCS_SESSION_SECRET`` — HMAC secret for session tokens (required for sessions)
* ``UCS_ADMIN_USER`` / ``UCS_ADMIN_PASSWORD`` — local login (optional)
* ``UCS_OAUTH_ISSUER`` — OIDC issuer URL (e.g. https://accounts.google.com)
* ``UCS_OAUTH_CLIENT_ID`` / ``UCS_OAUTH_CLIENT_SECRET``
* ``UCS_OAUTH_REDIRECT_URI`` — callback URL (default: http://127.0.0.1:8000/api/auth/oauth/callback)
* ``UCS_API_KEY`` — legacy API key (still accepted)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, Request, Response

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ucs_session"
SESSION_TTL_S = int(os.environ.get("UCS_SESSION_TTL_S", str(24 * 3600)))
_oauth_states: dict[str, float] = {}


@dataclass(frozen=True)
class AuthUser:
    sub: str
    method: str  # api_key | session | oauth


def _session_secret() -> str | None:
    return os.environ.get("UCS_SESSION_SECRET") or os.environ.get("UCS_API_KEY")


def auth_enabled() -> bool:
    return bool(
        os.environ.get("UCS_API_KEY")
        or (_session_secret() and os.environ.get("UCS_ADMIN_PASSWORD"))
        or os.environ.get("UCS_OAUTH_CLIENT_ID")
    )


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_session_token(sub: str, *, ttl_s: int = SESSION_TTL_S) -> str:
    secret = _session_secret()
    if not secret:
        raise RuntimeError("UCS_SESSION_SECRET or UCS_API_KEY required for sessions")
    payload = {"sub": sub, "exp": int(time.time()) + ttl_s, "iat": int(time.time())}
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64url(sig)}"


def peek_session_token(token: str) -> dict[str, Any] | None:
    """Decode a session token without enforcing expiry (for status display)."""
    secret = _session_secret()
    if not secret or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64url(expected), sig):
            return None
        return json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        return None


def session_cookie_info(request: Request) -> dict[str, Any]:
    """Expiry metadata for the session cookie, if present."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return {}
    payload = peek_session_token(token)
    if not payload:
        return {"session_invalid": True}
    exp = int(payload.get("exp", 0))
    now = int(time.time())
    return {
        "session_expires_at": exp,
        "session_expires_in_s": max(0, exp - now),
        "session_expired": exp < now,
    }


def verify_session_token(token: str) -> dict[str, Any] | None:
    payload = peek_session_token(token)
    if not payload:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def set_session_cookie(response: Response, token: str) -> None:
    secure = os.environ.get("UCS_SESSION_SECURE", "").lower() in ("1", "true", "yes")
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=SESSION_TTL_S,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def authenticate_local(username: str, password: str) -> AuthUser | None:
    admin_user = os.environ.get("UCS_ADMIN_USER", "admin")
    admin_pass = os.environ.get("UCS_ADMIN_PASSWORD", "")
    if not admin_pass:
        return None
    if secrets.compare_digest(username, admin_user) and secrets.compare_digest(password, admin_pass):
        return AuthUser(sub=username, method="session")
    return None


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def authenticate_request(request: Request) -> AuthUser | None:
    """Return authenticated user or None."""
    api_key = os.environ.get("UCS_API_KEY")
    if api_key:
        header_key = request.headers.get("X-API-Key", "")
        bearer = _extract_bearer(request)
        if header_key and secrets.compare_digest(header_key, api_key):
            return AuthUser(sub="api-key", method="api_key")
        if bearer and secrets.compare_digest(bearer, api_key):
            return AuthUser(sub="api-key", method="api_key")

    token = request.cookies.get(SESSION_COOKIE) or _extract_bearer(request)
    if token:
        payload = verify_session_token(token)
        if payload:
            return AuthUser(sub=str(payload.get("sub", "user")), method="session")

    return None


def is_public_path(path: str, method: str) -> bool:
    if path in ("/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/status"):
        return True
    if path.startswith("/api/auth/oauth/"):
        return True
    if method in ("GET", "HEAD", "OPTIONS") and not os.environ.get("UCS_REQUIRE_AUTH_ALL"):
        return True
    return False


def require_auth_on_mutations() -> bool:
    return bool(os.environ.get("UCS_API_KEY") or os.environ.get("UCS_ADMIN_PASSWORD") or os.environ.get("UCS_OAUTH_CLIENT_ID"))


def oauth_configured() -> bool:
    return bool(os.environ.get("UCS_OAUTH_CLIENT_ID") and os.environ.get("UCS_OAUTH_ISSUER"))


def oauth_authorize_url() -> tuple[str, str]:
    """Return (authorize_url, state)."""
    issuer = os.environ.get("UCS_OAUTH_ISSUER", "").rstrip("/")
    client_id = os.environ.get("UCS_OAUTH_CLIENT_ID", "")
    redirect = os.environ.get("UCS_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/oauth/callback")
    state = secrets.token_urlsafe(24)
    _oauth_states[state] = time.time() + 600
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": os.environ.get("UCS_OAUTH_SCOPE", "openid email profile"),
        "state": state,
    })
    return f"{issuer}/authorize?{params}", state


def oauth_exchange_code(code: str, state: str) -> AuthUser:
    if state not in _oauth_states or _oauth_states[state] < time.time():
        raise HTTPException(400, "Invalid or expired OAuth state")
    del _oauth_states[state]

    issuer = os.environ.get("UCS_OAUTH_ISSUER", "").rstrip("/")
    client_id = os.environ.get("UCS_OAUTH_CLIENT_ID", "")
    client_secret = os.environ.get("UCS_OAUTH_CLIENT_SECRET", "")
    redirect = os.environ.get("UCS_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/oauth/callback")

    import httpx

    token_url = f"{issuer}/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(token_url, data=data)
        if resp.status_code != 200:
            raise HTTPException(400, f"OAuth token exchange failed: {resp.text[:200]}")
        tokens = resp.json()
        access = tokens.get("access_token", "")
        userinfo_url = os.environ.get("UCS_OAUTH_USERINFO", f"{issuer}/userinfo")
        ui = client.get(userinfo_url, headers={"Authorization": f"Bearer {access}"})
        sub = "oauth-user"
        if ui.status_code == 200:
            info = ui.json()
            sub = str(info.get("email") or info.get("sub") or sub)
    return AuthUser(sub=sub, method="oauth")
