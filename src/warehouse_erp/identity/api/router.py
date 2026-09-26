from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from warehouse_erp.identity.api.dependencies import (
    get_current_user,
    get_identity_service,
    require_permission,
)
from warehouse_erp.identity.api.schemas import (
    Auth0Link,
    CurrentUserResponse,
    PermissionResponse,
    RoleAssignmentCreate,
    RoleAssignmentResponse,
    RoleCreate,
    RolePermissionsUpdate,
    RoleResponse,
    RoleUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from warehouse_erp.identity.application.commands import (
    AssignRole,
    CreateRole,
    CreateUser,
    LinkAuth0Identity,
    ReplaceRolePermissions,
    UpdateRole,
    UpdateUserProfile,
)
from warehouse_erp.identity.application.service import IdentityService
from warehouse_erp.identity.domain.entities import CurrentUser, UserStatus
from warehouse_erp.identity.permissions import IdentityPermission

router = APIRouter(prefix="/identity", tags=["identity"])
Current = Annotated[CurrentUser, Depends(get_current_user)]
Manager = Annotated[
    CurrentUser,
    Depends(require_permission(IdentityPermission.MANAGE_USERS)),
]
Service = Annotated[IdentityService, Depends(get_identity_service)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]
UserStatusFilter = Annotated[UserStatus | None, Query(alias="status")]


@router.get("/me", response_model=CurrentUserResponse)
def get_me(user: Current) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=user.user_id,
        subject=user.subject,
        status=user.status,
        permissions=sorted(user.permission_codes),
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    actor: Manager,
    service: Service,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
    user_status: UserStatusFilter = None,
) -> object:
    return service.list_users(actor, limit=limit, offset=offset, status=user_status)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, actor: Manager, service: Service) -> object:
    return service.create_user(actor, CreateUser(**payload.model_dump()))


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: UUID, actor: Manager, service: Service) -> object:
    return service.get_user(actor, user_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    actor: Manager,
    service: Service,
) -> object:
    current = service.get_user(actor, user_id)
    command = UpdateUserProfile(
        email=payload.email if "email" in payload.model_fields_set else current.email,
        display_name=(
            payload.display_name
            if "display_name" in payload.model_fields_set
            else current.display_name
        ),
    )
    return service.update_user_profile(actor, user_id, command)


@router.put("/users/{user_id}/auth0", response_model=UserResponse)
def link_auth0(
    user_id: UUID,
    payload: Auth0Link,
    actor: Manager,
    service: Service,
) -> object:
    return service.link_auth0_identity(actor, user_id, LinkAuth0Identity(**payload.model_dump()))


@router.post("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(user_id: UUID, actor: Manager, service: Service) -> object:
    return service.activate_user(actor, user_id)


@router.post("/users/{user_id}/suspend", response_model=UserResponse)
def suspend_user(user_id: UUID, actor: Manager, service: Service) -> object:
    return service.suspend_user(actor, user_id)


@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(actor: Manager, service: Service) -> object:
    return service.list_permissions(actor)


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(actor: Manager, service: Service, active: bool | None = None) -> object:
    return service.list_roles(actor, active=active)


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, actor: Manager, service: Service) -> object:
    return service.create_role(actor, CreateRole(**payload.model_dump()))


@router.get("/roles/{role_id}", response_model=RoleResponse)
def get_role(role_id: UUID, actor: Manager, service: Service) -> object:
    return service.get_role(actor, role_id)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    actor: Manager,
    service: Service,
) -> object:
    return service.update_role(actor, role_id, UpdateRole(**payload.model_dump()))


@router.get("/roles/{role_id}/permissions", response_model=list[PermissionResponse])
def list_role_permissions(role_id: UUID, actor: Manager, service: Service) -> object:
    return service.list_role_permissions(actor, role_id)


@router.put("/roles/{role_id}/permissions", response_model=list[PermissionResponse])
def replace_role_permissions(
    role_id: UUID,
    payload: RolePermissionsUpdate,
    actor: Manager,
    service: Service,
) -> object:
    command = ReplaceRolePermissions(permission_codes=frozenset(payload.permission_codes))
    return service.replace_role_permissions(actor, role_id, command)


@router.get(
    "/users/{user_id}/role-assignments",
    response_model=list[RoleAssignmentResponse],
)
def list_assignments(user_id: UUID, actor: Manager, service: Service) -> object:
    return service.list_assignments(actor, user_id)


@router.post(
    "/users/{user_id}/role-assignments",
    response_model=RoleAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_role(
    user_id: UUID,
    payload: RoleAssignmentCreate,
    actor: Manager,
    service: Service,
) -> object:
    return service.assign_role(actor, user_id, AssignRole(**payload.model_dump()))


@router.delete(
    "/users/{user_id}/role-assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_assignment(
    user_id: UUID,
    assignment_id: UUID,
    actor: Manager,
    service: Service,
) -> Response:
    service.revoke_assignment(actor, user_id, assignment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
