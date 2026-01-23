from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


_DEFAULT_PORT = 5432
_DEFAULT_POOL_SIZE = 5

_POOL: Optional[ConnectionPool] = None


def _build_conninfo() -> str:
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", _DEFAULT_PORT))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    dbname = os.getenv("POSTGRES_DB", "postgres")

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def get_pool() -> ConnectionPool:
    global _POOL
    if _POOL is None:
        pool_size = int(os.getenv("DB_POOL_SIZE", _DEFAULT_POOL_SIZE))
        _POOL = ConnectionPool(
            conninfo=_build_conninfo(),
            min_size=1,
            max_size=max(1, pool_size),
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
    return _POOL


@contextmanager
def get_conn(existing: Optional[psycopg.Connection] = None) -> Iterator[psycopg.Connection]:
    if existing is not None:
        yield existing
        return

    pool = get_pool()
    with pool.connection() as conn:
        conn.autocommit = True
        conn.row_factory = dict_row
        yield conn


def create_db_client() -> psycopg.Connection:
    conninfo = _build_conninfo()
    return psycopg.connect(conninfo, autocommit=True, row_factory=dict_row)
