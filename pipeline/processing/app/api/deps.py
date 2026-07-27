"""Processing-service dependencies.

Identity comes from the gateway (`X-User-Id`); the project access policy is the shared one.
"""

from shared.auth import get_current_user
from shared.deps import make_project_dependencies

_deps = make_project_dependencies(get_current_user)

require_project = _deps.require_project
require_project_role = _deps.require_project_role

#: Curating and training against a project's data requires more than read access.
require_project_contributor = _deps.require_project_role("analyst")
require_project_reviewer = _deps.require_project_role("reviewer")

__all__ = [
    "get_current_user",
    "require_project",
    "require_project_role",
    "require_project_contributor",
    "require_project_reviewer",
]
