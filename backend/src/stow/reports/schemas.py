from __future__ import annotations

from datetime import date
from pydantic import BaseModel


class TrialBalanceRow(BaseModel):
    account_id: int
    account_name: str
    group_name: str
    nature: str
    opening_balance: int   # paise, signed (positive = Dr)
    debit: int             # paise, always >= 0
    credit: int            # paise, always >= 0
    closing_balance: int   # paise, signed (positive = Dr)


class TrialBalanceReport(BaseModel):
    fy_id: int
    fy_start_date: date
    fy_end_date: date
    rows: list[TrialBalanceRow]
    total_debit: int
    total_credit: int


class ProfitLossGroup(BaseModel):
    group_name: str
    nature: str            # income | expense
    accounts: list[dict]   # {account_id, account_name, amount}
    subtotal: int          # paise


class ProfitLossReport(BaseModel):
    fy_id: int
    fy_start_date: date
    fy_end_date: date
    income_groups: list[ProfitLossGroup]
    expense_groups: list[ProfitLossGroup]
    total_income: int
    total_expenses: int
    net_profit: int        # paise (total_income - total_expenses)


class BalanceSheetSection(BaseModel):
    group_name: str
    nature: str
    accounts: list[dict]
    subtotal: int


class BalanceSheetReport(BaseModel):
    fy_id: int
    as_of_date: date
    asset_sections: list[BalanceSheetSection]
    liability_sections: list[BalanceSheetSection]
    equity_sections: list[BalanceSheetSection]
    total_assets: int
    total_liabilities_and_equity: int


class CashFlowSection(BaseModel):
    tag: str               # operating | investing | financing
    items: list[dict]      # {label, amount}
    subtotal: int


class CashFlowReport(BaseModel):
    fy_id: int
    fy_start_date: date
    fy_end_date: date
    net_profit: int
    sections: list[CashFlowSection]
    net_change_in_cash: int
    opening_cash: int
    closing_cash: int
