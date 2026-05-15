from sqlmodel import text
from stow.db import make_engine


def test_engine_connects(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
