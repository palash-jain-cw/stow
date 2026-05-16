from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from sqlalchemy import BigInteger, Column, JSON, UniqueConstraint
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
    accumulated_depreciation_account_id: Optional[int] = Field(default=None, foreign_key="account.id")
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


class Lot(SQLModel, table=True):
    __tablename__ = "lot"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    transaction_id: int = Field(foreign_key="transaction.id")
    acquisition_date: date
    units: int            # milliunits (1 unit = 1000 milliunits)
    cost_per_unit: int    # paise per milliunit
    remaining_units: int  # decremented on sale; 0 = fully consumed


class CapitalGainEntry(SQLModel, table=True):
    __tablename__ = "capital_gain_entry"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    lot_id: int = Field(foreign_key="lot.id")
    sale_transaction_id: int = Field(foreign_key="transaction.id")
    units_sold: int           # milliunits consumed from this lot
    sale_date: date
    sale_price_per_unit: int  # paise per milliunit
    gain: int                 # paise, signed (negative = loss)
    gain_type: str            # stcg | ltcg


class CapitalGainsTaxRule(SQLModel, table=True):
    __tablename__ = "capital_gains_tax_rule"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    asset_type: str                # equity | debt
    holding_threshold_days: int    # days >= this → ltcg
    stcg_rate_bps: int             # basis points (2000 = 20%)
    ltcg_rate_bps: int             # basis points (1250 = 12.5%)
    ltcg_exemption_paise: int      # paise (12_500_000 = ₹1.25L)
    effective_from: date


class FdMetadata(SQLModel, table=True):
    __tablename__ = "fd_metadata"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_fd_metadata_account"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    principal: int              # paise
    interest_rate: int          # basis points (e.g. 750 = 7.50% p.a.)
    start_date: date
    maturity_date: date
    compounding: str            # simple | monthly | quarterly | yearly
    status: str = "active"      # active | matured | closed


class RecurringSchedule(SQLModel, table=True):
    __tablename__ = "recurring_schedule"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    template_transaction_id: int = Field(foreign_key="transaction.id")
    frequency: str                       # daily | weekly | monthly | yearly
    day_of_period: Optional[int] = None  # day of month (monthly) or day of week (weekly)
    end_date: Optional[date] = None
    next_due_date: date
    is_active: bool = True


class RecurringQueueItem(SQLModel, table=True):
    __tablename__ = "recurring_queue_item"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_id: int = Field(foreign_key="recurring_schedule.id")
    due_date: date
    status: str = "pending"              # pending | confirmed | skipped | auto-posted
    posted_transaction_id: Optional[int] = Field(default=None, foreign_key="transaction.id")


class PriceQuote(SQLModel, table=True):
    __tablename__ = "price_quote"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("account_id", "quote_date", name="uq_price_quote_account_date"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    price: int        # paise per unit
    quote_date: date
    source: str       # mfapi | yfinance


class ImportBatch(SQLModel, table=True):
    __tablename__ = "import_batch"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    detected_bank: Optional[str] = None
    statement_from: Optional[date] = None
    statement_to: Optional[date] = None
    bank_account_id: Optional[int] = Field(default=None, foreign_key="account.id")
    status: str = "processing"  # processing | ready | posted
    possible_duplicate: bool = False


class StagingRow(SQLModel, table=True):
    __tablename__ = "staging_row"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="import_batch.id")
    raw_data: dict = Field(sa_column=Column(JSON))
    date: date
    amount: int  # paise — negative = debit
    description: str
    suggested_account_id: Optional[int] = Field(default=None, foreign_key="account.id")
    status: str = "pending"  # pending | confirmed | discarded | reconciled
    matched_transaction_id: Optional[int] = Field(default=None, foreign_key="transaction.id")
    narration_override: Optional[str] = None
    tags: Optional[list] = Field(default=None, sa_column=Column(JSON))
    possible_duplicate: bool = False


class MerchantRule(SQLModel, table=True):
    __tablename__ = "merchant_rule"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    pattern: str   # wildcard, case-insensitive, e.g. "BESCOM*"
    account_id: int = Field(foreign_key="account.id")


class TelegramUser(SQLModel, table=True):
    __tablename__ = "telegram_user"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_user_id: int = Field(sa_column=Column(BigInteger, unique=True, nullable=False))
    username: Optional[str] = None
