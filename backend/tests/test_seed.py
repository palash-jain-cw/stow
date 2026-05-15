from sqlmodel import Session, select
from stow.models import AccountGroup
from stow.seed import seed_account_groups


def test_seed_creates_expected_groups(session: Session):
    seed_account_groups(session)
    groups = session.exec(select(AccountGroup)).all()
    names = {g.name for g in groups}
    assert "Capital Account" in names
    assert "Bank Accounts" in names
    assert "Duties & Taxes" in names
    assert "Credit Cards" in names
    assert "Input CGST" in names
    assert "TDS Receivable" in names


def test_seed_is_idempotent(session: Session):
    seed_account_groups(session)
    count_after_first = len(session.exec(select(AccountGroup)).all())

    seed_account_groups(session)
    count_after_second = len(session.exec(select(AccountGroup)).all())

    assert count_after_first == count_after_second
