from contextlib import asynccontextmanager

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from sqlmodel import SQLModel, Session

from stow.db import engine
from stow.models import (  # noqa: F401 — registers tables
    AccountGroup, Account, OpeningBalance,
    FinancialYear, Transaction, Entry, TransactionAuditLog,
    Lot, CapitalGainEntry, CapitalGainsTaxRule, PriceQuote, FdMetadata,
    RecurringSchedule, RecurringQueueItem,
)
from stow.recurring import auto_post_pending, create_queue_entries_for_today
from stow.routers import account_groups, accounts, opening_balances, financial_years, transactions, reports, investments, tax_rules, prices, depreciation, recurring
from stow.seed import seed_account_groups


async def _morning_job():
    with Session(engine) as session:
        create_queue_entries_for_today(session)


async def _midnight_job():
    with Session(engine) as session:
        auto_post_pending(session)


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_account_groups(session)

    async with AsyncScheduler() as scheduler:
        await scheduler.add_schedule(_morning_job, CronTrigger(hour=6, minute=0))
        await scheduler.add_schedule(_midnight_job, CronTrigger(hour=0, minute=0))
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
app.include_router(prices.router)
app.include_router(depreciation.router)
app.include_router(recurring.router)


@app.get("/health")
def health():
    return {"status": "ok"}
