from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import Mock

import pymysql
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as DatabasePoolTimeout
from sqlalchemy.orm import Session, sessionmaker

from warehouse_erp.config import load_settings
from warehouse_erp.database import build_engine, get_db_session
from warehouse_erp.identity.api.dependencies import get_current_identity
from warehouse_erp.identity.domain.entities import AuthenticatedIdentity
from warehouse_erp.main import create_app


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("private SQL", {}, pymysql.err.OperationalError(2003, "private host")),
        OperationalError(
            "private SQL", {}, pymysql.err.OperationalError(2013, "private parameters")
        ),
        OperationalError(
            "private SQL", {}, pymysql.err.OperationalError(1040, "Too many connections")
        ),
        OperationalError(
            "private SQL", {}, pymysql.err.InterfaceError(0, "closed"), connection_invalidated=True
        ),
        DatabasePoolTimeout("private connection pool"),
    ],
)
def test_identity_database_outage_returns_503_without_replaying(error):
    app = create_app()
    session = Mock(spec=Session)
    session.scalar.side_effect = error

    def broken_session():
        yield session

    app.dependency_overrides[get_db_session] = broken_session
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|new-user"
    )
    with TestClient(app) as client:
        response = client.get("/api/identity/me")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database temporarily unavailable. Please try again later."
    }
    session.scalar.assert_called_once()
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ProgrammingError("private SQL", {}, pymysql.err.ProgrammingError(1146, "Missing table")),
        IntegrityError("private SQL", {}, pymysql.err.IntegrityError(1062, "Duplicate entry")),
        OperationalError("private SQL", {}, pymysql.err.OperationalError(1213, "Deadlock")),
    ],
)
def test_sql_errors_are_not_misreported_as_database_outages(error):
    app = create_app()

    def broken_identity():
        raise error

    app.dependency_overrides[get_current_identity] = broken_identity
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/identity/me")
    assert response.status_code == 500


@pytest.mark.parametrize("value", ["0", "-1"])
def test_database_timeout_must_be_positive(monkeypatch, value):
    monkeypatch.setenv("APP_DB_CONNECT_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="APP_DB_CONNECT_TIMEOUT_SECONDS"):
        load_settings()


def test_first_login_recovers_closed_pooled_connection(session_factory: sessionmaker[Session]):
    # Only use the isolated *_test database provisioned by the shared fixture.
    test_url = session_factory.kw["bind"].url
    assert test_url.database.endswith("_test")
    settings = replace(load_settings(), database_url=test_url.render_as_string(hide_password=False))
    engine = build_engine(settings)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    app = create_app()

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = test_session
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|recovered-first-login"
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            stale_connection = connection.connection.dbapi_connection
        # Simulate a server/network closing a connection while it sits idle in the pool.
        stale_connection.close()
        with TestClient(app) as client:
            first = client.get("/api/identity/me")
            second = client.get("/api/identity/me")
            protected = client.get("/api/catalog/categories")
        assert first.status_code == second.status_code == 200
        assert first.json()["status"] == "PENDING_APPROVAL"
        assert first.json()["permissions"] == []
        assert first.json()["user_id"] == second.json()["user_id"]
        assert protected.status_code == 403
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT COUNT(*) FROM identity_users WHERE auth0_subject = :subject"),
                    {"subject": "auth0|recovered-first-login"},
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()
