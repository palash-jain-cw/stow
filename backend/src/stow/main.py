from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel, Session
from stow.db import engine
from stow.models import AccountGroup, Account, OpeningBalance  # noqa: F401 — registers tables
from stow.routers import account_groups, accounts, opening_balances
from stow.seed import seed_account_groups


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_account_groups(session)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(account_groups.router)
app.include_router(accounts.router)
app.include_router(opening_balances.router)


@app.get("/health")
def health():
    return {"status": "ok"}
