class ApplicationError(Exception):
    """Base error safe to translate at the API boundary."""


class ValidationError(ApplicationError):
    pass


class NotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class ForbiddenError(ApplicationError):
    pass
