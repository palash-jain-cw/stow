from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select
from stow.db import get_session
from stow.models import AccountGroup

router = APIRouter(prefix="/account-groups", tags=["account-groups"])


@router.get("", response_model=list[AccountGroup])
def list_account_groups(session: Session = Depends(get_session)):
    return session.exec(select(AccountGroup).order_by(AccountGroup.sort_order)).all()


@router.post("", response_model=AccountGroup, status_code=201)
def create_account_group(group: AccountGroup, session: Session = Depends(get_session)):
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@router.put("/{group_id}", response_model=AccountGroup)
def update_account_group(group_id: int, data: AccountGroup, session: Session = Depends(get_session)):
    group = session.get(AccountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404)
    for field, value in data.model_dump(exclude_unset=True, exclude={"id"}).items():
        setattr(group, field, value)
    session.commit()
    session.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
def delete_account_group(group_id: int, session: Session = Depends(get_session)):
    group = session.get(AccountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404)
    session.delete(group)
    session.commit()
    return Response(status_code=204)
