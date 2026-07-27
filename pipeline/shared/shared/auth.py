"""Identity for the domain services (extraction / processing).

Authentication happens exactly once, at the gateway: it validates the JWT and forwards the
caller's id as ``X-User-Id``. Domain services do not re-verify tokens -- they trust the
gateway and resolve that header to a `User`.

Security note: these services must never be published. Only the gateway is exposed; the
service ports stay on the internal compose network, and `INTERNAL_SECRET` (when set) proves
a request actually came through the gateway.
"""

import hmac
import logging

from fastapi import Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from shared.config import get_common_settings
from shared.db.database import get_db
from shared.db.models import User
from shared.errors import AuthenticationError
from shared.logging import get_request_id

logger = logging.getLogger(__name__)

#: Reachable without the internal secret: liveness probes must work before anything else.
_UNGUARDED_PATHS = {"/health"}


def install_internal_secret_guard(app) -> None:
    """Reject anything that cannot prove it came from the gateway, when a secret is set.

    Defence in depth: the domain services trust `X-User-Id` blindly, so if they were ever
    reachable directly, that header would be an impersonation primitive. No-op when unset,
    so a bare `docker compose up` still works.
    """
    secret = get_common_settings().INTERNAL_SECRET
    if not secret:
        logger.warning(
            "INTERNAL_SECRET is not set: this service trusts X-User-Id from any caller. "
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
                        "request_id": get_request_id(),
                    }
                },
            )
        return await call_next(request)


def get_current_user(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the gateway-injected identity to a `User`."""
    if not x_user_id:
        raise AuthenticationError("Missing gateway identity (X-User-Id)")
    try:
        user_id = int(x_user_id)
    except (TypeError, ValueError):
        raise AuthenticationError("Malformed gateway identity")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return user
