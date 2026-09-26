import ssl
from typing import Any, Protocol

import certifi
import jwt

from warehouse_erp.identity.application.errors import (
    AuthenticationNotConfiguredError,
    AuthenticationProviderUnavailableError,
    InvalidAccessTokenError,
)
from warehouse_erp.identity.domain.entities import AuthenticatedIdentity


class SigningKey(Protocol):
    key: Any


class SigningKeyProvider(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


class Auth0AccessTokenVerifier:
    def __init__(
        self,
        *,
        domain: str | None,
        audience: str | None,
        algorithm: str = "RS256",
        signing_keys: SigningKeyProvider | None = None,
    ) -> None:
        self.domain = domain.strip().removeprefix("https://").rstrip("/") if domain else None
        self.audience = audience
        self.algorithm = algorithm
        self.issuer = f"https://{self.domain}/" if self.domain else None
        self.signing_keys = signing_keys
        if self.issuer and self.signing_keys is None:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            self.signing_keys = jwt.PyJWKClient(
                f"{self.issuer}.well-known/jwks.json",
                ssl_context=ssl_context,
            )

    def verify(self, access_token: str) -> AuthenticatedIdentity:
        if not self.issuer or not self.audience or not self.signing_keys:
            raise AuthenticationNotConfiguredError

        try:
            signing_key = self.signing_keys.get_signing_key_from_jwt(access_token).key
            payload = jwt.decode(
                access_token,
                signing_key,
                algorithms=[self.algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["aud", "exp", "iat", "iss", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthenticationProviderUnavailableError from exc
        except (jwt.PyJWKClientError, jwt.InvalidTokenError) as exc:
            raise InvalidAccessTokenError from exc

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidAccessTokenError

        raw_scope = payload.get("scope", "")
        scopes = frozenset(raw_scope.split()) if isinstance(raw_scope, str) else frozenset()
        return AuthenticatedIdentity(subject=subject, scopes=scopes)
