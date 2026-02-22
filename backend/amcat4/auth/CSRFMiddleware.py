import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from amcat4.config import get_settings

is_secure_context = get_settings().host.startswith("https://")


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cookie_token = request.cookies.get("CSRF-TOKEN")

        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            header_token = request.headers.get("X-CSRF-TOKEN")

            if not cookie_token or not header_token or cookie_token != header_token:
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

        response = await call_next(request)

        if not cookie_token:
            response.set_cookie(
                key="CSRF-TOKEN", value=secrets.token_urlsafe(32), httponly=False, samesite="lax", secure=is_secure_context
            )

        return response
