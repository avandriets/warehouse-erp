import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    host: str
    port: int
    database_url: str
    sql_echo: bool
    cors_origins: tuple[str, ...]
    auth0_domain: str | None
    auth0_audience: str | None


def load_settings() -> Settings:
    database_url = os.getenv("APP_DATABASE_URL", "")
    if not database_url.startswith("mariadb+pymysql://"):
        raise ValueError("APP_DATABASE_URL must be a MariaDB URL (mariadb+pymysql://)")
    return Settings(
        app_name=os.getenv("APP_NAME", "Warehouse ERP"),
        environment=os.getenv("APP_ENV", "development"),
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8100")),
        database_url=database_url,
        sql_echo=_as_bool(os.getenv("APP_SQL_ECHO", "false")),
        cors_origins=_as_csv(os.getenv("APP_CORS_ORIGINS", "http://localhost:4300")),
        auth0_domain=os.getenv("AUTH0_DOMAIN") or None,
        auth0_audience=os.getenv("AUTH0_AUDIENCE") or None,
    )
