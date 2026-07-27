"""Gateway-origin check for the prediction service.

`processing` already sends `X-Internal-Secret` on every call it makes here (see
`shared/http.py`), but nothing on this side ever looked at it. This closes that half.

Deliberately a local copy of `shared.auth.install_internal_secret_guard` rather than an
import: this service does not install the `shared` package (its image is built from
`prediction/` alone), and pulling `shared` in for one middleware would also pull in the
platform's SQLAlchemy models, whose `experiments` table collides with this service's own.
"""

from __future__ import annotations

import hmac
import logging

from fastapi.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: Reachable without the secret: the container healthcheck must work before anything else.
_UNGUARDED_PATHS = {"/health"}


def install_internal_secret_guard(app) -> None:
    """Reject calls that cannot prove they came through the gateway, when a secret is set.

    No-op when unset, so a bare `docker compose up` still works.
    """
    secret = get_settings().internal_secret
    if not secret:
        logger.warning(
            "INTERNAL_SECRET is not set: this service accepts calls from any caller. "
            "Acceptable only when the service port is unreachable from outside the network."
        )
        return

    @app.middleware("http")
    async def _guard(request, call_next):
        if request.url.path in _UNGUARDED_PATHS:
            return await call_next(request)
        presented = request.headers.get("x-internal-secret", "")
        # compare_digest, not ==: a short-circuiting comparison leaks the secret by timing.
        if not hmac.compare_digest(presented, secret):
            logger.warning("Rejected direct call to %s (bad internal secret)", request.url.path)
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "permission_denied",
                        "message": "This service is only reachable through the gateway",
                    }
                },
            )
        return await call_next(request)
