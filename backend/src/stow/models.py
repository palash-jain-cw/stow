from sqlmodel import Field, SQLModel


class AccountGroup(SQLModel, table=True):
    __tablename__ = "account_group"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    parent_id: int | None = Field(default=None, foreign_key="account_group.id")
    nature: str  # asset | liability | equity | income | expense
    cash_flow_tag: str | None = None  # operating | investing | financing
    sort_order: int = 0


class Account(SQLModel, table=True):
    __tablename__ = "account"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    group_id: int = Field(foreign_key="account_group.id")
    is_archived: bool = False
    investment_subtype: str | None = None  # equity_mf | stock | fd | ppf
    depreciation_rate: float | None = None
    price_source_id: str | None = None
    currency: str = "INR"


class OpeningBalance(SQLModel, table=True):
    __tablename__ = "opening_balance"

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    fy_id: int  # FK added in issue #4 when FY table exists
    amount: int = 0  # paise
