"""Database engine and session management."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from config import DB_PATH
from models import Base
from models.person import Person
from models.seed_image import SeedImage
from models.settings_model import Setting
from models.verification import Verification
from utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH_URL = f"sqlite:///{DB_PATH.as_posix()}"

try:
    engine = create_engine(
        DB_PATH_URL,
        connect_args={"check_same_thread": False},
    )
except Exception as exc:
    logger.exception("Failed to create database engine")
    raise RuntimeError(f"Failed to create database engine: {exc}") from exc


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all database tables if they do not exist."""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database initialized successfully")
    except SQLAlchemyError as exc:
        logger.exception("Database initialization failed")
        raise RuntimeError(f"Failed to initialize database: {exc}") from exc


@contextmanager
def get_db():
    """Yield a database session and ensure proper cleanup."""
    session = SessionLocal()
    try:
        yield session
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Database session error")
        raise RuntimeError(f"Database operation failed: {exc}") from exc
    finally:
        session.close()


__all__ = [
    "engine",
    "SessionLocal",
    "init_db",
    "get_db",
    "Person",
    "Verification",
    "Setting",
    "SeedImage",
]
