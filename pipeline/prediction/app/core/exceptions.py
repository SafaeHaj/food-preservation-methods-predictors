"""Application exception hierarchy."""

from __future__ import annotations


class AppError(Exception):
    """Base class for application errors."""


class ConcordanceError(AppError):
    """Raised when loaded data violates the schema's concordance rules.

    Carries the violations frame so callers can report every offending row at once.
    """

    def __init__(self, violations) -> None:
        self.violations = violations
        counts = violations["rule"].value_counts().to_dict()
        super().__init__(f"{len(violations)} concordance violation(s): {counts}")


class NotImplementedYetError(AppError):
    """Raised by endpoints/services that are scaffolded but not yet wired up."""
