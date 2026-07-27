"""Short-lived signed URLs for binary assets.

The problem this solves: figure PNGs, page images and chart CSVs are rendered with
`<img src>` and `<a href>`, which cannot carry an `Authorization` header. The previous
answer was to make the gateway treat *any* path ending in `/image`, `/page-image` or `/csv`
as public -- an unauthenticated read of every extracted asset in the installation, for
anyone who could guess a project and asset id.

Instead, an authenticated response embeds a URL carrying an expiry and an HMAC over the
path. The bearer token still governs who can obtain the URL; the signature governs how long
it remains usable and prevents it being edited to point at another asset.

The signature covers the path and the expiry together, so neither can be changed
independently -- bumping `exp` or swapping the asset id invalidates it.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

EXPIRY_PARAM = "exp"
SIGNATURE_PARAM = "sig"


def _digest(secret: str, path: str, expires_at: int) -> str:
    message = f"{path}:{expires_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign_path(secret: str, path: str, ttl_seconds: int) -> str:
    """Return `path` with `exp` and `sig` appended.

    `path` must be the exact request path the client will use, without a query string.
    """
    expires_at = int(time.time()) + ttl_seconds
    query = urlencode({EXPIRY_PARAM: expires_at, SIGNATURE_PARAM: _digest(secret, path, expires_at)})
    return f"{path}?{query}"


def verify_path(secret: str, path: str, expires_at: str | None, signature: str | None) -> bool:
    """True if `signature` is a live signature over `path`."""
    if not secret or not expires_at or not signature:
        return False
    try:
        expiry = int(expires_at)
    except (TypeError, ValueError):
        return False
    if expiry < time.time():
        return False
    # compare_digest: a short-circuiting comparison leaks the signature byte by byte.
    return hmac.compare_digest(_digest(secret, path, expiry), signature)
