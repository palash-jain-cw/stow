import logging
import os

from tests.load_env import load_llm_env

load_llm_env()
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
# WeasyPrint dlopen()s pango/gobject lazily; setting this before the first PDF request is sufficient.
os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

from stow.main import app
from stow.db import get_session
from stow.seed import seed_account_groups
from stow.migrations import run_migrations

logger = logging.getLogger(__name__)

# Set by run_tests.sh or manually when Docker group membership is missing.
STOW_TEST_DATABASE_URL = os.environ.get("STOW_TEST_DATABASE_URL", "").strip()


def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False)
    parser.addoption(
        "--test-db-url",
        action="store",
        default=None,
        help="Postgres URL for tests (overrides testcontainers when Docker is unavailable)",
    )


def pytest_configure(config):
    url = config.getoption("--test-db-url")
    if url:
        os.environ["STOW_TEST_DATABASE_URL"] = url


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="pass --run-integration to run")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)


def _docker_socket_accessible() -> bool:
    sock_path = "/var/run/docker.sock"
    if not os.path.exists(sock_path):
        return False
    if os.access(sock_path, os.R_OK | os.W_OK):
        return True
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _resolve_test_database_url(config) -> str | None:
    cli_url = config.getoption("--test-db-url") if config else None
    if cli_url:
        return cli_url
    if STOW_TEST_DATABASE_URL:
        return STOW_TEST_DATABASE_URL
    return None


def _truncate_all_tables(session: Session) -> None:
    """Clear all rows — external test DB persists between pytest runs."""
    bind = session.get_bind()
    with bind.connect() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        conn.commit()
    run_migrations(session)
    seed_account_groups(session)


def _create_engine_from_url(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        run_migrations(session)
        _truncate_all_tables(session)
    logger.info("Using external test database (fresh): %s", url.split("@")[-1])
    return engine


def _docker_help_message(original_error: Exception | None = None) -> str:
    err = f"\nOriginal error: {original_error}" if original_error else ""
    return (
        "Tests need Postgres. Options:\n"
        "  1. Add yourself to the docker group (permanent fix):\n"
        "       sudo usermod -aG docker $USER\n"
        "     then log out and back in (or reboot).\n"
        "  2. Use the test Postgres compose file (no docker group needed):\n"
        "       sudo docker compose -f docker-compose.test.yml up -d\n"
        "       cd backend && STOW_TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:5433/test uv run pytest tests/\n"
        "  3. Run the helper script (starts compose with sudo if needed):\n"
        "       cd backend && ./scripts/run_tests.sh\n"
        f"{err}"
    )


@pytest.fixture(scope="session")
def engine(request):
    external_url = _resolve_test_database_url(request.config)
    if external_url:
        yield _create_engine_from_url(external_url)
        return

    if not _docker_socket_accessible():
        pytest.exit(_docker_help_message(), returncode=1)

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.exit(
            _docker_help_message(exc),
            returncode=1,
        )

    try:
        with PostgresContainer("postgres:16-alpine") as pg:
            url = pg.get_connection_url()
            engine = create_engine(url)
            SQLModel.metadata.create_all(engine)
            with Session(engine) as session:
                seed_account_groups(session)
            logger.info("Using testcontainers Postgres")
            yield engine
    except Exception as exc:
        pytest.exit(_docker_help_message(exc), returncode=1)


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


@pytest.fixture()
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
