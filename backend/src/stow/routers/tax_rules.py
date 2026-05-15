from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from stow.db import get_session
from stow.models import CapitalGainsTaxRule
from stow.investments.schemas import TaxRuleIn, TaxRuleOut

router = APIRouter(prefix="/tax-rules", tags=["tax-rules"])


@router.get("", response_model=list[TaxRuleOut])
def list_tax_rules(session: Session = Depends(get_session)):
    return session.exec(
        select(CapitalGainsTaxRule).order_by(col(CapitalGainsTaxRule.effective_from))
    ).all()


@router.post("", response_model=TaxRuleOut, status_code=201)
def create_tax_rule(data: TaxRuleIn, session: Session = Depends(get_session)):
    rule = CapitalGainsTaxRule(**data.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule
