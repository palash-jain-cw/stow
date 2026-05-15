from __future__ import annotations

from datetime import date
from pydantic import BaseModel


class BuyIn(BaseModel):
    fy_id: int
    date: date
    units: int            # milliunits
    cost_per_unit: int    # paise per milliunit
    bank_account_id: int
    narration: str


class SellIn(BaseModel):
    fy_id: int
    date: date
    units: int              # milliunits to sell
    price_per_unit: int     # paise per milliunit
    bank_account_id: int
    narration: str


class LotOut(BaseModel):
    id: int
    account_id: int
    transaction_id: int
    acquisition_date: date
    units: int
    cost_per_unit: int
    remaining_units: int


class CapitalGainEntryOut(BaseModel):
    id: int
    lot_id: int
    sale_transaction_id: int
    units_sold: int
    sale_date: date
    sale_price_per_unit: int
    gain: int
    gain_type: str


class HoldingOut(BaseModel):
    lot_id: int
    acquisition_date: date
    units: int
    remaining_units: int
    cost_per_unit: int
    cost_basis: int       # paise: remaining_units * cost_per_unit // 1000


class CapitalGainsSummary(BaseModel):
    fy_id: int
    entries: list[CapitalGainEntryOut]
    total_stcg: int
    total_ltcg: int
    total_loss: int


class TaxRuleIn(BaseModel):
    asset_type: str
    holding_threshold_days: int
    stcg_rate_bps: int
    ltcg_rate_bps: int
    ltcg_exemption_paise: int
    effective_from: date


class TaxRuleOut(BaseModel):
    id: int
    asset_type: str
    holding_threshold_days: int
    stcg_rate_bps: int
    ltcg_rate_bps: int
    ltcg_exemption_paise: int
    effective_from: date
