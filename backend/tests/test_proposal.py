"""Unit tests for the proposal parser."""
from __future__ import annotations

import pytest
from agent.transport.proposal import parse_proposal, PROPOSAL_PREFIX


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
