from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

_today = date.today  # captured before Transaction class to avoid 'date' field shadowing


class AccountGroup(SQLModel, table=True):
    __tablename__ = "account_group"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="account_group.id")
    nature: str  # asset | liability | equity | income | expense
    cash_flow_tag: Optional[str] = None  # operating | investing | financing
    sort_order: int = 0


class Account(SQLModel, table=True):
    __tablename__ = "account"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    group_id: int = Field(foreign_key="account_group.id")
    is_archived: bool = False
    investment_subtype: Optional[str] = None  # equity_mf | stock | fd | ppf
    depreciation_rate: Optional[float] = None
    price_source_id: Optional[str] = None
    currency: str = "INR"


class FinancialYear(SQLModel, table=True):
    __tablename__ = "financial_year"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    start_date: date
    end_date: date
    status: str = "open"  # open | active | locked
    net_profit: Optional[int] = None  # paise, set at lock time


class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    number: str = Field(index=True)
    type: str  # payment | receipt | journal | contra
    date: date
    entry_date: date = Field(default_factory=_today)
    narration: str
    fy_id: int = Field(foreign_key="financial_year.id")
    tags: Optional[list] = Field(default=None, sa_column=Column(JSON))
    attachment_path: Optional[str] = None


class Entry(SQLModel, table=True):
    __tablename__ = "entry"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    amount: int  # paise — positive = debit, negative = credit


class TransactionAuditLog(SQLModel, table=True):
    __tablename__ = "transaction_audit_log"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    snapshot: dict = Field(sa_column=Column(JSON))
    edited_at: datetime = Field(default_factory=datetime.utcnow)


class OpeningBalance(SQLModel, table=True):
    __tablename__ = "opening_balance"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    fy_id: int = Field(foreign_key="financial_year.id")
    amount: int = 0  # paise
