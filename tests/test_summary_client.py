from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from meetingctl.summary_client import generate_summary


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
    """Test that generate_summary coerces malformed responses instead of failing."""
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "This is not valid JSON"
    mock_client.messages.create.return_value = mock_response

    parsed = generate_summary("Test transcript", api_key="test-key")
    assert parsed["minutes"] == "This is not valid JSON"
    assert parsed["decisions"] == []
    assert parsed["action_items"] == []


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_repairs_malformed_json_with_second_pass(
    mock_anthropic_class: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    first_response = MagicMock()
    first_response.content = [SimpleNamespace(text="Not JSON output")]
    second_response = MagicMock()
    second_response.content = [
        SimpleNamespace(text='{"minutes":"Recovered","decisions":["D1"],"action_items":["A1"]}')
    ]
    mock_client.messages.create.side_effect = [first_response, second_response]

    parsed = generate_summary("Test transcript", api_key="test-key")
    assert parsed["minutes"] == "Recovered"
    assert parsed["decisions"] == ["D1"]
    assert parsed["action_items"] == ["A1"]
    assert mock_client.messages.create.call_count == 2


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_coerces_when_repair_is_still_not_json(
    mock_anthropic_class: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    first_response = MagicMock()
    first_response.content = [SimpleNamespace(text="Not JSON output")]
    second_response = MagicMock()
    second_response.content = [SimpleNamespace(text="Still not JSON after repair")]
    mock_client.messages.create.side_effect = [first_response, second_response]

    parsed = generate_summary("Test transcript", api_key="test-key")
    assert parsed["minutes"] == "Still not JSON after repair"
    assert parsed["decisions"] == []
    assert parsed["action_items"] == []
    assert mock_client.messages.create.call_count == 2


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_coerces_action_item_dicts_from_repair(
    mock_anthropic_class: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    first_response = MagicMock()
    first_response.content = [SimpleNamespace(text="Not JSON output")]
    second_response = MagicMock()
    second_response.content = [
        SimpleNamespace(
            text='{"minutes":"Recovered","decisions":["D1"],"action_items":[{"owner":"Alex","task":"Send recap","due":"2026-03-01"}]}'
        )
    ]
    mock_client.messages.create.side_effect = [first_response, second_response]

    parsed = generate_summary("Test transcript", api_key="test-key")
    assert parsed["minutes"] == "Recovered"
    assert parsed["decisions"] == ["D1"]
    assert parsed["action_items"] == ["Owner: Alex; Task: Send recap; Due: 2026-03-01"]


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
    mock_anthropic_class.assert_called_once()
    kwargs = mock_anthropic_class.call_args.kwargs
    assert kwargs["api_key"] == "my-secret-key"


@patch("meetingctl.summary_client.subprocess.run")
@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_resolves_api_key_from_op_ref_param(
    mock_anthropic_class: MagicMock, mock_subprocess_run: MagicMock
) -> None:
    mock_subprocess_run.return_value = SimpleNamespace(stdout="resolved-key\n")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [SimpleNamespace(text='{"minutes":"ok","decisions":[],"action_items":[]}')]
    mock_client.messages.create.return_value = mock_response

    generate_summary("Test", api_key="op://Private/Anthropic/api_key")

    mock_subprocess_run.assert_called_once()
    mock_anthropic_class.assert_called_once()
    kwargs = mock_anthropic_class.call_args.kwargs
    assert kwargs["api_key"] == "resolved-key"


@patch("meetingctl.summary_client.subprocess.run")
@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_resolves_api_key_from_env_op_ref(
    mock_anthropic_class: MagicMock,
    mock_subprocess_run: MagicMock,
    monkeypatch,
) -> None:
    mock_subprocess_run.return_value = SimpleNamespace(stdout="resolved-from-env\n")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [SimpleNamespace(text='{"minutes":"ok","decisions":[],"action_items":[]}')]
    mock_client.messages.create.return_value = mock_response
    monkeypatch.setenv("MEETINGCTL_ANTHROPIC_API_KEY_OP_REF", "op://Private/Anthropic/api_key")

    generate_summary("Test", api_key="")

    mock_subprocess_run.assert_called_once()
    mock_anthropic_class.assert_called_once()
    kwargs = mock_anthropic_class.call_args.kwargs
    assert kwargs["api_key"] == "resolved-from-env"


def test_generate_summary_requires_api_key() -> None:
    """Test that generate_summary requires an API key."""
    with pytest.raises((ValueError, RuntimeError)):
        generate_summary("Test transcript", api_key="")


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_fails_when_response_content_empty(mock_anthropic_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = []
    mock_client.messages.create.return_value = mock_response

    with pytest.raises(RuntimeError, match="no content blocks"):
        generate_summary("Test transcript", api_key="test-key")


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_fails_when_no_text_block(mock_anthropic_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    block = MagicMock()
    block.text = ""
    mock_response = MagicMock()
    mock_response.content = [block]
    mock_client.messages.create.return_value = mock_response

    with pytest.raises(RuntimeError, match="did not include a text content block"):
        generate_summary("Test transcript", api_key="test-key")


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_falls_back_when_model_not_found(
    mock_anthropic_class: MagicMock, monkeypatch
) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    def _create(**kwargs):
        model = kwargs.get("model")
        if model == "bad-model":
            raise RuntimeError(
                "Error code: 404 - {'type':'error','error':{'type':'not_found_error','message':'model: bad-model'}}"
            )
        response = MagicMock()
        response.content = [SimpleNamespace(text='{"minutes":"ok","decisions":[],"action_items":[]}')]
        return response

    mock_client.messages.create.side_effect = _create
    monkeypatch.setenv("MEETINGCTL_SUMMARY_MODEL", "bad-model,claude-3-5-sonnet-latest")

    result = generate_summary("Test transcript", api_key="test-key")
    assert result["minutes"] == "ok"


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_errors_when_all_models_not_found(
    mock_anthropic_class: MagicMock, monkeypatch
) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError(
        "Error code: 404 - {'type':'error','error':{'type':'not_found_error','message':'model: missing'}}"
    )
    monkeypatch.setenv("MEETINGCTL_SUMMARY_MODEL", "missing-a,missing-b")

    with pytest.raises(RuntimeError, match="No configured summary model was available"):
        generate_summary("Test transcript", api_key="test-key")


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_accepts_fenced_json_response(mock_anthropic_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [
        SimpleNamespace(
            text="""Here is the summary:
```json
{"minutes":"ok","decisions":[],"action_items":[]}
```"""
        )
    ]
    mock_client.messages.create.return_value = mock_response

    result = generate_summary("Test transcript", api_key="test-key")
    assert result["minutes"] == "ok"


@patch("meetingctl.summary_client.anthropic.Anthropic")
def test_generate_summary_accepts_prose_wrapped_json(mock_anthropic_class: MagicMock) -> None:
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [
        SimpleNamespace(
            text='Summary follows: {"minutes":"ok","decisions":[],"action_items":[]} thanks.'
        )
    ]
    mock_client.messages.create.return_value = mock_response

    result = generate_summary("Test transcript", api_key="test-key")
    assert result["minutes"] == "ok"
