from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from warehouse_erp.catalog.api.router import router as catalog_router
from warehouse_erp.config import load_settings
from warehouse_erp.identity.api.router import router as identity_router
from warehouse_erp.settings.api.router import router as settings_router
from warehouse_erp.shared.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from warehouse_erp.warehouse.api.router import router as warehouse_router


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

    @application.exception_handler(ForbiddenError)
    async def forbidden_handler(_: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    application.include_router(identity_router, prefix="/api")
    application.include_router(catalog_router, prefix="/api")
    application.include_router(settings_router, prefix="/api")
    application.include_router(warehouse_router, prefix="/api")
    return application


app = create_app()
