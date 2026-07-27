"""Structured logging and request correlation.

One request id follows a call from the browser through the gateway into a domain service
and back out in the error envelope, so a user-reported failure can be found in the logs of
whichever service actually raised it.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-Id"

#: Set per request by `RequestIdMiddleware`; read by the log filter and the error handlers.
#: A ContextVar (not a global) so concurrent requests in the same worker never share a value.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class _RequestIdFilter(logging.Filter):
    """Inject the current request id into every record so the format string can use it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Install a single stdout handler with a consistent, greppable format.

    Idempotent: re-configuring replaces the handlers rather than stacking them, which
    matters under uvicorn's reloader.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt=(
                "%(asctime)s %(levelname)-8s [" + service_name + "] "
                "[%(request_id)s] %(name)s: %(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own handlers; let them propagate to ours instead of duplicating.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


#: The header name, lowercased and encoded, for matching against ASGI's lowercased headers.
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("latin-1")


def install_request_id_middleware(app) -> None:
    """Adopt the inbound request id (or mint one) and echo it on the response.

    A pure-ASGI middleware, deliberately not `@app.middleware("http")`
    (Starlette `BaseHTTPMiddleware`): that wrapper relays every response body through an
    internal memory stream, which buffers Server-Sent Events and stalls the job-progress
    stream at `/jobs/{id}/events` — a completed job never reaches the browser, so the UI
    sits on "running". This wrapper only reads the request headers and appends one response
    header, so `StreamingResponse` passes through frame by frame. Setting the request-id
    ContextVar in the same task that runs the app also makes it visible to the error handlers
    more reliably than the BaseHTTPMiddleware task hand-off did.
    """

    class _RequestIdMiddleware:
        def __init__(self, asgi_app) -> None:
            self._app = asgi_app

        async def __call__(self, scope, receive, send) -> None:
            if scope["type"] != "http":
                await self._app(scope, receive, send)
                return

            incoming = None
            for key, value in scope.get("headers", []):
                if key == _REQUEST_ID_HEADER_BYTES:
                    incoming = value.decode("latin-1")
                    break
            request_id = incoming or new_request_id()
            set_request_id(request_id)

            async def send_with_request_id(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((_REQUEST_ID_HEADER_BYTES, request_id.encode("latin-1")))
                    message = {**message, "headers": headers}
                await send(message)

            await self._app(scope, receive, send_with_request_id)

    app.add_middleware(_RequestIdMiddleware)
