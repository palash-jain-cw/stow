import os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
# WeasyPrint dlopen()s pango/gobject lazily; setting this before the first PDF request is sufficient.
os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from testcontainers.postgres import PostgresContainer

from stow.main import app
from stow.db import get_session
from stow.seed import seed_account_groups


@pytest.fixture(scope="session")
def engine():
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        engine = create_engine(url)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            seed_account_groups(s)
        yield engine


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
