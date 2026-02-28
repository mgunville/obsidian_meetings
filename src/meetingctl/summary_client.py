from __future__ import annotations

import json
import os
import re
import subprocess

import anthropic

from meetingctl.summary_parser import SummaryParseError, parse_summary_json


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


def _extract_candidate_json(raw_text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_text, flags=re.IGNORECASE)
    if fenced:
        return fenced.group(1)

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start >= 0 and end > start:
        return raw_text[start : end + 1]
    return raw_text


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", stripped, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if stripped.lower().startswith("```json"):
        body = stripped[len("```json") :].lstrip()
        if body.endswith("```"):
            body = body[:-3]
        return body.strip()
    if stripped.startswith("```"):
        body = stripped[3:].lstrip()
        if body.endswith("```"):
            body = body[:-3]
        return body.strip()
    return stripped


def _extract_minutes_from_jsonish(text: str) -> str | None:
    match = re.search(r'"minutes"\s*:\s*"', text)
    if not match:
        return None
    idx = match.end()
    chunks: list[str] = []
    escaped = False
    while idx < len(text):
        char = text[idx]
        if escaped:
            chunks.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
            chunks.append(char)
        elif char == '"':
            raw = "".join(chunks)
            try:
                decoded = json.loads(f'"{raw}"')
            except json.JSONDecodeError:
                decoded = raw.replace("\\n", "\n").replace('\\"', '"')
            cleaned = decoded.strip()
            return cleaned or None
        else:
            chunks.append(char)
        idx += 1
    if chunks:
        raw = "".join(chunks)
        decoded = raw.replace("\\n", "\n").replace('\\"', '"')
        cleaned = decoded.strip().rstrip('",')
        return cleaned or None
    return None


def _extract_embedded_summary(payload_text: str) -> dict[str, object] | None:
    stripped = _strip_markdown_fence(payload_text)
    candidates = [stripped]
    extracted = _extract_candidate_json(stripped)
    if extracted != stripped:
        candidates.append(extracted)
    for candidate in candidates:
        if '"minutes"' not in candidate and "'minutes'" not in candidate:
            continue
        try:
            return parse_summary_json(candidate)
        except SummaryParseError:
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                return {
                    "minutes": loaded.get("minutes", ""),
                    "decisions": loaded.get("decisions", []),
                    "action_items": loaded.get("action_items", []),
                }
    return None


def _coerce_minutes(value: object, *, fallback_text: str) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        extracted = _extract_minutes_from_jsonish(_strip_markdown_fence(text))
        if extracted:
            return extracted
        return _strip_markdown_fence(text)
    if value is not None:
        text = str(value).strip()
        if text:
            return text
    extracted_fallback = _extract_minutes_from_jsonish(_strip_markdown_fence(fallback_text))
    if extracted_fallback:
        return extracted_fallback
    cleaned = fallback_text.strip()
    return cleaned if cleaned else "Summary unavailable."


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if "\n" in stripped:
            lines = [
                line.strip().lstrip("-").lstrip("*").strip()
                for line in stripped.splitlines()
                if line.strip()
            ]
            return [line for line in lines if line]
        return [stripped]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _coerce_action_items(value: object) -> list[str]:
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            if isinstance(item, dict):
                owner = str(item.get("owner") or "Unknown").strip() or "Unknown"
                task = str(item.get("task") or item.get("action") or item.get("title") or "").strip()
                due = str(item.get("due") or item.get("deadline") or "TBD").strip() or "TBD"
                if task:
                    normalized.append(f"Owner: {owner}; Task: {task}; Due: {due}")
                continue
            text = str(item).strip()
            if not text:
                continue
            normalized.append(text)
        return normalized
    if isinstance(value, str):
        return _coerce_string_list(value)
    return []


def _coerce_summary_payload(raw_text: str) -> dict[str, object]:
    candidate = _extract_candidate_json(raw_text)
    payload: dict[str, object] = {}
    for source in (candidate, raw_text):
        try:
            loaded = json.loads(source)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            payload = loaded
            break

    minutes = _coerce_minutes(
        payload.get("minutes") if payload else None,
        fallback_text=raw_text,
    )
    decisions = _coerce_string_list(
        payload.get("decisions") if payload else None,
    )
    action_items = _coerce_action_items(
        payload.get("action_items") if payload else None,
    )

    normalized = {
        "minutes": minutes,
        "decisions": decisions,
        "action_items": action_items,
    }
    return _normalize_summary_payload(normalized)


def _normalize_summary_payload(payload: dict[str, object]) -> dict[str, object]:
    raw_minutes = payload.get("minutes")
    embedded_from_minutes = (
        _extract_embedded_summary(raw_minutes) if isinstance(raw_minutes, str) else None
    )

    minutes = _coerce_minutes(raw_minutes, fallback_text="")
    decisions = _coerce_string_list(payload.get("decisions"))
    action_items = _coerce_action_items(payload.get("action_items"))

    embedded = embedded_from_minutes or _extract_embedded_summary(minutes)
    if embedded:
        minutes = _coerce_minutes(embedded.get("minutes"), fallback_text=minutes)
        if not decisions:
            decisions = _coerce_string_list(embedded.get("decisions"))
        if not action_items:
            action_items = _coerce_action_items(embedded.get("action_items"))

    return {
        "minutes": minutes,
        "decisions": decisions,
        "action_items": action_items,
    }


