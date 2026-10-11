from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warehouse_erp.identity.domain.entities import (
    Permission,
    PermissionGrant,
    Role,
    RoleAssignment,
    ScopeType,
    User,
    UserStatus,
)
from warehouse_erp.identity.infrastructure.models import (
    PermissionModel,
    RoleAssignmentModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from warehouse_erp.shared.errors import ConflictError


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _user(model: UserModel) -> User:
    return User(
        id=UUID(model.id),
        default_warehouse_id=UUID(model.default_warehouse_id)
        if model.default_warehouse_id
        else None,
        auth0_subject=model.auth0_subject,
        email=model.email,
        first_name=model.first_name,
        last_name=model.last_name,
        display_name=model.display_name,
        status=UserStatus(model.status),
        created_at=_utc(model.created_at),
        created_by=UUID(model.created_by) if model.created_by else None,
        updated_at=_utc(model.updated_at),
        updated_by=UUID(model.updated_by) if model.updated_by else None,
    )


def _role(model: RoleModel) -> Role:
    return Role(
        id=UUID(model.id),
        code=model.code,
        name=model.name,
        description=model.description,
        active=model.active,
        system_role=model.system_role,
        created_at=_utc(model.created_at),
        created_by=UUID(model.created_by) if model.created_by else None,
        updated_at=_utc(model.updated_at),
        updated_by=UUID(model.updated_by) if model.updated_by else None,
    )


def _permission(model: PermissionModel) -> Permission:
    return Permission(id=UUID(model.id), code=model.code, description=model.description)


def _assignment(model: RoleAssignmentModel) -> RoleAssignment:
    return RoleAssignment(
        id=UUID(model.id),
        user_id=UUID(model.user_id),
        role_id=UUID(model.role_id),
        scope_type=ScopeType(model.scope_type),
        scope_id=UUID(model.scope_id) if model.scope_id else None,
        created_at=_utc(model.created_at),
        created_by=UUID(model.created_by) if model.created_by else None,
    )


class SqlAlchemyIdentityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active_warehouse_exists(self, warehouse_id: UUID, *, lock: bool = False) -> bool:
        from warehouse_erp.warehouse.infrastructure.models import WarehouseModel

        query = select(WarehouseModel.id).where(
            WarehouseModel.id == str(warehouse_id), WarehouseModel.active.is_(True)
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query) is not None

    def get_user_for_update(self, user_id: UUID) -> User | None:
        model = self.session.scalar(
            select(UserModel)
            .where(UserModel.id == str(user_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return _user(model) if model else None

    def add_user(self, user: User) -> None:
        self.session.add(self._user_model(user))

    def save_user(self, user: User) -> None:
        self.session.merge(self._user_model(user))

    def get_user(self, user_id: UUID) -> User | None:
        model = self.session.get(UserModel, str(user_id))
        return _user(model) if model else None

    def get_user_by_subject(self, subject: str) -> User | None:
        model = self.session.scalar(
            select(UserModel).where(UserModel.auth0_subject == subject.strip())
        )
        return _user(model) if model else None

    def get_user_by_email(self, email: str) -> User | None:
        model = self.session.scalar(select(UserModel).where(UserModel.email == email.lower()))
        return _user(model) if model else None

    def list_users(
        self, *, limit: int, offset: int, status: UserStatus | None, q: str | None = None
    ) -> tuple[list[User], int]:
        filters = []
        if status is not None:
            filters.append(UserModel.status == status.value)
        if q:
            filters.append(
                or_(
                    UserModel.first_name.icontains(q, autoescape=True),
                    UserModel.last_name.icontains(q, autoescape=True),
                    UserModel.display_name.icontains(q, autoescape=True),
                    UserModel.email.icontains(q, autoescape=True),
                )
            )
        statement = select(UserModel).where(*filters).order_by(UserModel.created_at, UserModel.id)
        count = select(func.count()).select_from(UserModel).where(*filters)
        total = self.session.scalar(count) or 0
        rows = self.session.scalars(statement.offset(offset).limit(limit))
        return [_user(row) for row in rows], total

    def add_role(self, role: Role) -> None:
        self.session.add(self._role_model(role))

    def save_role(self, role: Role) -> None:
        self.session.merge(self._role_model(role))

    def get_role(self, role_id: UUID) -> Role | None:
        model = self.session.get(RoleModel, str(role_id))
        return _role(model) if model else None

    def get_role_by_code(self, code: str) -> Role | None:
        model = self.session.scalar(select(RoleModel).where(RoleModel.code == code.upper()))
        return _role(model) if model else None

    def list_roles(self, *, active: bool | None, q: str | None = None) -> list[Role]:
        statement = select(RoleModel).order_by(RoleModel.name, RoleModel.id)
        if active is not None:
            statement = statement.where(RoleModel.active == active)
        if q:
            statement = statement.where(
                or_(
                    RoleModel.name.icontains(q, autoescape=True),
                    RoleModel.code.icontains(q, autoescape=True),
                )
            )
        return [_role(row) for row in self.session.scalars(statement)]

    def get_permissions_by_codes(self, codes: set[str]) -> list[Permission]:
        if not codes:
            return []
        rows = self.session.scalars(select(PermissionModel).where(PermissionModel.code.in_(codes)))
        return [_permission(row) for row in rows]

    def list_permissions(self) -> list[Permission]:
        rows = self.session.scalars(select(PermissionModel).order_by(PermissionModel.code))
        return [_permission(row) for row in rows]

    def replace_role_permissions(self, role_id: UUID, permission_ids: set[UUID]) -> None:
        self.session.execute(
            delete(RolePermissionModel).where(RolePermissionModel.role_id == str(role_id))
        )
        self.session.add_all(
            RolePermissionModel(role_id=str(role_id), permission_id=str(permission_id))
            for permission_id in permission_ids
        )

    def list_role_permissions(self, role_id: UUID) -> list[Permission]:
        statement = (
            select(PermissionModel)
            .join(
                RolePermissionModel,
                RolePermissionModel.permission_id == PermissionModel.id,
            )
            .where(RolePermissionModel.role_id == str(role_id))
            .order_by(PermissionModel.code)
        )
        return [_permission(row) for row in self.session.scalars(statement)]

    def add_assignment(self, assignment: RoleAssignment) -> None:
        self.session.add(self._assignment_model(assignment))

    def get_assignment(self, assignment_id: UUID) -> RoleAssignment | None:
        model = self.session.get(RoleAssignmentModel, str(assignment_id))
        return _assignment(model) if model else None

    def find_assignment(
        self, *, user_id: UUID, role_id: UUID, scope_type: str, scope_key: str
    ) -> RoleAssignment | None:
        model = self.session.scalar(
            select(RoleAssignmentModel).where(
                RoleAssignmentModel.user_id == str(user_id),
                RoleAssignmentModel.role_id == str(role_id),
                RoleAssignmentModel.scope_type == scope_type,
                RoleAssignmentModel.scope_key == scope_key,
            )
        )
        return _assignment(model) if model else None

    def list_assignments(self, user_id: UUID) -> list[RoleAssignment]:
        statement = (
            select(RoleAssignmentModel)
            .where(RoleAssignmentModel.user_id == str(user_id))
            .order_by(RoleAssignmentModel.created_at, RoleAssignmentModel.id)
        )
        return [_assignment(row) for row in self.session.scalars(statement)]

    def remove_assignment(self, assignment: RoleAssignment) -> None:
        model = self.session.get(RoleAssignmentModel, str(assignment.id))
        if model:
            self.session.delete(model)

    def list_grants(self, user_id: UUID) -> list[PermissionGrant]:
        statement = (
            select(
                PermissionModel.code,
                RoleAssignmentModel.role_id,
                RoleAssignmentModel.scope_type,
                RoleAssignmentModel.scope_id,
            )
            .join(
                RolePermissionModel,
                RolePermissionModel.permission_id == PermissionModel.id,
            )
            .join(RoleModel, RoleModel.id == RolePermissionModel.role_id)
            .join(RoleAssignmentModel, RoleAssignmentModel.role_id == RoleModel.id)
            .where(
                RoleAssignmentModel.user_id == str(user_id),
                RoleModel.active.is_(True),
            )
            .order_by(PermissionModel.code)
        )
        return [
            PermissionGrant(
                permission_code=code,
                role_id=UUID(role_id),
                scope_type=ScopeType(scope_type),
                scope_id=UUID(scope_id) if scope_id else None,
            )
            for code, role_id, scope_type, scope_id in self.session.execute(statement)
        ]

    @staticmethod
    def _user_model(user: User) -> UserModel:
        return UserModel(
            id=str(user.id),
            default_warehouse_id=str(user.default_warehouse_id)
            if user.default_warehouse_id
            else None,
            auth0_subject=user.auth0_subject,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            status=user.status.value,
            created_at=user.created_at,
            created_by=str(user.created_by) if user.created_by else None,
            updated_at=user.updated_at,
            updated_by=str(user.updated_by) if user.updated_by else None,
        )

    @staticmethod
    def _role_model(role: Role) -> RoleModel:
        return RoleModel(
            id=str(role.id),
            code=role.code,
            name=role.name,
            description=role.description,
            active=role.active,
            system_role=role.system_role,
            created_at=role.created_at,
            created_by=str(role.created_by) if role.created_by else None,
            updated_at=role.updated_at,
            updated_by=str(role.updated_by) if role.updated_by else None,
        )

    @staticmethod
    def _assignment_model(assignment: RoleAssignment) -> RoleAssignmentModel:
        return RoleAssignmentModel(
            id=str(assignment.id),
            user_id=str(assignment.user_id),
            role_id=str(assignment.role_id),
            scope_type=assignment.scope_type.value,
            scope_id=str(assignment.scope_id) if assignment.scope_id else None,
            scope_key=assignment.scope_key,
            created_at=assignment.created_at,
            created_by=str(assignment.created_by) if assignment.created_by else None,
        )


class SqlAlchemyIdentityUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.identity = SqlAlchemyIdentityRepository(session)

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Identity data conflicts with an existing record") from exc

    def rollback(self) -> None:
        self.session.rollback()
