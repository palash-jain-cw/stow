"""Unit tests for the proposal parser and confirm flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.transport.proposal import (
    PROPOSAL_PREFIX,
    confirm_pending_proposal,
    decline_pending_proposal,
    execute_proposal,
    normalize_proposal,
    parse_proposal,
    store_pending,
    try_handle_proposal_action,
)


class TestParseProposal:
    def test_plain_text_returns_no_proposal(self):
        proposal, display = parse_proposal("Just a regular response.")
        assert proposal is None
        assert display == "Just a regular response."

    def test_proposal_line_is_parsed(self):
        text = (
            'PROPOSAL:{"type":"payment","amount_paise":50000}\n\n'
            "Please confirm this transaction."
        )
        proposal, display = parse_proposal(text)
        assert proposal == {"type": "payment", "amount_paise": 50000}
        assert "PROPOSAL:" not in display
        assert "Please confirm" in display

    def test_proposal_line_stripped_from_display(self):
        text = 'PROPOSAL:{"type":"payment","amount_paise":50000}\n\nConfirm?'
        _, display = parse_proposal(text)
        assert not any(line.startswith(PROPOSAL_PREFIX) for line in display.splitlines())

    def test_full_proposal_fields_parsed(self):
        proposal_json = (
            '{"type":"payment","date":"2026-05-16","amount_paise":50000,'
            '"narration":"Electricity bill","from_account_id":5,'
            '"from_account_name":"HDFC Bank","to_account_id":12,'
            '"to_account_name":"Electricity","fy_id":3}'
        )
        text = f"PROPOSAL:{proposal_json}\n\n💸 Payment of ₹500"
        proposal, display = parse_proposal(text)
        assert proposal is not None
        assert proposal["type"] == "payment"
        assert proposal["amount_paise"] == 50000
        assert proposal["from_account_name"] == "HDFC Bank"
        assert proposal["fy_id"] == 3
        assert "💸" in display

    def test_invalid_json_returns_no_proposal(self):
        text = "PROPOSAL:not-valid-json\n\nSome text"
        proposal, display = parse_proposal(text)
        assert proposal is None

    def test_multiline_display_preserved(self):
        text = "PROPOSAL:{}\n\nLine one\nLine two\nLine three"
        proposal, display = parse_proposal(text)
        assert proposal == {}
        assert "Line one" in display
        assert "Line two" in display


class TestNormalizeProposal:
    def test_amount_alias_is_mapped(self):
        raw = {
            "type": "payment",
            "date": "2026-05-16",
            "amount": 50000,
            "from_account_id": 1,
            "to_account_id": 2,
            "fy_id": 1,
        }
        normalized = normalize_proposal(raw)
        assert normalized["amount_paise"] == 50000

    def test_missing_fields_raise(self):
        with pytest.raises(ValueError, match="amount_paise"):
            normalize_proposal({"type": "payment", "date": "2026-05-16"})


class TestProposalActions:
    @pytest.mark.asyncio
    async def test_try_handle_decline(self):
        client = AsyncMock()
        result = await try_handle_proposal_action("decline", client, "http://localhost:8000")
        assert result == "Transaction discarded."

    @pytest.mark.asyncio
    async def test_try_handle_confirm_posts_transaction(self):
        client = AsyncMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"number": "PAY-2026-001", "narration": "Swiggy"}
        client.post = AsyncMock(return_value=response)

        proposal = (
            '{"type":"payment","date":"2026-05-16","amount_paise":50000,'
            '"narration":"Swiggy","from_account_id":1,"to_account_id":2,"fy_id":1}'
        )
        result = await try_handle_proposal_action(
            f"confirm:{proposal}", client, "http://localhost:8000"
        )
        assert "PAY-2026-001" in result
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pending_confirm_flow(self):
        client = AsyncMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"number": "PAY-2026-002", "narration": "Test"}
        client.post = AsyncMock(return_value=response)

        proposal = {
            "type": "payment",
            "date": "2026-05-16",
            "amount_paise": 10000,
            "narration": "Test",
            "from_account_id": 1,
            "to_account_id": 2,
            "fy_id": 1,
        }
        proposal_id = store_pending("42", proposal)
        result = await confirm_pending_proposal("42", proposal_id, client, "http://localhost:8000")
        assert "PAY-2026-002" in result

    def test_decline_pending(self):
        proposal_id = store_pending(
            "7",
            {
                "type": "payment",
                "date": "2026-05-16",
                "amount_paise": 10000,
                "from_account_id": 1,
                "to_account_id": 2,
                "fy_id": 1,
            },
        )
        result = decline_pending_proposal("7", proposal_id)
        assert result == "Transaction discarded."

    @pytest.mark.asyncio
    async def test_execute_proposal_builds_balanced_entries(self):
        client = AsyncMock()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"number": "PAY-2026-003"}
        client.post = AsyncMock(return_value=response)

        await execute_proposal(
            {
                "type": "payment",
                "date": "2026-05-16",
                "amount_paise": 25000,
                "narration": "Coffee",
                "from_account_id": 5,
                "to_account_id": 9,
                "fy_id": 2,
            },
            client,
            "http://localhost:8000",
        )

        payload = client.post.await_args.kwargs["json"]
        assert payload["entries"] == [
            {"account_id": 5, "amount": -25000},
            {"account_id": 9, "amount": 25000},
        ]
