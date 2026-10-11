from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from warehouse_erp.config import Settings, load_settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        echo=settings.sql_echo,
        pool_pre_ping=True,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_timeout=settings.db_pool_timeout_seconds,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            "read_timeout": settings.db_read_timeout_seconds,
            "write_timeout": settings.db_write_timeout_seconds,
        },
    )


def is_database_unavailable(error: DBAPIError) -> bool:
    # Do not classify SQL/constraint errors as temporary outages.
    code = error.orig.args[0] if error.orig.args else None
    return error.connection_invalidated or code in {1040, 1203, 2002, 2003, 2006, 2013, 2055}


engine = build_engine(load_settings())
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db_session() -> Iterator[Session]:
    with SessionFactory() as session:
        yield session
