import base64
import hashlib
import json
import secrets
import time
from typing import Annotated, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from amcat4.config import get_settings
from amcat4.connections import http

app_auth = APIRouter(prefix="", tags=["auth"])

MIDDLECAT_URL = get_settings().middlecat_url
OIDC_URL = get_settings().oidc_url
OIDC_ID = get_settings().oidc_client_id
OIDC_SECRET = get_settings().oidc_client_secret
if OIDC_URL and not (OIDC_ID or OIDC_SECRET):
    raise ValueError("If OIDC_URL is set, ID and SECRET must also be set")

# TODO: use OIDC discovery endpoint to get the correct endpoints

IS_SECURE_CONTEXT = get_settings().host.startswith("https://")


def decode_claims(token: str) -> dict:
    _, payload, _ = token.split(".")
    decoded = base64.urlsafe_b64decode(payload + "==").decode("utf-8")
    return json.loads(decoded)


@app_auth.get("/auth/login")
async def login(
    request: Request,
    returnTo: Annotated[str | None, Query(description="URL to redirect to after login")] = None,
):
    host = get_settings().host
    api = host.rstrip("/") + "/api"
    redirect_back = returnTo or host

    # Generate PKCE
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base_urlsafe_hash(code_verifier)

    params = {
        "response_type": "code",
        "redirect_uri": f"{api}/auth/callback",
        "scope": "openid profile email",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": api,
        "state": secrets.token_urlsafe(16),
    }

    # Logic for Middlecat vs OIDC
    if OIDC_URL and not get_settings().test_mode:
        auth_url = OIDC_URL
        params["client_id"] = OIDC_ID or ""
    else:
        auth_url = f"{MIDDLECAT_URL}/authorize"
        params["client_id"] = host
        # params["refresh_mode"] = "static"

    if auth_url is None:
        raise HTTPException(500, "Server does not have an authentication provider set up")

    # Persist to encrypted session cookie
    request.session.update({"code_verifier": code_verifier, "state": params["state"], "rd": redirect_back})

    query_str = "&".join([f"{k}={v}" for k, v in params.items()])
    return RedirectResponse(f"{auth_url}?{query_str}")


@app_auth.get("/auth/callback")
async def callback(request: Request, code: str, state: str):
    if state != request.session.get("state"):
        raise HTTPException(status_code=400, detail="State mismatch")

    protocol = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    client_url = f"{protocol}://{host}"

    # Prepare Token Exchange
    if OIDC_URL and not get_settings().test_mode:
        token_url = OIDC_URL
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": OIDC_ID,
            "client_secret": OIDC_SECRET,
            "redirect_uri": f"{client_url}/auth/callback",
            "code_verifier": request.session.get("code_verifier"),
        }
    else:
        token_url = f"{MIDDLECAT_URL}/api/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": request.session.get("code_verifier"),
        }

    res = await http().post(token_url, data=data)
    tokens = res.json()

    claims = decode_claims(tokens["access_token"])

    # Create session
    request.session.update(
        {
            "id_token": tokens.get("id_token"),
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "exp": claims.get("exp"),
            "user": {"sub": claims.get("sub"), "name": claims.get("name"), "email": claims.get("email")},
        }
    )

    # Create the RedirectResponse
    response = RedirectResponse(url=request.session.get("rd") or "/")

    # Session data the client should be able to see
    value = str(claims.get("exp")) + "." + str(claims.get("email"))
    response.set_cookie(key="client_session", value=value, httponly=False, samesite="lax", secure=IS_SECURE_CONTEXT)

    return response


@app_auth.post("/auth/logout")
async def logout(
    request: Request,
    returnTo: Annotated[
        str | None, Body(max_length=100, description="Optionally, a return URL to redirect to after logout", embed=True)
    ] = None,
):

    refresh_token = request.session.get("refresh_token")
    id_token = request.session.get("id_token")
    final_destination = returnTo or get_settings().host

    # Local Session Clear
    request.session.clear()

    # Handle Logic per Provider
    if OIDC_URL and not get_settings().test_mode:
        params = {
            "post_logout_redirect_uri": final_destination,
        }
        if id_token:
            params["id_token_hint"] = id_token

        end_session_url = f"{OIDC_URL}/logout"
        encoded_params = urlencode(params)
        logout_url = f"{end_session_url}?{encoded_params}"

        # For OIDC, we tell the frontend where it needs to go next
        response = JSONResponse({"status": "logged_out", "logout_url": logout_url})
    else:
        # Middlecat 'kill_session' logic (Back-channel)
        token_endpoint = f"{MIDDLECAT_URL}/api/token"
        await http().post(
            token_endpoint,
            data={
                "grant_type": "kill_session",
                "refresh_token": refresh_token,
            },
        )
        # For Middlecat, since it's back-channel, we just tell the UI to refresh/redirect
        response = JSONResponse({"status": "logged_out", "logout_url": final_destination})

    # 4. Clear the non-httponly cookies
    response.delete_cookie("client_session")

    return response


@app_auth.post("/auth/refresh")
async def refresh_token(request: Request):
    # Check if refresh is actually needed (5-minute buffer)
    now = int(time.time())
    exp = int(request.session.get("exp", now))
    if exp - now > 5 * 60:
        return JSONResponse({"exp": exp})

    refresh_token = request.session.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token available")

    # 3. Determine Provider and Data
    if OIDC_URL and not get_settings().test_mode:
        token_url = OIDC_URL
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": OIDC_ID,
            "client_secret": OIDC_SECRET,
        }
    else:
        token_url = f"{MIDDLECAT_URL}/api/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

    # Refresh Request
    try:
        res = await http().post(token_url, data=data)
        res.raise_for_status()
        tokens = res.json()
    except httpx.HTTPStatusError:
        # If the refresh token is expired/invalid, clear session
        request.session.clear()
        raise HTTPException(status_code=401, detail="Refresh failed")

    # New Tokens
    new_access_token = tokens["access_token"]
    new_refresh_token = tokens.get("refresh_token", refresh_token)  # In case rotated
    claims = decode_claims(new_access_token)

    # Update Session
    request.session.update(
        {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "exp": claims.get("exp"),
        }
    )

    # Update session data the client should be able to see

    response = JSONResponse({"exp": claims.get("exp")})
    value = str(claims.get("exp", "")) + "." + str(claims.get("email"))
    response.set_cookie(key="client_session", value=value, httponly=False, samesite="lax", secure=IS_SECURE_CONTEXT)

    return response


def base_urlsafe_hash(verifier: str):
    sha256_hash = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).decode().replace("=", "")
