"""Reverse proxy: route `/api/*` to the domain service that owns it.

The JWT is verified here, exactly once, and the caller's id is forwarded as `X-User-Id`.
Nothing downstream re-verifies a token.

Binary assets (`/image`, `/page-image`, `/csv`) are the one class of request the SPA cannot
send an `Authorization` header with, because they are fetched by `<img src>` / `<a href>`.
They are authenticated by a short-lived HMAC signature minted into the asset payload by the
extraction service (see `shared.signing`) rather than -- as previously -- by exempting every
path with those suffixes from authentication entirely.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from shared.config import get_common_settings, get_gateway_settings
from shared.core.security import decode_token
from shared.db.database import get_db
from shared.db.models import User
from shared.errors import AuthenticationError, NotFoundError, UpstreamServiceError
from shared.logging import REQUEST_ID_HEADER, get_request_id
from shared.signing import EXPIRY_PARAM, SIGNATURE_PARAM, verify_path

logger = logging.getLogger(__name__)
router = APIRouter()

_settings = get_gateway_settings()
_common = get_common_settings()

#: Path roots owned by each domain service. A path matching neither is a 404 here rather
#: than being forwarded somewhere that would also not understand it.
#:
#: Processing owns no bare roots any more. It used to own ten -- studies, observations,
#: trajectories, thresholds and the rest -- backing a second scientific hierarchy that has
#: since been deleted; everything it serves now hangs off a project.
PROCESSING_ROOTS: frozenset[str] = frozenset()
EXTRACTION_ROOTS = frozenset({"schema", "chart2table", "evidence"})
EXTRACTION_PROJECT_SUBS = frozenset({
    "papers", "assets", "experiments", "ingredients", "indicators",
})
PROCESSING_PROJECT_SUBS = frozenset({"dataset", "prediction"})

#: Requests whose authentication is a URL signature rather than a bearer token.
SIGNED_ASSET_SUFFIXES = ("/image", "/page-image", "/csv", "/thumbnail")

_HOP_BY_HOP = frozenset({
    "host", "content-length", "connection", "keep-alive", "transfer-encoding",
    "upgrade", "proxy-authenticate", "proxy-authorization", "te", "trailer",
})

#: Never forwarded from the client. The bearer token stops at the gateway, and the trust
#: headers are the gateway's own assertions -- a client that could set them could
#: impersonate any user on any signature-authenticated path.
_CLIENT_STRIPPED = frozenset({"authorization", "x-user-id", "x-internal-secret"})


def _target_for(path: str) -> str | None:
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return None

    root = segments[0]
    if root in PROCESSING_ROOTS:
        return _settings.PROCESSING_SERVICE_URL
    if root in EXTRACTION_ROOTS:
        return _settings.EXTRACTION_SERVICE_URL

    if root == "projects" and len(segments) >= 3:
        sub = segments[2]
        if sub in PROCESSING_PROJECT_SUBS:
            return _settings.PROCESSING_SERVICE_URL
        if sub in EXTRACTION_PROJECT_SUBS:
            return _settings.EXTRACTION_SERVICE_URL
    return None


def _is_signed_asset(path: str) -> bool:
    return path.endswith(SIGNED_ASSET_SUFFIXES)


def _resolve_bearer_user(request: Request, db: Session) -> int | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    payload = decode_token(header.split(" ", 1)[1].strip())
    if not payload:
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user.id if user and user.is_active else None


def _authenticate(path: str, request: Request, db: Session) -> int | None:
    """Return the caller's user id, or None for a validly-signed asset request.

    Raises `AuthenticationError` when neither form of proof is present.
    """
    user_id = _resolve_bearer_user(request, db)
    if user_id is not None:
        return user_id

    if _is_signed_asset(path):
        valid = verify_path(
            _common.SECRET_KEY,
            f"/api/{path}",
            request.query_params.get(EXPIRY_PARAM),
            request.query_params.get(SIGNATURE_PARAM),
        )
        if valid:
            # No identity to forward: the signature already proves an authorized caller
            # obtained this exact URL. The asset route accepts that in place of X-User-Id.
            return None
        raise AuthenticationError("This asset link is invalid or has expired")

    raise AuthenticationError("Authentication required")


@router.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy(path: str, request: Request, db: Session = Depends(get_db)) -> Response:
    target = _target_for(path)
    if target is None:
        raise NotFoundError(f"No route for /api/{path}")

    user_id = _authenticate(path, request, db)

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP and key.lower() not in _CLIENT_STRIPPED
    }
    if user_id is not None:
        headers["X-User-Id"] = str(user_id)
    if _common.INTERNAL_SECRET:
        headers["X-Internal-Secret"] = _common.INTERNAL_SECRET
    headers[REQUEST_ID_HEADER] = get_request_id()

    body = await request.body()
    url = f"{target.rstrip('/')}/api/{path}"

    try:
        async with httpx.AsyncClient(
            timeout=_settings.PROXY_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            upstream = await client.request(
                request.method, url,
                params=dict(request.query_params), content=body, headers=headers,
            )
    except httpx.HTTPError as exc:
        logger.error("Proxy to %s failed: %s", url, exc)
        raise UpstreamServiceError(
            "The service handling this request is unavailable",
            details={"reason": str(exc)},
        ) from exc

    # Pass the response through verbatim: blob downloads must keep Content-Disposition and
    # asset endpoints must keep their Content-Type.
    passthrough = {
        key: value for key, value in upstream.headers.items() if key.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=passthrough,
        media_type=upstream.headers.get("content-type"),
    )
