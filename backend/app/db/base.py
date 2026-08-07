from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def build_engine(url: str | None = None):
    database_url = url or get_settings().database_url
    options = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    value = create_engine(database_url, connect_args=options)
    if database_url.startswith("sqlite"):
        @event.listens_for(value, "connect")
        def enable_foreign_keys(connection, record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return value


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
