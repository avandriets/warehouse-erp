import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as DatabasePoolTimeout

from warehouse_erp.catalog.api.router import router as catalog_router
from warehouse_erp.config import load_settings
from warehouse_erp.configuration.api.router import router as configuration_router
from warehouse_erp.configuration.domain.exchange_rates import ExchangeRateProviderError
from warehouse_erp.database import is_database_unavailable
from warehouse_erp.identity.api.router import router as identity_router
from warehouse_erp.settings.api.router import router as settings_router
from warehouse_erp.shared.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from warehouse_erp.warehouse.api.router import router as warehouse_router

logger = logging.getLogger(__name__)


def _database_unavailable_response(request: Request) -> JSONResponse:
    # SQL exceptions may contain credentials, personal data, and query parameters.
    logger.warning("Database unavailable for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database temporarily unavailable. Please try again later."},
    )


def create_app() -> FastAPI:
    settings = load_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(DBAPIError)
    async def database_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
        if not is_database_unavailable(exc):
            raise exc
        return _database_unavailable_response(request)

    @application.exception_handler(DatabasePoolTimeout)
    async def database_pool_timeout_handler(
        request: Request, _: DatabasePoolTimeout
    ) -> JSONResponse:
        return _database_unavailable_response(request)

    @application.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @application.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @application.exception_handler(ValidationError)
    async def validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc)},
        )

    @application.exception_handler(ExchangeRateProviderError)
    async def exchange_rate_provider_handler(
        _: Request, exc: ExchangeRateProviderError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
        )

    @application.exception_handler(ForbiddenError)
    async def forbidden_handler(_: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    application.include_router(identity_router, prefix="/api")
    application.include_router(catalog_router, prefix="/api")
    application.include_router(settings_router, prefix="/api")
    application.include_router(configuration_router, prefix="/api")
    application.include_router(warehouse_router, prefix="/api")
    return application


app = create_app()
