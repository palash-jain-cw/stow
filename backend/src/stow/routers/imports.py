from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from pydantic_ai import Agent
from sqlmodel import Session, select

from stow.ai_agent import get_ai_agent
from stow.db import get_session
from stow.import_parsers import ParsedStatement, extract_pdf_text, parse_statement
from stow.import_pipeline import detect_duplicates, confirm_batch, map_accounts
from stow.models import ImportBatch, StagingRow, Transaction, Entry, FinancialYear

router = APIRouter(prefix="/imports", tags=["imports"])


class BatchOut(BaseModel):
    id: int
    filename: str
    detected_bank: str | None
    statement_from: str | None
    statement_to: str | None
    status: str
    row_count: int


class StatusCounts(BaseModel):
    pending: int
    confirmed: int
    discarded: int
    reconciled: int


class BatchDetailOut(BaseModel):
    id: int
    filename: str
    detected_bank: str | None
    statement_from: str | None
    statement_to: str | None
    bank_account_id: int | None
    status: str
    counts: StatusCounts


class StagingRowOut(BaseModel):
    id: int
    batch_id: int
    date: str
    amount: int
    description: str
    suggested_account_id: int | None
    status: str
    narration_override: str | None
    tags: list | None
    possible_duplicate: bool
    matched_transaction_id: int | None


@router.post("", status_code=201, response_model=BatchOut)
async def upload_statement(
    file: UploadFile,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_ai_agent),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported")

    file_bytes = await file.read()
    pdf_text = extract_pdf_text(file_bytes)

    parsed: ParsedStatement = await parse_statement(agent, pdf_text)

    batch = ImportBatch(
        filename=file.filename,
        detected_bank=parsed.bank,
        statement_from=parsed.statement_from,
        statement_to=parsed.statement_to,
        status="ready",
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)

    for row in parsed.rows:
        session.add(StagingRow(
            batch_id=batch.id,
            raw_data=row.model_dump(mode="json"),
            date=row.date,
            amount=row.amount_paise,
            description=row.description,
        ))
    session.commit()

    detect_duplicates(session, batch.id)
    map_accounts(session, batch.id)

    row_count = session.exec(
        select(StagingRow).where(StagingRow.batch_id == batch.id)
    ).all()

    return BatchOut(
        id=batch.id,
        filename=batch.filename,
        detected_bank=batch.detected_bank,
        statement_from=batch.statement_from.isoformat() if batch.statement_from else None,
        statement_to=batch.statement_to.isoformat() if batch.statement_to else None,
        status=batch.status,
        row_count=len(row_count),
    )


@router.get("/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: int, session: Session = Depends(get_session)):
    batch = session.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    rows = session.exec(
        select(StagingRow).where(StagingRow.batch_id == batch_id)
    ).all()

    counts = StatusCounts(
        pending=sum(1 for r in rows if r.status == "pending"),
        confirmed=sum(1 for r in rows if r.status == "confirmed"),
        discarded=sum(1 for r in rows if r.status == "discarded"),
        reconciled=sum(1 for r in rows if r.status == "reconciled"),
    )

    return BatchDetailOut(
        id=batch.id,
        filename=batch.filename,
        detected_bank=batch.detected_bank,
        statement_from=batch.statement_from.isoformat() if batch.statement_from else None,
        statement_to=batch.statement_to.isoformat() if batch.statement_to else None,
        bank_account_id=batch.bank_account_id,
        status=batch.status,
        counts=counts,
    )


@router.get("/{batch_id}/rows", response_model=list[StagingRowOut])
def get_batch_rows(
    batch_id: int,
    status: str | None = None,
    session: Session = Depends(get_session),
):
    batch = session.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")

    query = select(StagingRow).where(StagingRow.batch_id == batch_id)
    if status:
        query = query.where(StagingRow.status == status)

    rows = session.exec(query).all()
    return [
        StagingRowOut(
            id=r.id,
            batch_id=r.batch_id,
            date=r.date.isoformat(),
            amount=r.amount,
            description=r.description,
            suggested_account_id=r.suggested_account_id,
            status=r.status,
            narration_override=r.narration_override,
            tags=r.tags,
            possible_duplicate=r.possible_duplicate,
            matched_transaction_id=r.matched_transaction_id,
        )
        for r in rows
    ]


class RowUpdateIn(BaseModel):
    status: str | None = None
    suggested_account_id: int | None = None
    narration_override: str | None = None
    tags: list | None = None


class MatchIn(BaseModel):
    transaction_id: int


class ConfirmIn(BaseModel):
    bank_account_id: int
    fy_id: int | None = None


class ConfirmOut(BaseModel):
    posted_count: int
    skipped_count: int
    skipped: list[dict[str, str | int]]
    status: str


def _row_out(r: StagingRow) -> StagingRowOut:
    return StagingRowOut(
        id=r.id, batch_id=r.batch_id, date=r.date.isoformat(),
        amount=r.amount, description=r.description,
        suggested_account_id=r.suggested_account_id, status=r.status,
        narration_override=r.narration_override, tags=r.tags,
        possible_duplicate=r.possible_duplicate,
        matched_transaction_id=r.matched_transaction_id,
    )


@router.put("/{batch_id}/rows/{row_id}", response_model=StagingRowOut)
def update_row(
    batch_id: int,
    row_id: int,
    body: RowUpdateIn,
    session: Session = Depends(get_session),
):
    row = session.get(StagingRow, row_id)
    if not row or row.batch_id != batch_id:
        raise HTTPException(status_code=404, detail="Row not found")
    if body.status is not None:
        row.status = body.status
    if body.suggested_account_id is not None:
        row.suggested_account_id = body.suggested_account_id
    if body.narration_override is not None:
        row.narration_override = body.narration_override
    if body.tags is not None:
        row.tags = body.tags
    session.add(row)
    session.commit()
    session.refresh(row)
    return _row_out(row)


@router.post("/{batch_id}/rows/{row_id}/match", response_model=StagingRowOut)
def match_row(
    batch_id: int,
    row_id: int,
    body: MatchIn,
    session: Session = Depends(get_session),
):
    row = session.get(StagingRow, row_id)
    if not row or row.batch_id != batch_id:
        raise HTTPException(status_code=404, detail="Row not found")
    txn = session.get(Transaction, body.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    row.matched_transaction_id = body.transaction_id
    row.status = "reconciled"
    session.add(row)
    session.commit()
    session.refresh(row)
    return _row_out(row)


@router.post("/{batch_id}/confirm", response_model=ConfirmOut)
def confirm(
    batch_id: int,
    body: ConfirmIn,
    session: Session = Depends(get_session),
):
    batch = session.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    try:
        result = confirm_batch(session, batch_id, body.bank_account_id, body.fy_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ConfirmOut(
        posted_count=result.posted_count,
        skipped_count=result.skipped_count,
        skipped=result.skipped,
        status="posted" if result.posted_count else "ready",
    )
