from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from stow.db import get_session
from stow.investments.prices import PriceRepository
from stow.investments.schemas import PriceQuoteOut

router = APIRouter(tags=["prices"])


def _repo(session: Session = Depends(get_session)) -> PriceRepository:
    return PriceRepository(session)


@router.post("/prices/fetch/{account_id}", response_model=PriceQuoteOut, status_code=201)
async def fetch_price(account_id: int, repo: PriceRepository = Depends(_repo)):
    try:
        return await repo.fetch(account_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/prices/fetch-all", response_model=list[PriceQuoteOut])
async def fetch_all_prices(repo: PriceRepository = Depends(_repo)):
    return await repo.fetch_all()


@router.get("/prices/latest/{account_id}", response_model=PriceQuoteOut)
def get_latest_price(account_id: int, repo: PriceRepository = Depends(_repo)):
    quote = repo.latest(account_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="No price quote found")
    return quote
