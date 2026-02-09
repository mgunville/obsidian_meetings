from __future__ import annotations

import json


class SummaryParseError(ValueError):
    pass


def parse_summary_json(raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SummaryParseError("Malformed summary JSON") from exc

    if not isinstance(payload, dict):
        raise SummaryParseError("Summary payload must be a JSON object")

    minutes = payload.get("minutes")
    decisions = payload.get("decisions")
    action_items = payload.get("action_items")

    if not isinstance(minutes, str):
        raise SummaryParseError("minutes must be a string")
    if not (isinstance(decisions, list) and all(isinstance(item, str) for item in decisions)):
        raise SummaryParseError("decisions must be a list of strings")
    if not (isinstance(action_items, list) and all(isinstance(item, str) for item in action_items)):
        raise SummaryParseError("action_items must be a list of strings")

    return {
        "minutes": minutes,
        "decisions": decisions,
        "action_items": action_items,
    }


def summary_to_patch_regions(parsed_summary: dict[str, object]) -> dict[str, str]:
    decisions = parsed_summary["decisions"]
    action_items = parsed_summary["action_items"]
    return {
        "minutes": str(parsed_summary["minutes"]),
        "decisions": "\n".join(f"- {item}" for item in decisions) if decisions else "> _Pending_",
        "action_items": (
            "\n".join(f"- {item}" for item in action_items) if action_items else "> _Pending_"
        ),
    }
