import pytest
from testcontainers.postgres import PostgresContainer
from sqlmodel import text
from stow.db import make_engine


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg2")


def test_engine_connects(postgres_url):
    engine = make_engine(postgres_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
