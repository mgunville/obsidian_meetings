from __future__ import annotations

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

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    response_text = _extract_text_content(response)

    # Parse and validate the response
    return parse_summary_json(response_text)
