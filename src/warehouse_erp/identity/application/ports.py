from typing import Protocol

from warehouse_erp.identity.domain.entities import AuthenticatedIdentity


class AccessTokenVerifier(Protocol):
    def verify(self, access_token: str) -> AuthenticatedIdentity: ...
