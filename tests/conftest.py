import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

# Ensure repo root is importable when running pytest directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.db import get_engine


@pytest.fixture(scope="session")
def postgres_container():
    container = PostgresContainer("postgres:17", driver=None)
    container.start()
    try:
        os.environ["DATABASE_URL"] = container.get_connection_url()
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def _init_db(postgres_container):
    import os
    from pathlib import Path
    from sqlalchemy.engine.url import make_url

    os.environ["DATABASE_URL"] = postgres_container.get_connection_url()

    # Ensure schema is initialized once per test session using psql inside container.
    base_dir = Path(__file__).resolve().parents[1]
    init_sql = (base_dir / "db" / "init" / "init.sql").read_text(encoding="utf-8")
    catalog_sql = (base_dir / "db" / "init" / "insert_catalog.sql").read_text(encoding="utf-8")

    url = make_url(os.environ["DATABASE_URL"])
    user = url.username or "test"
    dbname = url.database or "test"

    def _psql_exec(sql_text: str) -> None:
        heredoc = (
            "set -euo pipefail\n"
            "cat > /tmp/test_init.sql <<'SQL'\n"
            f"{sql_text}\n"
            "SQL\n"
            f"psql -U {user} -d {dbname} -v ON_ERROR_STOP=1 -f /tmp/test_init.sql\n"
        )
        exit_code, output = postgres_container.exec(["/bin/sh", "-c", heredoc])
        if exit_code != 0:
            raise RuntimeError(f"Failed to init schema: {output}")

    _psql_exec(init_sql)
    _psql_exec(catalog_sql)


@pytest.fixture()
def db_session(_init_db):
    import os
    os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        future=True,
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
