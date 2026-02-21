import base64
import hashlib
import json
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from amcat4.config import get_settings

app_auth = APIRouter(prefix="", tags=["auth"])

MIDDLECAT_URL = get_settings().middlecat_url
OIDC_URL = get_settings().oidc_url
OIDC_ID = get_settings().oidc_client_id
OIDC_SECRET = get_settings().oidc_client_secret
if OIDC_URL and not (OIDC_ID or OIDC_SECRET):
    raise ValueError("If OIDC_URL is set, ID and SECRET must also be set")

# TODO: use OIDC discovery endpoint to get the correct endpoints


def decode_claims(token: str) -> dict:
    _, payload, _ = token.split(".")
    decoded = base64.urlsafe_b64decode(payload + "==").decode("utf-8")
    return json.loads(decoded)


@app_auth.get("/auth/login")
async def login(request: Request, returnTo: Optional[str] = None):
    host = get_settings().host
    api = host.rstrip("/") + "/api"
    redirect_back = returnTo or host

    # Generate PKCE
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base_urlsafe_hash(code_verifier)

    # Logic for Middlecat vs OIDC
    if OIDC_URL:
        auth_url = OIDC_URL
        client_id = OIDC_ID
    else:
        auth_url = f"{MIDDLECAT_URL}/authorize"
        client_id = host

    if auth_url is None:
        raise HTTPException(500, "Server does not have an authentication provider set up")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": f"{api}/auth/callback",
        "scope": "openid profile email",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": api,
        "state": secrets.token_urlsafe(16),
    }

    # Persist to encrypted session cookie
    request.session.update({"code_verifier": code_verifier, "state": params["state"], "rd": redirect_back})

    query_str = "&".join([f"{k}={v}" for k, v in params.items()])
    return RedirectResponse(f"{auth_url}?{query_str}")


@app_auth.get("/auth/callback")
async def callback(request: Request, code: str, state: str):
    session = request.session
    if state != session.get("state"):
        raise HTTPException(status_code=400, detail="State mismatch")

    protocol = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    client_url = f"{protocol}://{host}"

    # Prepare Token Exchange
    if OIDC_URL:
        token_url = OIDC_URL
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": OIDC_ID,
            "client_secret": OIDC_SECRET,
            "redirect_uri": f"{client_url}/auth/callback",
            "code_verifier": session.get("code_verifier"),
        }
    else:
        token_url = f"{MIDDLECAT_URL}/api/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": session.get("code_verifier"),
        }

    async with httpx.AsyncClient() as client:
        res = await client.post(token_url, data=data)
        tokens = res.json()

    claims = decode_claims(tokens["access_token"])

    # Create session
    csrf_token = secrets.token_hex(32)
    session.update(
        {
            "id_token": tokens.get("id_token"),
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "csrf_token": csrf_token,
            "exp": claims.get("exp"),
            "user": {"sub": claims.get("sub"), "name": claims.get("name"), "email": claims.get("email")},
        }
    )

    is_secure_context = get_settings().host.startswith("https://")

    # Create the RedirectResponse
    response = RedirectResponse(url=request.session.get("rd") or "/")

    # Set the Non-HttpOnly CSRF cookie
    response.set_cookie(
        key="XSRF-TOKEN",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=is_secure_context,
    )

    # Set the user_email cookie (also lets UI know user is logged in)
    response.set_cookie(
        key="user_email", value=claims.get("email") or "", httponly=False, samesite="lax", secure=is_secure_context
    )

    return response


@app_auth.post("/auth/logout")
async def logout(request: Request, returnTo: Optional[str] = None):
    # CSRF Verification
    if request.headers.get("X-CSRF-TOKEN") != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    refresh_token = request.session.get("refresh_token")
    id_token = request.session.get("id_token")
    final_destination = returnTo or get_settings().host

    # Local Session Clear
    request.session.clear()

    # Handle Logic per Provider
    if OIDC_URL:
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
        async with httpx.AsyncClient() as client:
            await client.post(
                token_endpoint,
                data={
                    "grant_type": "kill_session",
                    "refresh_token": refresh_token,
                },
            )
        # For Middlecat, since it's back-channel, we just tell the UI to refresh/redirect
        response = JSONResponse({"status": "logged_out", "redirect_to": final_destination})

    # 4. Clear the non-httponly cookies
    response.delete_cookie("XSRF-TOKEN")
    response.delete_cookie("user_email")

    return response


@app_auth.post("/auth/refresh")
async def refresh_token(request: Request):
    session = request.session

    # CSRF Verification
    if request.headers.get("X-CSRF-TOKEN") != session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    # Check if refresh is actually needed (5-minute buffer)
    now = int(time.time())
    exp = session.get("exp")
    if exp and (exp - now > 5 * 60):
        return JSONResponse({"exp": exp, "access_token": session.get("access_token"), "csrf_token": session.get("csrf_token")})

    refresh_token = session.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token available")

    # 3. Determine Provider and Data
    if OIDC_URL:
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
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(token_url, data=data)
            res.raise_for_status()
            tokens = res.json()
        except httpx.HTTPStatusError:
            # If the refresh token is expired/invalid, clear session
            session.clear()
            raise HTTPException(status_code=401, detail="Refresh failed")

    # New Tokens
    new_access_token = tokens["access_token"]
    new_refresh_token = tokens.get("refresh_token", refresh_token)  # Some providers don't rotate
    claims = decode_claims(new_access_token)
    new_csrf_token = secrets.token_hex(32)

    # Update Session
    session.update(
        {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "csrf_token": new_csrf_token,
            "exp": claims.get("exp"),
        }
    )

    # 6. Return Response
    response = JSONResponse(
        {
            "exp": claims.get("exp"),
            "access_token": new_access_token,
            "csrf_token": new_csrf_token,
        }
    )

    # Update the XSRF-TOKEN cookie so the frontend has the new one
    is_secure_context = get_settings().host.startswith("https://")
    response.set_cookie(
        key="XSRF-TOKEN",
        value=new_csrf_token,
        httponly=False,
        samesite="lax",
        secure=is_secure_context,
    )

    return response


def base_urlsafe_hash(verifier: str):
    sha256_hash = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).decode().replace("=", "")
