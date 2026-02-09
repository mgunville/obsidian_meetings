from __future__ import annotations

import pytest

from meetingctl.summary_parser import SummaryParseError, parse_summary_json


def test_summary_parser_valid_payload() -> None:
    parsed = parse_summary_json(
        """
        {
          "minutes": "Meeting summary",
          "decisions": ["Ship beta"],
          "action_items": ["Prepare rollout plan"]
        }
        """
    )
    assert parsed["minutes"] == "Meeting summary"
    assert parsed["decisions"] == ["Ship beta"]
    assert parsed["action_items"] == ["Prepare rollout plan"]


def test_summary_parser_malformed_json_fails_safely() -> None:
    with pytest.raises(SummaryParseError):
        parse_summary_json("{invalid json")


def test_summary_parser_invalid_schema_fails_safely() -> None:
    with pytest.raises(SummaryParseError):
        parse_summary_json('{"minutes": 1, "decisions": [], "action_items": []}')
