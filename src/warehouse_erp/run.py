import uvicorn

from warehouse_erp.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "warehouse_erp.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
