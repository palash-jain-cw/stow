import io
import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

from sqlmodel import select

from stow.models import (
    ImportBatch, StagingRow, MerchantRule,
    AccountGroup, Account, Transaction, Entry,
)


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
    assert matched is not None
    assert matched.account_id == bank_account.id


def test_merchant_rule_no_match(session, bank_account):
    session.add(MerchantRule(pattern="BESCOM*", account_id=bank_account.id))
    session.commit()

    matched = match_merchant_rule(session, "UPI PAYMENT TO SWIGGY")
    assert matched is None


def test_merchant_rule_case_insensitive(session, bank_account):
    session.add(MerchantRule(pattern="swiggy*", account_id=bank_account.id))
    session.commit()

    matched = match_merchant_rule(session, "SWIGGY ORDER 12345")
    assert matched is not None
    assert matched.account_id == bank_account.id


def test_merchant_rule_bare_pattern_matches_substring(session, bank_account):
    session.add(MerchantRule(pattern="swiggy", account_id=bank_account.id))
    session.commit()

    matched = match_merchant_rule(session, "UPI-SWIGGY BANGALORE")
    assert matched is not None
    assert matched.account_id == bank_account.id


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
def mock_parsed_statement():
    return ParsedStatement(
        bank="HDFC Bank",
        statement_from=date(2026, 4, 1),
        statement_to=date(2026, 4, 30),
        rows=[
            ParsedRow(
                date=date(2026, 4, 5),
                amount_paise=120000,
                flow="out",
                description="BESCOM ELECTRICITY",
            ),
            ParsedRow(
                date=date(2026, 4, 10),
                amount_paise=500000,
                flow="in",
                description="SALARY CREDIT",
            ),
        ],
    )


def test_post_imports_creates_batch_and_rows(client, mock_parsed_statement):
    fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")

    with patch(
        "stow.routers.imports.parse_statement_pdf",
        new=AsyncMock(return_value=mock_parsed_statement),
    ):
        r = client.post(
            "/imports",
            files={"file": ("hdfc_april.pdf", fake_pdf, "application/pdf")},
        )

    assert r.status_code == 201
    data = r.json()
    assert data["detected_bank"] == "HDFC Bank"
    assert data["status"] == "ready"
    assert data["row_count"] == 2


def test_upload_rejects_invalid_pdf_bytes(client):
    r = client.post(
        "/imports",
        files={"file": ("bad.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert r.status_code == 422
    assert "pdf" in r.json()["detail"].lower()


def test_import_parser_agent_uses_parsed_statement_on_first_page():
    from stow.import_parsers import ParsedStatement, build_import_parser_agent

    agent = build_import_parser_agent()
    assert agent.output_type is ParsedStatement
    assert agent._max_output_retries == 3


def test_parsed_row_flow_out_is_negative_signed_amount():
    from stow.import_parsers import ParsedRow

    row = ParsedRow(
        date=date(2026, 4, 5),
        amount_paise=120000,
        flow="out",
        description="SWIGGY",
    )
    assert row.signed_amount_paise == -120000


def test_parsed_row_flow_in_is_positive_signed_amount():
    from stow.import_parsers import ParsedRow

    row = ParsedRow(
        date=date(2026, 4, 10),
        amount_paise=500000,
        flow="in",
        description="SALARY",
    )
    assert row.signed_amount_paise == 500000


def test_parsed_row_legacy_signed_amount_infers_flow():
    from stow.import_parsers import ParsedRow

    out_row = ParsedRow(date=date(2026, 4, 5), amount_paise=-120000, description="BESCOM")
    in_row = ParsedRow(date=date(2026, 4, 10), amount_paise=500000, description="SALARY")
    assert out_row.flow == "out"
    assert out_row.signed_amount_paise == -120000
    assert in_row.flow == "in"
    assert in_row.signed_amount_paise == 500000


def test_parse_markdown_debit_credit_table():
    from stow.import_parsers import _parse_debit_credit_table

    table = [
        ["Tran Date", "Chq No", "Particulars", "Debit", "Credit", "Balance", "Init. Br"],
        ["", "", "OPENING BALANCE", "", "", "1705.97", ""],
        ["22-05-2026", "", "UPI/P2A/614217772364/Mr MANOJ /CBIN/UPI/", "", "10000.00", "11705.97", "521"],
        ["23-05-2026", "", "UPI/P2A/123566665387/SHIVAPUTRA", "15.00", "", "11690.97", "521"],
        ["", "", "TRANSACTION TOTAL", "15.00", "10000.00", "", ""],
    ]
    rows, schema = _parse_debit_credit_table(table)
    assert len(rows) == 2
    assert rows[0].flow == "in"
    assert rows[0].amount_paise == 1_000_000
    assert rows[1].flow == "out"
    assert rows[1].amount_paise == 1500
    assert schema is not None

    continuation = [
        ["24-05-2026", "", "UPI/P2M/809958567940/Dominos Pizza", "410.05", "", "9951.92", "521"],
        ["TRANSACTION TOTAL", "1017203.26", "1005315.77"],
    ]
    cont_rows, _ = _parse_debit_credit_table(continuation, schema)
    assert len(cont_rows) == 1
    assert cont_rows[0].flow == "out"
    assert cont_rows[0].amount_paise == 41005


def test_try_parse_statement_from_tables_axis_sample():
    from stow.import_parsers import try_parse_statement_from_tables

    markdown = """
**Statement of Axis Account No: 916010024744783 for the period (From: 22-05-2026  To: 23-05-2026)**

|Tran Date|Chq No|Particulars|Debit|Credit|Balance|Init.<br>Br|
|---|---|---|---|---|---|---|
|||**OPENING BALANCE**|||**1705.97**||
|22-05-2026||UPI/P2A/614217772364/Mr MANOJ /CBIN/UPI/||10000.00|11705.97|521|
|23-05-2026||UPI/P2A/123566665387/SHIVAPUTRA|15.00||11690.97|521|
"""
    with patch(
        "stow.import_parsers.extract_pdf_page_chunks",
        return_value=[{"text": markdown, "metadata": {"page_number": 1}}],
    ):
        parsed = try_parse_statement_from_tables(b"%PDF fake")

    assert parsed is not None
    assert parsed.bank == "Axis Bank"
    assert len(parsed.rows) == 2
    assert parsed.rows[0].signed_amount_paise == 1_000_000
    assert parsed.rows[1].signed_amount_paise == -1500


def test_merge_parsed_pages_combines_rows_and_metadata():
    from stow.import_parsers import ParsedPage, merge_parsed_pages

    pages = [
        ParsedPage(
            bank="Axis Bank",
            statement_from=date(2026, 5, 1),
            statement_to=date(2026, 5, 31),
            rows=[ParsedRow(date=date(2026, 5, 10), amount_paise=-50000, description="SWIGGY")],
        ),
        ParsedPage(
            rows=[ParsedRow(date=date(2026, 5, 11), amount_paise=100000, description="SALARY")],
        ),
    ]
    merged = merge_parsed_pages(pages)
    assert merged.bank == "Axis Bank"
    assert merged.statement_from == date(2026, 5, 1)
    assert len(merged.rows) == 2


@pytest.mark.asyncio
async def test_parse_statement_pdf_batches_two_pages_per_llm_call():
    from stow.import_parsers import ParsedPage, parse_statement_pdf

    batch_one = ParsedPage(
        bank="HDFC Bank",
        statement_from=date(2026, 4, 1),
        statement_to=date(2026, 4, 30),
        rows=[
            ParsedRow(date=date(2026, 4, 5), amount_paise=-10000, description="PAGE1"),
            ParsedRow(date=date(2026, 4, 6), amount_paise=-20000, description="PAGE2"),
        ],
    )

    with patch("stow.import_parsers.try_parse_statement_from_tables", return_value=None):
        with patch(
            "stow.import_parsers.extract_pdf_page_texts",
            return_value=["page one", "page two"],
        ):
            with patch(
                "stow.import_parsers._parse_page_batch",
                new=AsyncMock(return_value=batch_one),
            ) as mock_parse:
                result = await parse_statement_pdf(b"%PDF-1.4")

    assert mock_parse.await_count == 1
    assert len(result.rows) == 2
    assert {row.description for row in result.rows} == {"PAGE1", "PAGE2"}


@pytest.mark.asyncio
async def test_parse_statement_pdf_odd_page_count_uses_final_single_page_batch():
    from stow.import_parsers import ParsedPage, parse_statement_pdf

    batch_one = ParsedPage(
        bank="Axis Bank",
        statement_from=date(2026, 5, 1),
        statement_to=date(2026, 5, 31),
        rows=[ParsedRow(date=date(2026, 5, 10), amount_paise=-50000, description="PAGE1")],
    )
    batch_two = ParsedPage(
        rows=[ParsedRow(date=date(2026, 5, 11), amount_paise=100000, description="PAGE3")],
    )

    with patch("stow.import_parsers.try_parse_statement_from_tables", return_value=None):
        with patch(
            "stow.import_parsers.extract_pdf_page_texts",
            return_value=["page one", "page two", "page three"],
        ):
            with patch(
                "stow.import_parsers._parse_page_batch",
                new=AsyncMock(side_effect=[batch_one, batch_two]),
            ) as mock_parse:
                result = await parse_statement_pdf(b"%PDF-1.4")

    assert mock_parse.await_count == 2
    assert len(result.rows) == 2
    assert {row.description for row in result.rows} == {"PAGE1", "PAGE3"}


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


def test_map_accounts_prefills_miscellaneous_by_flow(session):
    from stow.seed import seed_account_groups

    seed_account_groups(session)

    expense_misc = session.exec(
        select(Account)
        .join(AG, Account.group_id == AG.id)
        .where(AG.name == "Indirect Expenses")
        .where(Account.name == "Miscellaneous")
    ).one()
    income_misc = session.exec(
        select(Account)
        .join(AG, Account.group_id == AG.id)
        .where(AG.name == "Indirect Income")
        .where(Account.name == "Miscellaneous")
    ).one()

    batch = ImportBatch(filename="misc_default.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    debit_row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 1), amount=-50000,
        description="UNKNOWN DEBIT",
    )
    credit_row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 2), amount=25000,
        description="UNKNOWN CREDIT",
    )
    session.add_all([debit_row, credit_row])
    session.commit()

    map_accounts(session, batch.id)
    session.refresh(debit_row)
    session.refresh(credit_row)

    assert debit_row.suggested_account_id == expense_misc.id
    assert credit_row.suggested_account_id == income_misc.id


def test_merchant_rule_applies_tags_on_import(session):
    from stow.seed import seed_account_groups

    seed_account_groups(session)
    expense_misc = session.exec(
        select(Account)
        .join(AG, Account.group_id == AG.id)
        .where(AG.name == "Indirect Expenses")
        .where(Account.name == "Miscellaneous")
    ).one()

    session.add(MerchantRule(
        pattern="ZXY_TAGS_TEST*",
        account_id=expense_misc.id,
        tags=["food", "delivery"],
    ))
    session.commit()

    batch = ImportBatch(filename="tags_test.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 1), amount=-50000,
        description="ZXY_TAGS_TEST ORDER 123",
    )
    session.add(row)
    session.commit()

    map_accounts(session, batch.id)
    session.refresh(row)

    assert row.suggested_account_id == expense_misc.id
    assert row.tags == ["food", "delivery"]


def test_apply_merchant_rules_only_defaults_skips_manual_mapping(session, client):
    from stow.seed import seed_account_groups

    seed_account_groups(session)
    expense_misc = session.exec(
        select(Account)
        .join(AG, Account.group_id == AG.id)
        .where(AG.name == "Indirect Expenses")
        .where(Account.name == "Miscellaneous")
    ).one()
    groceries_grp = AG(name="GroceriesGrp", nature="expense")
    session.add(groceries_grp)
    session.commit()
    session.refresh(groceries_grp)
    groceries = Account(name="Groceries", group_id=groceries_grp.id)
    session.add(groceries)
    session.commit()
    session.refresh(groceries)
    electricity_grp = AG(name="ElectricityGrp", nature="expense")
    session.add(electricity_grp)
    session.commit()
    session.refresh(electricity_grp)
    electricity = Account(name="Electricity", group_id=electricity_grp.id)
    session.add(electricity)
    session.commit()
    session.refresh(electricity)

    batch = ImportBatch(filename="apply_rules.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    misc_row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 1), amount=-10000,
        description="ZXY_APPLY_TEST LUNCH",
        suggested_account_id=expense_misc.id,
    )
    manual_row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 2), amount=-20000,
        description="ZXY_APPLY_TEST DINNER",
        suggested_account_id=electricity.id,
    )
    session.add_all([misc_row, manual_row])
    session.commit()

    session.add(MerchantRule(pattern="ZXY_APPLY_TEST*", account_id=groceries.id, tags=["food"]))
    session.commit()

    r = client.post(f"/imports/{batch.id}/apply-merchant-rules", json={"only_defaults": True})
    assert r.status_code == 200
    data = r.json()
    assert data["updated_count"] == 1

    rows_by_desc = {row["description"]: row for row in data["rows"]}
    assert rows_by_desc["ZXY_APPLY_TEST LUNCH"]["suggested_account_id"] == groceries.id
    assert rows_by_desc["ZXY_APPLY_TEST LUNCH"]["tags"] == ["food"]
    assert rows_by_desc["ZXY_APPLY_TEST DINNER"]["suggested_account_id"] == electricity.id


