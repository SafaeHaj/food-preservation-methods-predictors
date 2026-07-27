"""Gateway dependencies.

The gateway is the only service that verifies a JWT; everything downstream trusts the
`X-User-Id` it forwards.
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from shared.core.security import decode_token
from shared.db.database import get_db
from shared.db.models import User
from shared.deps import make_project_dependencies
from shared.errors import AuthenticationError

# auto_error=False so a missing header raises our AuthenticationError (and the standard
# error envelope) rather than FastAPI's bare 403 with a different body shape.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationError("Authentication required")

    payload = decode_token(credentials.credentials)
    if not payload:
        raise AuthenticationError("Invalid or expired token")

    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise AuthenticationError("Malformed token subject")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return user


_deps = make_project_dependencies(get_current_user)

require_project = _deps.require_project
require_project_role = _deps.require_project_role
require_job = _deps.require_job
