from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_PORT = 5432
_DEFAULT_POOL_SIZE = 5

_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker[Session]] = None


def _build_conninfo() -> str:
    direct = os.getenv("DATABASE_URL")
    if direct:
        if direct.startswith("postgresql+psycopg://"):
            return direct
        if direct.startswith("postgresql://"):
            return direct.replace("postgresql://", "postgresql+psycopg://", 1)
        if direct.startswith("postgres://"):
            return direct.replace("postgres://", "postgresql+psycopg://", 1)
        return direct

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", _DEFAULT_PORT))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    dbname = os.getenv("POSTGRES_DB", "postgres")

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"


def get_engine() -> Engine:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is None:
        pool_size = int(os.getenv("DB_POOL_SIZE", _DEFAULT_POOL_SIZE))
        _ENGINE = create_engine(
            _build_conninfo(),
            pool_size=pool_size,
            max_overflow=max(1, pool_size),
            pool_pre_ping=True,
            future=True,
        )
        _SESSION_FACTORY = sessionmaker(
            bind=_ENGINE,
            expire_on_commit=False,
            autoflush=False,
            future=True,
        )
    return _ENGINE


def _get_session_factory() -> sessionmaker[Session]:
    if _SESSION_FACTORY is None:
        get_engine()
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


@contextmanager
def get_session(existing: Optional[Session] = None) -> Iterator[Session]:
    if existing is not None:
        yield existing
        return

    factory = _get_session_factory()
    with factory() as session:
        yield session


def create_db_client() -> Session:
    factory = _get_session_factory()
    return factory()
