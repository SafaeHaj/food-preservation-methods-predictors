"""Extraction-service dependencies.

Identity comes from the gateway (`X-User-Id`); the project/paper access policy is the
shared one. Binding happens once here so no route re-implements either.
"""

from fastapi import Request

from shared.auth import get_current_user
from shared.config import get_common_settings
from shared.deps import make_project_dependencies
from shared.errors import AuthenticationError
from shared.signing import EXPIRY_PARAM, SIGNATURE_PARAM, verify_path

_common = get_common_settings()
_deps = make_project_dependencies(get_current_user)


def verify_signed_asset(request: Request) -> None:
    """Authenticate a binary-asset request by its URL signature.

    The gateway already verified it, but these routes must also stand alone: the signature
    is the *only* proof on this path, and a service that trusted the gateway blindly here
    would serve any asset to anything that reached it directly.
    """
    valid = verify_path(
        _common.SECRET_KEY,
        request.url.path,
        request.query_params.get(EXPIRY_PARAM),
        request.query_params.get(SIGNATURE_PARAM),
    )
    if not valid:
        raise AuthenticationError("This asset link is invalid or has expired")

require_project = _deps.require_project
require_paper = _deps.require_paper
require_project_role = _deps.require_project_role
require_paper_role = _deps.require_paper_role

#: Writing to a project's extraction workspace requires more than read access.
require_project_contributor = _deps.require_project_role("analyst")
require_paper_contributor = _deps.require_paper_role("analyst")

__all__ = [
    "get_current_user",
    "require_project",
    "require_paper",
    "require_project_role",
    "require_paper_role",
    "require_project_contributor",
    "require_paper_contributor",
    "verify_signed_asset",
]
