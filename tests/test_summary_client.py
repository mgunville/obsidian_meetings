from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from meetingctl.summary_client import generate_summary
from meetingctl.summary_parser import SummaryParseError


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_sends_transcript_to_llm(mock_anthropic_class: MagicMock) -> None:
    """Test that generate_summary sends transcript to LLM API."""
    # Setup mock
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = """
    {
        "minutes": "Team discussed Q1 roadmap priorities.",
        "decisions": ["Focus on feature X first"],
        "action_items": ["Alice to draft spec", "Bob to review"]
    }
    """
    mock_client.messages.create.return_value = mock_response

    # Call function
    transcript = "We should focus on feature X in Q1. Alice will draft the spec. Bob will review."
    result = generate_summary(transcript, api_key="test-key")

    # Verify API was called
    assert mock_client.messages.create.called
    call_kwargs = mock_client.messages.create.call_args[1]

    # Check that transcript was sent
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert transcript in messages[0]["content"]

    # Verify result structure
    assert result["minutes"] == "Team discussed Q1 roadmap priorities."
    assert result["decisions"] == ["Focus on feature X first"]
    assert result["action_items"] == ["Alice to draft spec", "Bob to review"]


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_handles_malformed_json(mock_anthropic_class: MagicMock) -> None:
    """Test that generate_summary fails safely on malformed JSON response."""
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "This is not valid JSON"
    mock_client.messages.create.return_value = mock_response

    with pytest.raises(SummaryParseError):
        generate_summary("Test transcript", api_key="test-key")


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_uses_api_key_from_param(mock_anthropic_class: MagicMock) -> None:
    """Test that generate_summary uses API key from parameter."""
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = '{"minutes": "Test", "decisions": [], "action_items": []}'
    mock_client.messages.create.return_value = mock_response

    generate_summary("Test", api_key="my-secret-key")

    # Verify client was initialized with API key
    mock_anthropic_class.assert_called_once_with(api_key="my-secret-key")


def test_generate_summary_requires_api_key() -> None:
    """Test that generate_summary requires an API key."""
    with pytest.raises((ValueError, RuntimeError)):
        generate_summary("Test transcript", api_key="")
