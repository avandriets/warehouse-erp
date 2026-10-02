from uuid import UUID

from warehouse_erp.identity.application.commands import (
    AssignRole,
    CreateRole,
    CreateUser,
    LinkAuth0Identity,
    ReplaceRolePermissions,
    UpdateRole,
    UpdateUserProfile,
)
from warehouse_erp.identity.domain.entities import (
    AuthenticatedIdentity,
    CurrentUser,
    Permission,
    Role,
    RoleAssignment,
    ScopeType,
    User,
    UserStatus,
    normalize_email,
    normalize_permission_code,
    normalize_role_code,
)
from warehouse_erp.identity.domain.repositories import IdentityUnitOfWork
from warehouse_erp.identity.permissions import IdentityPermission
from warehouse_erp.shared.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)


class IdentityService:
    def __init__(self, unit_of_work: IdentityUnitOfWork) -> None:
        self.uow = unit_of_work

    def resolve_current_user(self, identity: AuthenticatedIdentity) -> CurrentUser:
        user = self.uow.identity.get_user_by_subject(identity.subject)
        if user is None:
            user = User(
                auth0_subject=identity.subject,
                status=UserStatus.PENDING_APPROVAL,
            )
            self.uow.identity.add_user(user)
            self.uow.commit()
        grants = tuple(self.uow.identity.list_grants(user.id))
        return CurrentUser(
            user_id=user.id,
            subject=identity.subject,
            status=user.status,
            grants=grants,
        )

    def get_user(self, actor: CurrentUser, user_id: UUID) -> User:
        self._require_manage_users(actor)
        return self._get_user(user_id)

    def list_users(
        self,
        actor: CurrentUser,
        *,
        limit: int,
        offset: int,
        status: UserStatus | None,
        q: str | None = None,
    ) -> tuple[list[User], int]:
        self._require_manage_users(actor)
        return self.uow.identity.list_users(
            limit=limit, offset=offset, status=status, q=(q or "").strip() or None
        )

    def create_user(self, actor: CurrentUser, command: CreateUser) -> User:
        self._require_manage_users(actor)
        email = normalize_email(command.email)
        if email is None:
            raise ValidationError("email is required")
        if self.uow.identity.get_user_by_email(email):
            raise ConflictError("User with this email already exists")
        user = User(
            email=email,
            first_name=command.first_name,
            last_name=command.last_name,
            display_name=command.display_name,
            status=UserStatus.INVITED,
            created_by=actor.user_id,
            updated_by=actor.user_id,
        )
        self.uow.identity.add_user(user)
        self.uow.commit()
        return user

    def update_user_profile(
        self, actor: CurrentUser, user_id: UUID, command: UpdateUserProfile
    ) -> User:
        self._require_manage_users(actor)
        user = self._get_user(user_id)
        email = normalize_email(command.email)
        if email:
            duplicate = self.uow.identity.get_user_by_email(email)
            if duplicate and duplicate.id != user.id:
                raise ConflictError("User with this email already exists")
        user.update_profile(
            email=email,
            first_name=command.first_name,
            last_name=command.last_name,
            display_name=command.display_name,
            actor_id=actor.user_id,
        )
        self.uow.identity.save_user(user)
        self.uow.commit()
        return user

    def activate_user(self, actor: CurrentUser, user_id: UUID) -> User:
        self._require_manage_users(actor)
        user = self._get_user(user_id)
        if not user.auth0_subject:
            raise ValidationError("User must be linked to Auth0 before activation")
        user.activate(actor.user_id)
        self.uow.identity.save_user(user)
        self.uow.commit()
        return user

    def suspend_user(self, actor: CurrentUser, user_id: UUID) -> User:
        self._require_manage_users(actor)
        if actor.user_id == user_id:
            raise ValidationError("Users cannot suspend themselves")
        user = self._get_user(user_id)
        user.suspend(actor.user_id)
        self.uow.identity.save_user(user)
        self.uow.commit()
        return user

    def link_auth0_identity(
        self, actor: CurrentUser, user_id: UUID, command: LinkAuth0Identity
    ) -> User:
        self._require_manage_users(actor)
        duplicate = self.uow.identity.get_user_by_subject(command.auth0_subject.strip())
        if duplicate and duplicate.id != user_id:
            raise ConflictError("Auth0 identity is already linked to another user")
        user = self._get_user(user_id)
        user.link_auth0(command.auth0_subject, actor.user_id)
        self.uow.identity.save_user(user)
        self.uow.commit()
        return user

    def list_permissions(self, actor: CurrentUser) -> list[Permission]:
        self._require_manage_users(actor)
        return self.uow.identity.list_permissions()

    def list_roles(
        self, actor: CurrentUser, *, active: bool | None, q: str | None = None
    ) -> list[Role]:
        self._require_manage_users(actor)
        return self.uow.identity.list_roles(active=active, q=(q or "").strip() or None)

    def get_role(self, actor: CurrentUser, role_id: UUID) -> Role:
        self._require_manage_users(actor)
        return self._get_role(role_id)

    def create_role(self, actor: CurrentUser, command: CreateRole) -> Role:
        self._require_manage_users(actor)
        code = normalize_role_code(command.code)
        if self.uow.identity.get_role_by_code(code):
            raise ConflictError(f"Role with code {code} already exists")
        role = Role(
            code=code,
            name=command.name,
            description=command.description,
            created_by=actor.user_id,
            updated_by=actor.user_id,
        )
        self.uow.identity.add_role(role)
        self.uow.commit()
        return role

    def update_role(self, actor: CurrentUser, role_id: UUID, command: UpdateRole) -> Role:
        self._require_manage_users(actor)
        role = self._get_role(role_id)
        role.update(
            name=command.name,
            description=command.description,
            active=command.active,
            actor_id=actor.user_id,
        )
        self.uow.identity.save_role(role)
        self.uow.commit()
        return role

    def replace_role_permissions(
        self,
        actor: CurrentUser,
        role_id: UUID,
        command: ReplaceRolePermissions,
    ) -> list[Permission]:
        self._require_manage_users(actor)
        self._get_role(role_id)
        codes = {normalize_permission_code(code) for code in command.permission_codes}
        permissions = self.uow.identity.get_permissions_by_codes(codes)
        found_codes = {permission.code for permission in permissions}
        missing = codes - found_codes
        if missing:
            raise ValidationError(f"Unknown permissions: {', '.join(sorted(missing))}")
        self.uow.identity.replace_role_permissions(
            role_id, {permission.id for permission in permissions}
        )
        self.uow.commit()
        return self.uow.identity.list_role_permissions(role_id)

    def list_role_permissions(self, actor: CurrentUser, role_id: UUID) -> list[Permission]:
        self._require_manage_users(actor)
        self._get_role(role_id)
        return self.uow.identity.list_role_permissions(role_id)

    def assign_role(self, actor: CurrentUser, user_id: UUID, command: AssignRole) -> RoleAssignment:
        self._require_manage_users(actor)
        self._get_user(user_id)
        role = self._get_role(command.role_id)
        if not role.active:
            raise ValidationError("Cannot assign an inactive role")
        assignment = RoleAssignment(
            user_id=user_id,
            role_id=command.role_id,
            scope_type=command.scope_type,
            scope_id=command.scope_id,
            created_by=actor.user_id,
        )
        duplicate = self.uow.identity.find_assignment(
            user_id=user_id,
            role_id=command.role_id,
            scope_type=command.scope_type.value,
            scope_key=assignment.scope_key,
        )
        if duplicate:
            return duplicate
        self.uow.identity.add_assignment(assignment)
        self.uow.commit()
        return assignment

    def list_assignments(self, actor: CurrentUser, user_id: UUID) -> list[RoleAssignment]:
        self._require_manage_users(actor)
        self._get_user(user_id)
        return self.uow.identity.list_assignments(user_id)

    def revoke_assignment(self, actor: CurrentUser, user_id: UUID, assignment_id: UUID) -> None:
        self._require_manage_users(actor)
        assignment = self.uow.identity.get_assignment(assignment_id)
        if not assignment or assignment.user_id != user_id:
            raise NotFoundError("Role assignment not found")
        self.uow.identity.remove_assignment(assignment)
        self.uow.commit()

    def bootstrap_admin(
        self,
        *,
        auth0_subject: str,
        email: str | None,
        display_name: str | None,
    ) -> User:
        admin_role = self.uow.identity.get_role_by_code("ADMIN")
        if not admin_role:
            raise NotFoundError("ADMIN role is not initialized; run database migrations")
        user = self.uow.identity.get_user_by_subject(auth0_subject)
        if user is None:
            user = User(
                auth0_subject=auth0_subject,
                email=email,
                display_name=display_name,
                status=UserStatus.ACTIVE,
            )
            self.uow.identity.add_user(user)
            self.uow.commit()
        else:
            if user.status is not UserStatus.ACTIVE:
                user.activate(user.id)
            if email is not None or display_name is not None:
                user.update_profile(
                    email=email if email is not None else user.email,
                    display_name=(display_name if display_name is not None else user.display_name),
                    actor_id=user.id,
                )
            self.uow.identity.save_user(user)
            self.uow.commit()

        assignment = RoleAssignment(
            user_id=user.id,
            role_id=admin_role.id,
            scope_type=ScopeType.GLOBAL,
            created_by=user.id,
        )
        existing = self.uow.identity.find_assignment(
            user_id=user.id,
            role_id=admin_role.id,
            scope_type=ScopeType.GLOBAL.value,
            scope_key=assignment.scope_key,
        )
        if not existing:
            self.uow.identity.add_assignment(assignment)
            self.uow.commit()
        return user

    def _get_user(self, user_id: UUID) -> User:
        user = self.uow.identity.get_user(user_id)
        if not user:
            raise NotFoundError("User not found")
        return user

    def _get_role(self, role_id: UUID) -> Role:
        role = self.uow.identity.get_role(role_id)
        if not role:
            raise NotFoundError("Role not found")
        return role

    @staticmethod
    def _require_manage_users(actor: CurrentUser) -> None:
        if actor.status is not UserStatus.ACTIVE or not actor.has_permission(
            IdentityPermission.MANAGE_USERS
        ):
            raise ForbiddenError(f"{IdentityPermission.MANAGE_USERS} permission is required")