def test_apply_merchant_rules_by_rule_id(client, session):
    from stow.seed import seed_account_groups

    seed_account_groups(session)
    expense_misc = session.exec(
        select(Account)
        .join(AG, Account.group_id == AG.id)
        .where(AG.name == "Indirect Expenses")
        .where(Account.name == "Miscellaneous")
    ).one()

    rule = MerchantRule(pattern="ZXY_RULE_ID", account_id=expense_misc.id, tags=["misc-tag"])
    session.add(rule)
    session.commit()
    session.refresh(rule)

    batch = ImportBatch(filename="rule_id.pdf", status="ready")
    session.add(batch)
    session.commit()
    session.refresh(batch)

    row = StagingRow(
        batch_id=batch.id, raw_data={},
        date=date(2026, 5, 1), amount=-10000,
        description="ZXY_RULE_ID PAYMENT",
        suggested_account_id=expense_misc.id,
    )
    session.add(row)
    session.commit()

    r = client.post(
        f"/imports/{batch.id}/apply-merchant-rules",
        json={"only_defaults": True, "rule_id": rule.id},
    )
    assert r.status_code == 200
    assert r.json()["updated_count"] == 1
    assert r.json()["rows"][0]["tags"] == ["misc-tag"]


# ---------------------------------------------------------------------------
# Slice 6: GET /imports/{id} and GET /imports/{id}/rows
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_batch(client, mock_parsed_statement):
    fake_pdf = io.BytesIO(b"%PDF fake")
    with patch(
        "stow.routers.imports.parse_statement_pdf",
        new=AsyncMock(return_value=mock_parsed_statement),
    ):
        r = client.post("/imports", files={"file": ("stmt.pdf", fake_pdf, "application/pdf")})
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


