"""Client for service-to-service calls.

Replaces two ad-hoc httpx call sites that each invented their own failure convention: the
processing service returned `{"error": "..."}` as a value (forcing every caller to remember
an `if "error" in result` check that was easy to forget), and the gateway proxy raised a
bare `HTTPException(502)`.

Here, a failed internal call raises `UpstreamServiceError`, which the centralized handler
turns into the same 502 envelope as everything else. The upstream's own message goes into
`details`, never into the client-facing message.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.errors import UpstreamServiceError
from shared.logging import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class InternalServiceClient:
    """Thin, synchronous httpx wrapper for one downstream service.

    Attaches the internal shared secret and propagates the request id so a single user
    action can be traced across service boundaries.
    """

    def __init__(
        self,
        base_url: str,
        *,
        service_name: str,
        timeout: float = 60.0,
        internal_secret: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = timeout
        self._internal_secret = internal_secret

    def _headers(self) -> dict[str, str]:
        headers = {REQUEST_ID_HEADER: get_request_id()}
        if self._internal_secret:
            headers["X-Internal-Secret"] = self._internal_secret
        return headers

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json=payload)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = httpx.request(
                method, url, headers=self._headers(), timeout=self.timeout, **kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "%s %s -> %s from %s", method, url, exc.response.status_code, self.service_name
            )
            raise UpstreamServiceError(
                f"The {self.service_name} service rejected the request",
                details={
                    "service": self.service_name,
                    "status": exc.response.status_code,
                    "body": exc.response.text[:500],
                },
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("%s %s -> unreachable (%s)", method, url, exc)
            raise UpstreamServiceError(
                f"The {self.service_name} service is unavailable",
                details={"service": self.service_name, "reason": str(exc)},
            ) from exc
