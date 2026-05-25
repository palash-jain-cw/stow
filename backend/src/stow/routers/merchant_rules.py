from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from stow.db import get_session
from stow.models import MerchantRule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/merchant-rules", tags=["merchant-rules"])


class RuleIn(BaseModel):
    pattern: str
    account_id: int
    tags: list[str] = Field(default_factory=list)


class RuleOut(BaseModel):
    id: int
    pattern: str
    account_id: int
    tags: list[str] = Field(default_factory=list)


def _rule_out(rule: MerchantRule) -> RuleOut:
    return RuleOut(
        id=rule.id or 0,
        pattern=rule.pattern,
        account_id=rule.account_id,
        tags=list(rule.tags) if rule.tags else [],
    )


@router.get("", response_model=list[RuleOut])
def list_rules(session: Session = Depends(get_session)):
    return [_rule_out(r) for r in session.exec(select(MerchantRule)).all()]


@router.post("", status_code=201, response_model=RuleOut)
def create_rule(body: RuleIn, session: Session = Depends(get_session)):
    tags = [t.strip() for t in body.tags if t.strip()] or None
    rule = MerchantRule(pattern=body.pattern.strip(), account_id=body.account_id, tags=tags)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    logger.info("Created merchant rule id=%s pattern=%r account_id=%s tags=%s", rule.id, rule.pattern, rule.account_id, tags)
    return _rule_out(rule)


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, session: Session = Depends(get_session)):
    rule = session.get(MerchantRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Merchant rule not found")
    rule.pattern = body.pattern.strip()
    rule.account_id = body.account_id
    rule.tags = [t.strip() for t in body.tags if t.strip()] or None
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _rule_out(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(MerchantRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Merchant rule not found")
    session.delete(rule)
    session.commit()
    return Response(status_code=204)
