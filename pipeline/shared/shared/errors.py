"""Domain exception hierarchy shared by every service.

Services raise these; they never raise `HTTPException` and never return an error as a
value (`{"error": ...}`). Translation to an HTTP response happens in exactly one place --
`shared.error_handlers.install_exception_handlers` -- so the wire format is identical
across gateway, extraction, processing and prediction.

Each class carries a stable machine-readable `code` (what clients branch on), a
human-readable `message`, and optional structured `details`. The HTTP status is a property
of the exception type, not of the call site: that is what stops the same condition being
reported as 400 in one route and 404 in another.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for every expected (i.e. non-bug) application error.

    Subclasses fix `status_code` and `code`; call sites supply the message and details.
    Anything that escapes as a plain `Exception` is by definition unexpected and is
    reported as a 500 with a generic body.
    """

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.details = details or {}
        if code:
            self.code = code
        super().__init__(self.message)


class AuthenticationError(AppError):
    """The caller could not be identified."""

    status_code = 401
    code = "unauthenticated"


class PermissionDeniedError(AppError):
    """The caller is known but is not allowed to perform this action."""

    status_code = 403
    code = "permission_denied"


class NotFoundError(AppError):
    """The requested resource does not exist."""

    status_code = 404
    code = "not_found"

    @classmethod
    def for_resource(cls, resource: str, identifier: Any) -> NotFoundError:
        """`NotFoundError.for_resource("Paper", 12)` -> "Paper 12 not found"."""
        return cls(f"{resource} {identifier} not found",
                   details={"resource": resource, "id": identifier})


class ConflictError(AppError):
    """The action conflicts with the current state of the resource."""

    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    """The request was well-formed but its contents are not acceptable.

    Use for semantic validation the schema cannot express (an unparseable upload, a column
    mapping that references a missing header). Pydantic's own failures are translated
    separately and share this `code`.
    """

    status_code = 422
    code = "validation_error"


class BusinessRuleError(AppError):
    """A domain rule forbids this operation."""

    status_code = 400
    code = "business_rule_violation"


class UpstreamServiceError(AppError):
    """A service or provider this request depends on failed or was unreachable.

    Covers the prediction service, the LLM providers and any other outbound call. The
    upstream's own message goes in `details`, never in the client-facing `message`, so
    internal topology is not leaked.
    """

    status_code = 502
    code = "upstream_unavailable"


class ServiceUnavailableError(AppError):
    """A required capability is not installed or not ready in this deployment."""

    status_code = 503
    code = "service_unavailable"
