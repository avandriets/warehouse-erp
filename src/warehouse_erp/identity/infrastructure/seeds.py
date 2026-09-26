from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from warehouse_erp.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
)
from warehouse_erp.shared.authorization import PermissionDefinition, RoleDefinition


def permission_id(code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/permission/{code}"))


def role_id(code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"warehouse-erp/role/{code}"))


def seed_identity_defaults(
    session: Session,
    *,
    permissions: Iterable[PermissionDefinition],
    roles: Iterable[RoleDefinition],
) -> None:
    permission_definitions = tuple(permissions)
    role_definitions = tuple(roles)
    now = datetime.now(UTC)
    existing_permissions = set(session.scalars(select(PermissionModel.code)))
    for definition in permission_definitions:
        code = str(definition.code)
        if code not in existing_permissions:
            session.add(
                PermissionModel(
                    id=permission_id(code),
                    code=code,
                    description=definition.description,
                )
            )

    existing_roles = set(session.scalars(select(RoleModel.code)))
    for definition in role_definitions:
        if definition.code not in existing_roles:
            session.add(
                RoleModel(
                    id=role_id(definition.code),
                    code=definition.code,
                    name=definition.name,
                    description=definition.description,
                    active=True,
                    system_role=True,
                    created_at=now,
                    updated_at=now,
                )
            )
    session.flush()

    existing_links = set(
        session.execute(
            select(RolePermissionModel.role_id, RolePermissionModel.permission_id)
        ).tuples()
    )
    for definition in role_definitions:
        for permission_code in definition.permission_codes:
            link = (role_id(definition.code), permission_id(str(permission_code)))
            if link not in existing_links:
                session.add(RolePermissionModel(role_id=link[0], permission_id=link[1]))
    session.commit()
