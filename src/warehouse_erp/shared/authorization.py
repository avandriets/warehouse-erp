from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    """A permission contributed by the module that implements the protected operation."""

    code: str
    description: str


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    """An optional application-level role template composed from module permissions."""

    code: str
    name: str
    description: str
    permission_codes: frozenset[str]
