from sqlmodel import create_engine
from sqlalchemy import Engine


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url)
