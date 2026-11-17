"""Bearer credential authentication and tenant role authorization."""

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal

from flask import abort

from demoapp import db

logger = logging.getLogger(__name__)

BEARER_PREFIX = "Bearer "
Role = Literal["admin", "member"]


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity bound to a single tenant and role."""

    user_id: int
    tenant_id: str
    role: Role


def authenticate_request(db_path: str, auth_header: str | None) -> Principal:
    """Resolve an HTTP Authorization bearer header to a tenant Principal.

    Args:
        db_path: Path to the SQLite database file.
        auth_header: Raw HTTP Authorization header value, if present.

    Returns:
        The authenticated Principal for the bearer credential.
    """
    if not auth_header or not auth_header.startswith(BEARER_PREFIX):
        abort(401)
    raw_credential = auth_header.removeprefix(BEARER_PREFIX).strip()
    if not raw_credential:
        abort(401)
    digest = hashlib.sha256(raw_credential.encode("utf-8")).hexdigest()
    row = db.get_principal_row_by_token_hash(db_path, digest)
    if row is None:
        logger.warning("Rejected unrecognized bearer credential")
        abort(401)
    user_id, tenant_id, role_value = row
    if role_value not in ("admin", "member"):
        abort(401)
    role: Role = "admin" if role_value == "admin" else "member"
    return Principal(user_id=user_id, tenant_id=tenant_id, role=role)


def require_admin(principal: Principal) -> None:
    """Abort with 403 Forbidden unless the principal holds the admin role."""
    if principal.role != "admin":
        logger.warning("Denied non-admin user %s in tenant %s", principal.user_id, principal.tenant_id)
        abort(403)
