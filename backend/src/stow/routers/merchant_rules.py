from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from stow.db import get_session
from stow.models import MerchantRule

router = APIRouter(prefix="/merchant-rules", tags=["merchant-rules"])


class RuleIn(BaseModel):
    pattern: str
    account_id: int


class RuleOut(BaseModel):
    id: int
    pattern: str
    account_id: int


@router.get("", response_model=list[RuleOut])
def list_rules(session: Session = Depends(get_session)):
    return session.exec(select(MerchantRule)).all()


@router.post("", status_code=201, response_model=RuleOut)
def create_rule(body: RuleIn, session: Session = Depends(get_session)):
    rule = MerchantRule(pattern=body.pattern, account_id=body.account_id)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, session: Session = Depends(get_session)):
    rule = session.get(MerchantRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Merchant rule not found")
    rule.pattern = body.pattern
    rule.account_id = body.account_id
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(MerchantRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Merchant rule not found")
    session.delete(rule)
    session.commit()
    return Response(status_code=204)
