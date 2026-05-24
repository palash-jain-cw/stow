import io
import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from stow.models import (
    ImportBatch, StagingRow, MerchantRule,
    AccountGroup, Account,
)
from stow.main import app
from stow.ai_agent import get_ai_agent


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bank_account(session):
    grp = AccountGroup(name="Test Banks", nature="asset")
    session.add(grp)
    session.commit()
    session.refresh(grp)
    acc = Account(name="HDFC Savings", group_id=grp.id)
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


@pytest.fixture()
def expense_account(session):
    grp = AccountGroup(name="Test Expenses", nature="expense")
    session.add(grp)
    session.commit()
    session.refresh(grp)
    acc = Account(name="Electricity", group_id=grp.id)
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc


# ---------------------------------------------------------------------------
# Slice 1: Models — ImportBatch, StagingRow, MerchantRule can be persisted
# ---------------------------------------------------------------------------

def test_import_batch_can_be_created(session):
    batch = ImportBatch(filename="hdfc_may2026.pdf", status="processing")
    session.add(batch)
    session.commit()
    session.refresh(batch)
    assert batch.id is not None
    assert batch.status == "processing"


def test_staging_row_possible_duplicate_defaults_false(session):
    batch = ImportBatch(filename="test.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id,
        raw_data={"raw": "line"},
        date=date(2026, 5, 1),
        amount=-50000,
        description="BESCOM ELECTRICITY BILL",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.id is not None
    assert row.possible_duplicate is False
    assert row.status == "pending"


def test_merchant_rule_can_be_created(session, bank_account):
    rule = MerchantRule(pattern="ZOMATO*", account_id=bank_account.id)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    assert rule.id is not None
    assert rule.pattern == "ZOMATO*"


# ---------------------------------------------------------------------------
# Slice 2: Merchant rule wildcard matching
# ---------------------------------------------------------------------------

from stow.import_pipeline import match_merchant_rule


def test_merchant_rule_matches_wildcard(session, bank_account):
    session.add(MerchantRule(pattern="BESCOM*", account_id=bank_account.id))
    session.commit()

    matched = match_merchant_rule(session, "BESCOM ELECTRICITY BILL")
    assert matched == bank_account.id


def test_merchant_rule_no_match(session, bank_account):
    session.add(MerchantRule(pattern="BESCOM*", account_id=bank_account.id))
    session.commit()

    matched = match_merchant_rule(session, "UPI PAYMENT TO SWIGGY")
    assert matched is None


def test_merchant_rule_case_insensitive(session, bank_account):
    session.add(MerchantRule(pattern="swiggy*", account_id=bank_account.id))
    session.commit()

    matched = match_merchant_rule(session, "SWIGGY ORDER 12345")
    assert matched == bank_account.id


# ---------------------------------------------------------------------------
# Slice 3: Duplicate detection
# ---------------------------------------------------------------------------

from stow.import_pipeline import detect_duplicates
from stow.models import FinancialYear, Transaction, Entry


@pytest.fixture()
def fy(session):
    fy = FinancialYear(start_date=date(2026, 4, 1), end_date=date(2027, 3, 31))
    session.add(fy)
    session.commit()
    session.refresh(fy)
    return fy


@pytest.fixture()
def posted_txn(session, fy, bank_account, expense_account):
    """A posted transaction: ₹500 debit on 2026-05-10."""
    txn = Transaction(
        number="PAY-2026-001", type="payment",
        date=date(2026, 5, 10), narration="BESCOM bill",
        fy_id=fy.id,
    )
    session.add(txn)
    session.commit()
    session.refresh(txn)
    session.add(Entry(transaction_id=txn.id, account_id=expense_account.id, amount=50000))
    session.add(Entry(transaction_id=txn.id, account_id=bank_account.id, amount=-50000))
    session.commit()
    return txn


def test_exact_duplicate_flagged(session, posted_txn):
    batch = ImportBatch(filename="may.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 10), amount=-50000,
        description="BESCOM",
    )
    session.add(row)
    session.commit()

    detect_duplicates(session, batch.id)
    session.refresh(row)
    assert row.possible_duplicate is True


def test_adjacent_day_duplicate_flagged(session, posted_txn):
    batch = ImportBatch(filename="may2.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 11), amount=-50000,  # +1 day
        description="BESCOM",
    )
    session.add(row)
    session.commit()

    detect_duplicates(session, batch.id)
    session.refresh(row)
    assert row.possible_duplicate is True


def test_different_amount_not_flagged(session, posted_txn):
    batch = ImportBatch(filename="may3.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 10), amount=-99999,  # different amount
        description="OTHER",
    )
    session.add(row)
    session.commit()

    detect_duplicates(session, batch.id)
    session.refresh(row)
    assert row.possible_duplicate is False


# ---------------------------------------------------------------------------
# Slice 4: POST /imports — PDF upload creates batch + staging rows (LLM mocked)
# ---------------------------------------------------------------------------

from stow.import_parsers import ParsedStatement, ParsedRow


@pytest.fixture()
def mock_parse_agent():
    agent = MagicMock()
    result = MagicMock()
    result.data = ParsedStatement(
        bank="HDFC Bank",
        statement_from=date(2026, 4, 1),
        statement_to=date(2026, 4, 30),
        rows=[
            ParsedRow(date=date(2026, 4, 5), amount_paise=-120000, description="BESCOM ELECTRICITY"),
            ParsedRow(date=date(2026, 4, 10), amount_paise=500000, description="SALARY CREDIT"),
        ],
    )
    agent.run = AsyncMock(return_value=result)
    return agent


def test_post_imports_creates_batch_and_rows(client, mock_parse_agent):
    app.dependency_overrides[get_ai_agent] = lambda: mock_parse_agent

    fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")

    with patch("stow.routers.imports.extract_pdf_text", return_value="fake pdf text"):
        try:
            r = client.post(
                "/imports",
                files={"file": ("hdfc_april.pdf", fake_pdf, "application/pdf")},
            )
        finally:
            app.dependency_overrides.pop(get_ai_agent, None)

    assert r.status_code == 201
    data = r.json()
    assert data["detected_bank"] == "HDFC Bank"
    assert data["status"] == "ready"
    assert data["row_count"] == 2


# ---------------------------------------------------------------------------
# Slice 5: Account mapping — merchant rule takes priority over LLM suggestion
# ---------------------------------------------------------------------------

from stow.import_pipeline import map_accounts
from stow.models import AccountGroup as AG


@pytest.fixture()
def two_accounts(session):
    grp = AG(name="MapTest", nature="expense")
    session.add(grp)
    session.commit()
    session.refresh(grp)
    from stow.models import Account as Acc
    a1 = Acc(name="Electricity", group_id=grp.id)
    a2 = Acc(name="Groceries", group_id=grp.id)
    session.add_all([a1, a2])
    session.commit()
    session.refresh(a1)
    session.refresh(a2)
    return a1, a2


def test_merchant_rule_overrides_llm_suggestion(session, two_accounts):
    electricity_acc, groceries_acc = two_accounts

    # Rule: TNEB_ELEC* → electricity (unique pattern to avoid cross-test pollution)
    session.add(MerchantRule(pattern="TNEB_ELEC*", account_id=electricity_acc.id))
    session.commit()

    batch = ImportBatch(filename="map_test.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 1), amount=-50000,
        description="TNEB_ELEC BILL MAY26",
        suggested_account_id=groceries_acc.id,  # LLM got it wrong
    )
    session.add(row)
    session.commit()

    map_accounts(session, batch.id)
    session.refresh(row)

    assert row.suggested_account_id == electricity_acc.id  # rule wins


def test_llm_suggestion_used_when_no_rule(session, two_accounts):
    electricity_acc, groceries_acc = two_accounts

    batch = ImportBatch(filename="map_test2.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 1), amount=-30000,
        description="BIGBASKET ORDER",
        suggested_account_id=groceries_acc.id,
    )
    session.add(row)
    session.commit()

    map_accounts(session, batch.id)
    session.refresh(row)

    assert row.suggested_account_id == groceries_acc.id  # LLM suggestion kept


# ---------------------------------------------------------------------------
# Slice 6: GET /imports/{id} and GET /imports/{id}/rows
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_batch(client, mock_parse_agent):
    app.dependency_overrides[get_ai_agent] = lambda: mock_parse_agent
    fake_pdf = io.BytesIO(b"%PDF fake")
    with patch("stow.routers.imports.extract_pdf_text", return_value="text"):
        r = client.post("/imports", files={"file": ("stmt.pdf", fake_pdf, "application/pdf")})
    app.dependency_overrides.pop(get_ai_agent, None)
    return r.json()


def test_get_batch_returns_details_and_counts(client, seeded_batch):
    r = client.get(f"/imports/{seeded_batch['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == seeded_batch["id"]
    assert data["detected_bank"] == "HDFC Bank"
    assert data["counts"]["pending"] == 2
    assert data["counts"]["confirmed"] == 0


def test_get_batch_rows_returns_staging_rows(client, seeded_batch):
    r = client.get(f"/imports/{seeded_batch['id']}/rows")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    descriptions = {row["description"] for row in rows}
    assert "BESCOM ELECTRICITY" in descriptions
    assert "SALARY CREDIT" in descriptions


# ---------------------------------------------------------------------------
# Slice 7: PUT /imports/{id}/rows/{row_id} — update status / account / narration
# ---------------------------------------------------------------------------

def test_put_row_updates_status_and_narration(client, seeded_batch, bank_account):
    rows = client.get(f"/imports/{seeded_batch['id']}/rows").json()
    row_id = rows[0]["id"]

    r = client.put(
        f"/imports/{seeded_batch['id']}/rows/{row_id}",
        json={"status": "confirmed", "narration_override": "Electricity bill May", "suggested_account_id": bank_account.id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "confirmed"
    assert data["narration_override"] == "Electricity bill May"
    assert data["suggested_account_id"] == bank_account.id


# ---------------------------------------------------------------------------
# Slice 8: POST /imports/{id}/rows/{row_id}/match — reconcile to existing txn
# ---------------------------------------------------------------------------

def test_match_row_sets_reconciled(client, seeded_batch, session, fy, bank_account, expense_account):
    # Create a posted transaction to match against
    from stow.models import Transaction as Txn, Entry as E
    txn = Txn(number="PAY-MATCH-001", type="payment", date=date(2026, 4, 5),
               narration="BESCOM", fy_id=fy.id)
    session.add(txn)
    session.commit()
    session.refresh(txn)
    session.add(E(transaction_id=txn.id, account_id=expense_account.id, amount=120000))
    session.add(E(transaction_id=txn.id, account_id=bank_account.id, amount=-120000))
    session.commit()

    rows = client.get(f"/imports/{seeded_batch['id']}/rows").json()
    row_id = rows[0]["id"]

    r = client.post(
        f"/imports/{seeded_batch['id']}/rows/{row_id}/match",
        json={"transaction_id": txn.id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "reconciled"
    assert data["matched_transaction_id"] == txn.id


# ---------------------------------------------------------------------------
# Slice 9: POST /imports/{id}/confirm — confirmed rows → posted transactions
# ---------------------------------------------------------------------------

def test_confirm_batch_posts_transactions(client, seeded_batch, session, fy, bank_account, expense_account):
    rows = client.get(f"/imports/{seeded_batch['id']}/rows").json()

    # Confirm both rows with account assignments
    for row in rows:
        client.put(
            f"/imports/{seeded_batch['id']}/rows/{row['id']}",
            json={
                "status": "confirmed",
                "suggested_account_id": expense_account.id,
                "narration_override": row["description"],
            },
        )

    r = client.post(
        f"/imports/{seeded_batch['id']}/confirm",
        json={"bank_account_id": bank_account.id, "fy_id": fy.id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["posted_count"] == 2
    assert data["skipped_count"] == 0
    assert data["status"] == "posted"


# ---------------------------------------------------------------------------
# Slice 10: Merchant rules CRUD — GET/POST/PUT/DELETE /merchant-rules
# ---------------------------------------------------------------------------

def test_merchant_rules_crud(client, bank_account, expense_account):
    # POST
    r = client.post("/merchant-rules", json={"pattern": "SWIGGY_CRUD*", "account_id": expense_account.id})
    assert r.status_code == 201
    rule = r.json()
    assert rule["pattern"] == "SWIGGY_CRUD*"
    rule_id = rule["id"]

    # GET list
    r = client.get("/merchant-rules")
    assert r.status_code == 200
    patterns = [x["pattern"] for x in r.json()]
    assert "SWIGGY_CRUD*" in patterns

    # PUT
    r = client.put(f"/merchant-rules/{rule_id}", json={"pattern": "SWIGGY_CRUD_UP*", "account_id": bank_account.id})
    assert r.status_code == 200
    assert r.json()["pattern"] == "SWIGGY_CRUD_UP*"

    # DELETE
    r = client.delete(f"/merchant-rules/{rule_id}")
    assert r.status_code == 204

    # Verify gone
    r = client.get("/merchant-rules")
    patterns = [x["pattern"] for x in r.json()]
    assert "SWIGGY_CRUD_UP*" not in patterns


# ---------------------------------------------------------------------------
# confirm_batch skips unmapped rows instead of posting bank-to-bank
# ---------------------------------------------------------------------------

def test_confirm_skips_rows_without_account_mapping(
    client, session, fy, bank_account, expense_account
):
    batch = ImportBatch(filename="skip_test.pdf", status="ready")
    session.add(batch)
    session.flush()
    mapped = StagingRow(
        batch_id=batch.id,
        raw_data={},
        date=date(2026, 5, 1),
        amount=-10000,
        description="SKIP_TEST_MAPPED",
        suggested_account_id=expense_account.id,
        status="confirmed",
    )
    unmapped = StagingRow(
        batch_id=batch.id,
        raw_data={},
        date=date(2026, 5, 2),
        amount=-20000,
        description="SKIP_TEST_UNMAPPED",
        status="confirmed",
    )
    session.add_all([mapped, unmapped])
    session.commit()

    r = client.post(
        f"/imports/{batch.id}/confirm",
        json={"bank_account_id": bank_account.id, "fy_id": fy.id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["posted_count"] == 1
    assert data["skipped_count"] == 1
    assert any("no account mapped" in s["reason"] for s in data["skipped"])


def test_upload_applies_merchant_rules(session, client, expense_account):
    from stow.import_parsers import ParsedRow, ParsedStatement

    unique = "ZXY_UPLOAD_RULE_TEST"
    session.add(MerchantRule(pattern=f"{unique}*", account_id=expense_account.id))
    session.commit()

    parsed = ParsedStatement(
        bank="HDFC Bank",
        statement_from=date(2026, 4, 1),
        statement_to=date(2026, 4, 30),
        rows=[
            ParsedRow(
                date=date(2026, 4, 10),
                amount_paise=-45000,
                description=f"{unique} ORDER",
            )
        ],
    )

    mock_agent = MagicMock()
    with patch("stow.routers.imports.parse_statement", new=AsyncMock(return_value=parsed)):
        with patch("stow.routers.imports.extract_pdf_text", return_value="fake"):
            with patch("stow.routers.imports.get_ai_agent", return_value=mock_agent):
                r = client.post(
                    "/imports",
                    files={"file": ("stmt.pdf", b"%PDF fake", "application/pdf")},
                )
    assert r.status_code == 201
    batch_id = r.json()["id"]
    rows = client.get(f"/imports/{batch_id}/rows").json()
    assert rows[0]["suggested_account_id"] == expense_account.id


def test_match_bank_account_helper():
    from stow.import_pipeline import match_bank_account

    accounts = [
        {"id": 1, "name": "Union Bank Savings Account", "group_name": "Bank Accounts", "is_archived": False},
        {"id": 2, "name": "Axis Bank Savings Account", "group_name": "Bank Accounts", "is_archived": False},
    ]
    matched = match_bank_account(accounts, "Union Bank of India")
    assert matched is not None
    assert matched["id"] == 1
