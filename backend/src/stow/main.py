from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel, Session
from stow.db import engine
from stow.models import (  # noqa: F401 — registers tables
    AccountGroup, Account, OpeningBalance,
    FinancialYear, Transaction, Entry, TransactionAuditLog,
    Lot, CapitalGainEntry, CapitalGainsTaxRule,
)
from stow.routers import account_groups, accounts, opening_balances, financial_years, transactions, reports, investments, tax_rules
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
app.include_router(financial_years.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(investments.router)
app.include_router(tax_rules.router)


@app.get("/health")
def health():
    return {"status": "ok"}
