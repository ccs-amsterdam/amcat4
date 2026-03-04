import base64
import hashlib
import json
from typing import Annotated

from amcat4.auth.oauth import oauth_callback, oauth_login, oauth_logout, oauth_refresh
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse

app_auth = APIRouter(prefix="", tags=["auth"])


def decode_claims(token: str) -> dict:
    _, payload, _ = token.split(".")
    decoded = base64.urlsafe_b64decode(payload + "==").decode("utf-8")
    return json.loads(decoded)


@app_auth.get("/auth/login")
async def login(
    request: Request,
    returnTo: Annotated[str | None, Query(description="URL to redirect to after login")] = None,
):
    try:
        return await oauth_login(request, returnTo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app_auth.get("/auth/callback")
async def callback(request: Request, code: str, state: str):
    try:
        return await oauth_callback(request, code, state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app_auth.post("/auth/logout")
async def logout(
    request: Request,
    returnTo: Annotated[
        str | None, Body(max_length=100, description="Optionally, a return URL to redirect to after logout", embed=True)
    ] = None,
):
    try:
        return await oauth_logout(request, returnTo)
    except Exception as e:
        request.session.clear()
        response = JSONResponse(status_code=500, content={"error": str(e)})
        response.delete_cookie("client_session")
        return response


@app_auth.post("/auth/refresh")
async def refresh_token(request: Request):
    try:
        return await oauth_refresh(request)
    except Exception as e:
        request.session.clear()
        response = JSONResponse(status_code=500, content={"error": str(e)})
        response.delete_cookie("client_session")
        return response


def base_urlsafe_hash(verifier: str):
    sha256_hash = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).decode().replace("=", "")
