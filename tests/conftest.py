import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from warehouse_erp.catalog.infrastructure import models  # noqa: F401
from warehouse_erp.config import load_settings
from warehouse_erp.configuration.infrastructure import models as configuration_models  # noqa: F401
from warehouse_erp.database import Base, get_db_session
from warehouse_erp.identity.api.dependencies import get_current_identity, get_current_user
from warehouse_erp.identity.domain.entities import (
    AuthenticatedIdentity,
    CurrentUser,
    PermissionGrant,
    ScopeType,
    UserStatus,
)
from warehouse_erp.identity.infrastructure import models as identity_models  # noqa: F401
from warehouse_erp.identity.infrastructure.seeds import role_id, seed_identity_defaults
from warehouse_erp.inventory.infrastructure import models as inventory_models  # noqa: F401
from warehouse_erp.main import create_app
from warehouse_erp.permission_catalog import PERMISSIONS, SYSTEM_ROLES
from warehouse_erp.settings.infrastructure import models as settings_models  # noqa: F401
from warehouse_erp.settings.infrastructure.seeds import seed_settings_defaults
from warehouse_erp.warehouse.infrastructure import models as warehouse_models  # noqa: F401


def _test_engine(url):
    return create_engine(
        url,
        connect_args={"connect_timeout": 10, "read_timeout": 45, "write_timeout": 45},
        pool_pre_ping=True,
    )


def _drop_test_schema(engine):
    # Reflect actual schema: setup/migration failures may leave only part of the DDL applied.
    metadata = MetaData()
    metadata.reflect(engine)
    metadata.drop_all(engine)


ADMIN_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _test_database_url(environment_variable: str) -> URL:
    raw = os.getenv(environment_variable)
    if not raw:
        pytest.skip(f"{environment_variable} is required for MariaDB integration tests")
    url = make_url(raw)
    if (
        url.drivername != "mariadb+pymysql"
        or not url.database
        or not url.database.endswith("_test")
    ):
        raise RuntimeError(
            f"{environment_variable} must target a dedicated MariaDB *_test database"
        )
    application = make_url(load_settings().database_url)
    if url.database == application.database:
        raise RuntimeError("Test database must differ from APP_DATABASE_URL")
    return url


def _require_empty_database(url: URL) -> None:
    engine = _test_engine(url)
    try:
        tables = inspect(engine).get_table_names()
        if tables:
            raise RuntimeError(
                f"Test database {url.database} must be empty before tests: {', '.join(tables)}"
            )
    finally:
        engine.dispose()


@pytest.fixture
def migration_database_url() -> Iterator[str]:
    url = _test_database_url("TEST_DATABASE_URL")
    _require_empty_database(url)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        engine = _test_engine(url)
        try:
            _drop_test_schema(engine)
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        finally:
            engine.dispose()


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    url = _test_database_url("TEST_DATABASE_URL")
    _require_empty_database(url)
    engine = _test_engine(url)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        Base.metadata.create_all(engine)
        with factory() as session:
            seed_identity_defaults(
                session,
                permissions=PERMISSIONS,
                roles=SYSTEM_ROLES,
            )
            seed_settings_defaults(session)
            from warehouse_erp.configuration.infrastructure.repositories import (
                seed_configuration_defaults,
            )

            seed_configuration_defaults(session)
            now = datetime.now(UTC)
            session.add(
                identity_models.UserModel(
                    id=str(ADMIN_USER_ID),
                    auth0_subject="auth0|test-user",
                    email="admin@example.test",
                    display_name="Test admin",
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        yield factory
    finally:
        _drop_test_schema(engine)
        engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|test-user"
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=ADMIN_USER_ID,
        subject="auth0|test-user",
        status=UserStatus.ACTIVE,
        grants=tuple(
            PermissionGrant(
                permission_code=str(definition.code),
                role_id=UUID(role_id("ADMIN")),
                scope_type=ScopeType.GLOBAL,
                scope_id=None,
            )
            for definition in PERMISSIONS
        ),
    )
    with TestClient(app) as test_client:
        yield test_client
