from dataclasses import dataclass
from uuid import UUID

from warehouse_erp.identity.domain.entities import ScopeType


@dataclass(frozen=True, slots=True)
class CreateUser:
    email: str
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateUserProfile:
    email: str | None
    display_name: str | None


@dataclass(frozen=True, slots=True)
class LinkAuth0Identity:
    auth0_subject: str


@dataclass(frozen=True, slots=True)
class CreateRole:
    code: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateRole:
    name: str
    description: str | None
    active: bool


@dataclass(frozen=True, slots=True)
class ReplaceRolePermissions:
    permission_codes: frozenset[str]


@dataclass(frozen=True, slots=True)
class AssignRole:
    role_id: UUID
    scope_type: ScopeType = ScopeType.GLOBAL
    scope_id: UUID | None = None
