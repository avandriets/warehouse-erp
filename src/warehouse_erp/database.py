from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from warehouse_erp.config import load_settings


class Base(DeclarativeBase):
    pass


settings = load_settings()
engine = create_engine(settings.database_url, echo=settings.sql_echo)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db_session() -> Iterator[Session]:
    with SessionFactory() as session:
        yield session
