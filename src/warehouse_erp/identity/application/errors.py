class InvalidAccessTokenError(Exception):
    """The access token is absent, malformed, expired, or has invalid claims."""


class AuthenticationProviderUnavailableError(Exception):
    """The external identity provider keys cannot currently be obtained."""


class AuthenticationNotConfiguredError(Exception):
    """Authentication settings required to verify tokens are missing."""