def _summary_max_tokens() -> int:
    raw = os.environ.get("MEETINGCTL_SUMMARY_MAX_TOKENS", "").strip()
    if not raw:
        return 4096
    try:
        return max(int(raw), 512)
    except ValueError:
        return 4096


def _repair_max_tokens() -> int:
    raw = os.environ.get("MEETINGCTL_SUMMARY_REPAIR_MAX_TOKENS", "").strip()
    if not raw:
        return 1536
    try:
        return max(int(raw), 256)
    except ValueError:
        return 1536


def _summary_timeout_seconds() -> float:
    raw = os.environ.get("MEETINGCTL_SUMMARY_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return 120.0
    try:
        return max(float(raw), 5.0)
    except ValueError:
        return 120.0


def _read_onepassword_secret(ref: str) -> str:
    try:
        completed = subprocess.run(
            ["op", "read", ref],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "1Password CLI (`op`) is not installed or not on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Failed to read 1Password secret ref {ref}: {detail}") from exc
    value = completed.stdout.strip()
    if not value:
        raise RuntimeError(f"1Password returned empty secret for ref {ref}.")
    return value


def _resolve_api_key(api_key: str) -> str:
    direct = api_key.strip()
    ref_from_env = os.environ.get("MEETINGCTL_ANTHROPIC_API_KEY_OP_REF", "").strip()

    if direct.startswith("op://"):
        return _read_onepassword_secret(direct)
    if direct:
        return direct
    if ref_from_env:
        return _read_onepassword_secret(ref_from_env)
    return ""


def _request_text_with_model_fallback(
    *,
    client: anthropic.Anthropic,
    prompt: str,
    max_tokens: int,
) -> str:
    last_exc: Exception | None = None
    response = None
    for model in _summary_model_candidates():
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
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
    return _extract_text_content(response)


def _parse_summary_payload(raw_text: str) -> dict[str, object]:
    try:
        parsed = parse_summary_json(raw_text)
        return _normalize_summary_payload(parsed)
    except SummaryParseError:
        candidate = _extract_candidate_json(raw_text)
        if candidate != raw_text:
            parsed = parse_summary_json(candidate)
            return _normalize_summary_payload(parsed)
        raise


def _repair_summary_json(
    *,
    client: anthropic.Anthropic,
    malformed_text: str,
) -> dict[str, object]:
    repair_prompt = f"""Convert the following assistant output into valid JSON.

Requirements:
- Output ONLY valid JSON (no prose, no markdown fences).
- Include exactly these keys:
  - "minutes" (string)
  - "decisions" (array of strings)
  - "action_items" (array of strings)
- Keep all useful detail from the source when possible.
- If a field is missing/unknown, use empty string for minutes or empty arrays for lists.

Source output:
{malformed_text}
"""
    repaired_text = _request_text_with_model_fallback(
        client=client,
        prompt=repair_prompt,
        max_tokens=_repair_max_tokens(),
    )
    try:
        return _parse_summary_payload(repaired_text)
    except SummaryParseError:
        return _coerce_summary_payload(repaired_text or malformed_text)


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
    resolved_api_key = _resolve_api_key(api_key)
    if not resolved_api_key:
        raise ValueError("API key is required")

    client = anthropic.Anthropic(
        api_key=resolved_api_key,
        timeout=_summary_timeout_seconds(),
    )

    prompt = f"""You are a meeting assistant. Given the following meeting transcript, generate a structured summary.

Transcript:
{transcript}

Respond with ONLY a JSON object in this exact format:
{{
  "minutes": "Markdown text with sectioned bullets and sub-bullets",
  "decisions": ["Decision 1", "Decision 2"],
  "action_items": ["Owner: <name or Unknown>; Task: <action>; Due: <date or TBD>"]
}}

Formatting rules:
- `minutes` must be detailed and use markdown bullets/sub-bullets with clear sections in this order:
  1) Meeting Details (title/date/time if inferable, including UTC and US Central when available)
  2) Attendees (participants and inferred roles if available)
  3) Agenda
  4) Key Themes & Pain Points
  5) Minutes & Decisions (discussion narrative in structured bullets)
- Keep `minutes` concise but thorough; prefer nested bullets for readability.
- `decisions` must be a list of concise, stand-alone decision statements.
- `action_items` must be a list where each item follows:
  "Owner: <name or Unknown>; Task: <action>; Due: <date or TBD>"
- If no decisions or action items exist, use empty arrays.
- Do not include markdown code fences.
"""

    response_text = _request_text_with_model_fallback(
        client=client,
        prompt=prompt,
        max_tokens=_summary_max_tokens(),
    )

    # Parse and validate response, then attempt one repair pass if malformed.
    try:
        return _parse_summary_payload(response_text)
    except SummaryParseError:
        return _repair_summary_json(client=client, malformed_text=response_text)
