from collections.abc import Callable
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from warehouse_erp.config import load_settings
from warehouse_erp.database import get_db_session
from warehouse_erp.identity.application.errors import (
    AuthenticationNotConfiguredError,
    AuthenticationProviderUnavailableError,
    InvalidAccessTokenError,
)
from warehouse_erp.identity.application.ports import AccessTokenVerifier
from warehouse_erp.identity.application.service import IdentityService
from warehouse_erp.identity.domain.entities import (
    AuthenticatedIdentity,
    CurrentUser,
    ScopeType,
    UserStatus,
)
from warehouse_erp.identity.infrastructure.auth0 import Auth0AccessTokenVerifier
from warehouse_erp.identity.infrastructure.repositories import SqlAlchemyIdentityUnitOfWork

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_access_token_verifier() -> AccessTokenVerifier:
    settings = load_settings()
    return Auth0AccessTokenVerifier(
        domain=settings.auth0_domain,
        audience=settings.auth0_audience,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    verifier: Annotated[AccessTokenVerifier, Depends(get_access_token_verifier)],
) -> AuthenticatedIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Authentication required")

    try:
        return verifier.verify(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise _unauthorized("Invalid access token") from exc
    except AuthenticationNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        ) from exc
    except AuthenticationProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider is unavailable",
        ) from exc


def get_identity_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> IdentityService:
    return IdentityService(SqlAlchemyIdentityUnitOfWork(session))


def get_current_user(
    identity: Annotated[AuthenticatedIdentity, Depends(get_current_identity)],
    service: Annotated[IdentityService, Depends(get_identity_service)],
) -> CurrentUser:
    return service.resolve_current_user(identity)


def require_permission(
    permission_code: str,
    *,
    scope_type: ScopeType = ScopeType.GLOBAL,
    scope_id: UUID | None = None,
) -> Callable[[CurrentUser], CurrentUser]:
    def dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if user.status is UserStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is waiting for administrator approval",
            )
        if user.status is not UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not active",
            )
        if not user.has_permission(
            permission_code,
            scope_type=scope_type,
            scope_id=scope_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission_code}",
            )
        return user

    return dependency
