"""Basic-auth gate for the deployed dashboard.

The app can end up on a public URL once deployed (e.g. Render), and it
holds company-internal safety documents plus settings that can send
mail or change the tracked-law list, so it needs at least a login
prompt. Set DASHBOARD_USERNAME and DASHBOARD_PASSWORD (env vars) to
turn it on; leave them empty for local development to skip auth.
"""

import base64
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings

_UNPROTECTED_PATHS = {"/api/health"}


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.DASHBOARD_USERNAME or not settings.DASHBOARD_PASSWORD:
            return await call_next(request)
        if request.url.path in _UNPROTECTED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, _, password = decoded.partition(":")
            except Exception:
                username, password = "", ""
            if hmac.compare_digest(username, settings.DASHBOARD_USERNAME) and hmac.compare_digest(
                password, settings.DASHBOARD_PASSWORD
            ):
                return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Safety Law Tracker"'},
        )
