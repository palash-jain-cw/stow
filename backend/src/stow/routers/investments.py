from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from stow.db import get_session
from stow.investments.prices import PriceRepository
from stow.investments.repository import LotRepository
from stow.investments.schemas import (
    BuyIn, SellIn, LotOut, HoldingOut, CapitalGainsSummary, CapitalGainEntryOut,
    PortfolioItemOut,
)

router = APIRouter(prefix="/investments", tags=["investments"])


def _repo(session: Session = Depends(get_session)) -> LotRepository:
    return LotRepository(session)


@router.post("/{account_id}/buy", response_model=LotOut, status_code=201)
def buy(account_id: int, data: BuyIn, repo: LotRepository = Depends(_repo)):
    try:
        return repo.buy(account_id, data)
    except (ValueError, PermissionError) as e:
        status = 403 if isinstance(e, PermissionError) else 422
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/{account_id}/sell", response_model=list[CapitalGainEntryOut], status_code=201)
def sell(account_id: int, data: SellIn, repo: LotRepository = Depends(_repo)):
    try:
        return repo.sell(account_id, data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{account_id}/holdings", response_model=list[HoldingOut])
def holdings(account_id: int, repo: LotRepository = Depends(_repo)):
    return repo.holdings(account_id)


@router.get("/{account_id}/capital-gains", response_model=CapitalGainsSummary)
def capital_gains(account_id: int, fy_id: int, repo: LotRepository = Depends(_repo)):
    try:
        return repo.capital_gains(account_id, fy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{account_id}/portfolio", response_model=list[PortfolioItemOut])
def portfolio(
    account_id: int,
    repo: LotRepository = Depends(_repo),
    session: Session = Depends(get_session),
):
    holdings = repo.holdings(account_id)
    latest = PriceRepository(session).latest(account_id)
    current_price = latest.price if latest else None
    return [
        PortfolioItemOut(
            lot_id=h.lot_id,
            acquisition_date=h.acquisition_date,
            units=h.units,
            remaining_units=h.remaining_units,
            cost_per_unit=h.cost_per_unit,
            cost_basis=h.cost_basis,
            current_price_per_unit=current_price,
            current_value=h.remaining_units * current_price // 1000 if current_price is not None else None,
            unrealized_gain=(h.remaining_units * current_price // 1000) - h.cost_basis if current_price is not None else None,
        )
        for h in holdings
    ]
