import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from warehouse_erp.shared.errors import ValidationError


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class UserStatus(StrEnum):
    INVITED = "INVITED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ScopeType(StrEnum):
    GLOBAL = "GLOBAL"
    COMPANY = "COMPANY"
    WAREHOUSE = "WAREHOUSE"


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if len(normalized) > 320 or "@" not in normalized:
        raise ValidationError("email is invalid")
    return normalized


def normalize_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 255:
        raise ValidationError("display_name must not exceed 255 characters")
    return normalized


def normalize_person_name(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 100:
        raise ValidationError(f"{field} must not exceed 100 characters")
    return normalized


def normalize_role_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", normalized):
        raise ValidationError(
            "role code must contain 2-64 uppercase letters, digits, or underscores"
        )
    return normalized


def normalize_permission_code(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or not re.fullmatch(r"[a-z][a-z0-9_.]{2,127}", normalized):
        raise ValidationError("permission code is invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    """An external identity proven by a validated access token."""

    subject: str
    scopes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValidationError("authenticated subject must not be empty")


@dataclass(slots=True)
class User:
    status: UserStatus
    id: UUID = field(default_factory=uuid4)
    auth0_subject: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=utc_now)
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        self.email = normalize_email(self.email)
        self.first_name = normalize_person_name(self.first_name, "first_name")
        self.last_name = normalize_person_name(self.last_name, "last_name")
        self.display_name = self._display_name(self.display_name)
        if self.auth0_subject is not None:
            self.auth0_subject = self.auth0_subject.strip()
            if not self.auth0_subject:
                raise ValidationError("auth0_subject must not be empty")

    def activate(self, actor_id: UUID) -> None:
        self.status = UserStatus.ACTIVE
        self._touch(actor_id)

    def suspend(self, actor_id: UUID) -> None:
        self.status = UserStatus.SUSPENDED
        self._touch(actor_id)

    def link_auth0(self, subject: str, actor_id: UUID) -> None:
        normalized = subject.strip()
        if not normalized:
            raise ValidationError("auth0_subject must not be empty")
        if self.auth0_subject is not None and self.auth0_subject != normalized:
            raise ValidationError("user is already linked to another Auth0 identity")
        self.auth0_subject = normalized
        self._touch(actor_id)

    def update_profile(
        self,
        *,
        email: str | None,
        first_name: str | None,
        last_name: str | None,
        display_name: str | None,
        actor_id: UUID,
    ) -> None:
        self.email = normalize_email(email)
        self.first_name = normalize_person_name(first_name, "first_name")
        self.last_name = normalize_person_name(last_name, "last_name")
        self.display_name = self._display_name(display_name)
        self._touch(actor_id)

    def _display_name(self, fallback: str | None) -> str | None:
        full_name = " ".join(part for part in (self.first_name, self.last_name) if part)
        return normalize_display_name(full_name or fallback)

    def _touch(self, actor_id: UUID) -> None:
        self.updated_at = utc_now()
        self.updated_by = actor_id


@dataclass(frozen=True, slots=True)
class Permission:
    code: str
    description: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_permission_code(self.code))
        if not self.description.strip():
            raise ValidationError("permission description must not be empty")


@dataclass(slots=True)
class Role:
    code: str
    name: str
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    active: bool = True
    system_role: bool = False
    created_at: datetime = field(default_factory=utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=utc_now)
    updated_by: UUID | None = None

    def __post_init__(self) -> None:
        self.code = normalize_role_code(self.code)
        self.name = self.name.strip()
        if not self.name or len(self.name) > 255:
            raise ValidationError("role name must contain 1-255 characters")

    def update(
        self,
        *,
        name: str,
        description: str | None,
        active: bool,
        actor_id: UUID,
    ) -> None:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 255:
            raise ValidationError("role name must contain 1-255 characters")
        self.name = normalized_name
        self.description = description
        self.active = active
        self.updated_at = utc_now()
        self.updated_by = actor_id


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    user_id: UUID
    role_id: UUID
    scope_type: ScopeType = ScopeType.GLOBAL
    scope_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)
    created_by: UUID | None = None

    def __post_init__(self) -> None:
        if self.scope_type is ScopeType.GLOBAL and self.scope_id is not None:
            raise ValidationError("GLOBAL role assignment must not have scope_id")
        if self.scope_type is not ScopeType.GLOBAL and self.scope_id is None:
            raise ValidationError("scoped role assignment requires scope_id")

    @property
    def scope_key(self) -> str:
        return "GLOBAL" if self.scope_id is None else str(self.scope_id)


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    permission_code: str
    role_id: UUID
    scope_type: ScopeType
    scope_id: UUID | None


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: UUID
    subject: str
    status: UserStatus
    grants: tuple[PermissionGrant, ...] = ()

    @property
    def permission_codes(self) -> frozenset[str]:
        return frozenset(grant.permission_code for grant in self.grants)

    def has_permission(
        self,
        permission_code: str,
        *,
        scope_type: ScopeType = ScopeType.GLOBAL,
        scope_id: UUID | None = None,
    ) -> bool:
        code = normalize_permission_code(permission_code)
        for grant in self.grants:
            if grant.permission_code != code:
                continue
            if grant.scope_type is ScopeType.GLOBAL:
                return True
            if grant.scope_type is scope_type and grant.scope_id == scope_id:
                return True
        return False
