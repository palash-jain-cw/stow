from collections.abc import Generator
from sqlmodel import create_engine, Session
from sqlalchemy import Engine
from stow.config import Settings

engine: Engine = create_engine(Settings().database_url)


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
