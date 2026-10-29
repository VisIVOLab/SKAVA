# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Generator
import math
import sqlite3
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def _sqlite_math(dbapi_connection, _record) -> None:
    """The trigonometry the cone search uses, on any SQLite connection.

    PostgreSQL has these functions; SQLite has them only when built with its
    math functions, which a given Python's SQLite may lack. Registering them
    makes the same SQL run on both (tests, development, CI)."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    for name, fn in (("sin", math.sin), ("cos", math.cos), ("radians", math.radians)):
        dbapi_connection.create_function(name, 1, _null_safe(fn), deterministic=True)


def _null_safe(fn):
    """SQL semantics: NULL in, NULL out."""
    def wrapped(value):
        return None if value is None else fn(value)
    return wrapped


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _build_engine():
    if _is_sqlite(settings.database_url):
        return create_engine(settings.database_url, pool_pre_ping=True)

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def wait_for_db() -> None:
    """Retry DB connectivity during startup for robust deployments."""
    last_error: Exception | None = None
    for _ in range(settings.db_connect_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(settings.db_connect_retry_delay)

    raise RuntimeError(f"Database connection failed after retries: {last_error}")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
