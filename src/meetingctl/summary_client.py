from __future__ import annotations

import os

import anthropic

from meetingctl.summary_parser import parse_summary_json


def _extract_text_content(response: object) -> str:
    content = getattr(response, "content", None)
    if not isinstance(content, list) or not content:
        raise RuntimeError("LLM response had no content blocks.")
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    raise RuntimeError("LLM response did not include a text content block.")


def _summary_model_candidates() -> list[str]:
    raw = os.environ.get("MEETINGCTL_SUMMARY_MODEL", "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [
        "claude-3-5-sonnet-latest",
        "claude-3-5-sonnet-20241022",
    ]


def _is_model_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "not_found_error" in text and "model:" in text


def generate_summary(transcript: str, *, api_key: str) -> dict[str, object]:
    """Generate meeting summary from transcript using LLM API.

    Args:
        transcript: Meeting transcript text
        api_key: Anthropic API key

    Returns:
        Parsed summary dictionary with minutes, decisions, and action_items

    Raises:
        ValueError: If API key is missing
        SummaryParseError: If LLM response is malformed
    """
    if not api_key:
        raise ValueError("API key is required")

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a meeting assistant. Given the following meeting transcript, generate a structured summary.

Transcript:
{transcript}

Respond with ONLY a JSON object in this exact format:
{{
  "minutes": "A brief summary of the meeting (2-3 sentences)",
  "decisions": ["Decision 1", "Decision 2"],
  "action_items": ["Action item 1", "Action item 2"]
}}

If there are no decisions or action items, use empty arrays.
"""

    last_exc: Exception | None = None
    response = None
    for model in _summary_model_candidates():
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
            break
        except Exception as exc:
            if _is_model_not_found_error(exc):
                last_exc = exc
                continue
            raise

    if response is None:
        candidate_list = ", ".join(_summary_model_candidates())
        if last_exc is not None:
            raise RuntimeError(
                f"No configured summary model was available ({candidate_list}). "
                "Set MEETINGCTL_SUMMARY_MODEL to a model your Anthropic account can access."
            ) from last_exc
        raise RuntimeError(
            "No summary model candidates configured. "
            "Set MEETINGCTL_SUMMARY_MODEL to a valid Anthropic model."
        )

    response_text = _extract_text_content(response)

    # Parse and validate the response
    return parse_summary_json(response_text)