def test_confirm_does_not_post_pending_rows_even_with_account(
    client, session, fy, bank_account, expense_account
):
    """Rows must be status=confirmed in DB; pending + suggested_account_id are skipped."""
    batch = ImportBatch(filename="pending_ui_only.pdf", status="ready")
    session.add(batch)
    session.flush()
    session.add_all([
        StagingRow(
            batch_id=batch.id,
            raw_data={},
            date=date(2026, 5, 1),
            amount=-10000,
            description="PENDING_WITH_ACCOUNT",
            suggested_account_id=expense_account.id,
            status="pending",
        ),
        StagingRow(
            batch_id=batch.id,
            raw_data={},
            date=date(2026, 5, 2),
            amount=-20000,
            description="CONFIRMED_ROW",
            suggested_account_id=expense_account.id,
            status="confirmed",
        ),
    ])
    session.commit()

    r = client.post(
        f"/imports/{batch.id}/confirm",
        json={"bank_account_id": bank_account.id, "fy_id": fy.id},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["posted_count"] == 1
    assert data["skipped_count"] == 0


def test_confirm_batch_posts_payment_and_receipt_with_correct_entry_signs(
    session, fy, bank_account, expense_account
):
    from stow.import_pipeline import confirm_batch
    from stow.models import Entry, ImportBatch, StagingRow, Transaction

    batch = ImportBatch(filename="signs.pdf", status="ready")
    session.add(batch)
    session.flush()

    payment = StagingRow(
        batch_id=batch.id,
        raw_data={},
        date=date(2026, 5, 1),
        amount=-120000,
        description="SWIGGY PAYMENT",
        suggested_account_id=expense_account.id,
        status="confirmed",
    )
    receipt = StagingRow(
        batch_id=batch.id,
        raw_data={},
        date=date(2026, 5, 2),
        amount=500000,
        description="SALARY CREDIT",
        suggested_account_id=expense_account.id,
        status="confirmed",
    )
    session.add_all([payment, receipt])
    session.commit()

    result = confirm_batch(session, batch.id, bank_account.id, fy.id)
    assert result.posted_count == 2

    txns = session.exec(
        select(Transaction)
        .where(Transaction.number.like("IMP-202605%"))
        .order_by(Transaction.date)
    ).all()
    assert len(txns) == 2
    assert txns[0].type == "payment"
    assert txns[1].type == "receipt"

    payment_entries = session.exec(
        select(Entry).where(Entry.transaction_id == txns[0].id)
    ).all()
    assert {e.account_id: e.amount for e in payment_entries} == {
        expense_account.id: 120000,
        bank_account.id: -120000,
    }

    receipt_entries = session.exec(
        select(Entry).where(Entry.transaction_id == txns[1].id)
    ).all()
    assert {e.account_id: e.amount for e in receipt_entries} == {
        bank_account.id: 500000,
        expense_account.id: -500000,
    }


# ---------------------------------------------------------------------------
# Slice 10: Merchant rules CRUD — GET/POST/PUT/DELETE /merchant-rules
# ---------------------------------------------------------------------------

def test_merchant_rules_crud(client, bank_account, expense_account):
    # POST
    r = client.post("/merchant-rules", json={
        "pattern": "SWIGGY_CRUD*",
        "account_id": expense_account.id,
        "tags": ["food"],
    })
    assert r.status_code == 201
    rule = r.json()
    assert rule["pattern"] == "SWIGGY_CRUD*"
    assert rule["tags"] == ["food"]
    rule_id = rule["id"]

    # GET list
    r = client.get("/merchant-rules")
    assert r.status_code == 200
    patterns = [x["pattern"] for x in r.json()]
    assert "SWIGGY_CRUD*" in patterns

    # PUT
    r = client.put(f"/merchant-rules/{rule_id}", json={
        "pattern": "SWIGGY_CRUD_UP*",
        "account_id": bank_account.id,
        "tags": ["groceries"],
    })
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
                amount_paise=45000,
                flow="out",
                description=f"{unique} ORDER",
            )
        ],
    )

    with patch("stow.routers.imports.parse_statement_pdf", new=AsyncMock(return_value=parsed)):
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


def test_render_pdf_pages_as_images():
    """Verify PDF pages render as PNG images for vision parsing."""
    import pymupdf
    from stow.import_parsers import _render_pdf_pages_as_images

    # Create a 3-page test PDF
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72 + i * 100), f"Page {i + 1}", fontsize=14)
    doc_bytes = doc.tobytes()
    doc.close()

    images = _render_pdf_pages_as_images(doc_bytes)
    assert len(images) == 3
    for img in images:
        # Verify PNG format
        assert img[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(img) > 1000  # Reasonable image size
