"""Authentication routes: local session login and optional OIDC OAuth."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .auth import (
    authenticate_local,
    authenticate_request,
    auth_enabled,
    clear_session_cookie,
    create_session_token,
    oauth_authorize_url,
    oauth_configured,
    oauth_exchange_code,
    session_cookie_info,
    set_session_cookie,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    user: str
    token: str | None = None


@auth_router.get("/status")
def auth_status(request: Request) -> dict:
    user = authenticate_request(request)
    info = {
        "auth_enabled": auth_enabled(),
        "oauth_configured": oauth_configured(),
        "authenticated": user is not None,
        "user": user.sub if user else None,
        "method": user.method if user else None,
    }
    info.update(session_cookie_info(request))
    return info


@auth_router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response) -> LoginResponse:
    user = authenticate_local(body.username, body.password)
    if user is None:
        raise HTTPException(401, "Invalid username or password")
    token = create_session_token(user.sub)
    set_session_cookie(response, token)
    return LoginResponse(ok=True, user=user.sub, token=token)


@auth_router.post("/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@auth_router.get("/oauth/login")
def oauth_login() -> RedirectResponse:
    if not oauth_configured():
        raise HTTPException(501, "OAuth not configured (set UCS_OAUTH_CLIENT_ID and UCS_OAUTH_ISSUER)")
    url, _state = oauth_authorize_url()
    return RedirectResponse(url)


@auth_router.get("/oauth/callback")
def oauth_callback(
    request: Request,
    response: Response,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    if error:
        raise HTTPException(400, f"OAuth error: {error}")
    if not code:
        raise HTTPException(400, "Missing authorization code")
    user = oauth_exchange_code(code, state)
    token = create_session_token(user.sub)
    set_session_cookie(response, token)
    return RedirectResponse("/settings")
