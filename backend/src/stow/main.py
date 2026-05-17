from contextlib import asynccontextmanager

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session

from stow.db import engine
from stow.models import (  # noqa: F401 — registers tables
    AccountGroup, Account, OpeningBalance,
    FinancialYear, Transaction, Entry, TransactionAuditLog,
    Lot, CapitalGainEntry, CapitalGainsTaxRule, PriceQuote, FdMetadata,
    RecurringSchedule, RecurringQueueItem,
    ImportBatch, StagingRow, MerchantRule, TelegramUser,
)
from stow.routers import account_groups, accounts, opening_balances, financial_years, transactions, reports, investments, tax_rules, prices, depreciation, recurring
from stow.routers import scheduler as scheduler_router
from stow.routers import ai as ai_router
from stow.routers import imports as imports_router
from stow.routers import merchant_rules as merchant_rules_router
from stow.routers import chat as chat_router
from stow.scheduler import register_schedules
from stow.seed import seed_account_groups


from agent.transport.telegram.bot import lifespan_telegram


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_account_groups(session)

    async with lifespan_telegram(app):
        async with AsyncScheduler() as scheduler:
            app.state.scheduler = scheduler
            await register_schedules(scheduler)
            yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
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
app.include_router(scheduler_router.router)
app.include_router(ai_router.router)
app.include_router(imports_router.router)
app.include_router(merchant_rules_router.router)
app.include_router(chat_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
