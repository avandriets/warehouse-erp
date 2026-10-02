from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from warehouse_erp.identity.domain.entities import ScopeType, UserStatus


class CurrentUserResponse(BaseModel):
    user_id: UUID
    subject: str
    status: UserStatus
    permissions: list[str]


class UserCreate(BaseModel):
    email: str
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None


class Auth0Link(BaseModel):
    auth0_subject: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    auth0_subject: str | None
    email: str | None
    first_name: str | None
    last_name: str | None
    display_name: str | None
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    description: str


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str | None = None


class RoleUpdate(BaseModel):
    name: str
    description: str | None = None
    active: bool = True


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    active: bool
    system_role: bool
    created_at: datetime
    updated_at: datetime


class RolePermissionsUpdate(BaseModel):
    permission_codes: set[str] = Field(default_factory=set)


class RoleAssignmentCreate(BaseModel):
    role_id: UUID
    scope_type: ScopeType = ScopeType.GLOBAL
    scope_id: UUID | None = None


class RoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role_id: UUID
    scope_type: ScopeType
    scope_id: UUID | None
    created_at: datetime
