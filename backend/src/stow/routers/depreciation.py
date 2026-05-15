from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from stow.db import get_session
from stow.depreciation import depreciation_summary

router = APIRouter(prefix="/depreciation", tags=["depreciation"])


@router.get("/summary")
def summary(fy_id: int, session: Session = Depends(get_session)):
    from stow.models import FinancialYear
    if not session.get(FinancialYear, fy_id):
        raise HTTPException(status_code=404, detail="Financial year not found")
    return depreciation_summary(session, fy_id)
