from __future__ import annotations

import plistlib
from pathlib import Path


KM_PATH = Path(__file__).resolve().parents[1] / "config" / "km" / "Meeting-Automation-Macros.kmmacros"


def _load_macros() -> list[dict[str, object]]:
    payload = plistlib.loads(KM_PATH.read_bytes())
    if isinstance(payload, dict):
        groups = payload["MacroGroups"]
    else:
        groups = payload
    assert isinstance(groups, list) and groups
    group = groups[0]
    macros = group["Macros"]
    assert isinstance(macros, list)
    return macros


def _macro_by_uid(uid: str) -> dict[str, object]:
    for macro in _load_macros():
        if macro.get("UID") == uid:
            return macro
    raise AssertionError(f"Macro UID not found: {uid}")


def _macro_by_name(name: str) -> dict[str, object]:
    for macro in _load_macros():
        if macro.get("Name") == name:
            return macro
    raise AssertionError(f"Macro name not found: {name}")


def _action_texts(macro: dict[str, object]) -> list[str]:
    actions = macro.get("Actions", [])
    texts: list[str] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        for key in ("Text", "Title", "Subtitle", "Prompt"):
            value = action.get(key)
            if isinstance(value, str):
                texts.append(value)
    return texts


def test_e6_s1_start_macro_uses_json_and_surfaces_fallback() -> None:
    macro = _macro_by_name("Start Meeting Recording")
    texts = _action_texts(macro)
    assert any("meetingctl start --json" in text for text in texts)
    assert any("Browser+Mic fallback" in text for text in texts)


def test_e6_s2_stop_macro_has_immediate_confirmation_path() -> None:
    macro = _macro_by_name("Stop Meeting Recording")
    texts = _action_texts(macro)
    assert any("meetingctl stop --json" in text for text in texts)
    assert any("Recording Stopped" in text for text in texts)


def test_e6_s3_status_macro_consumes_status_json() -> None:
    macro = _macro_by_name("Check Recording Status")
    texts = _action_texts(macro)
    assert any("meetingctl status --json" in text for text in texts)
    assert any("Recording Active" in text for text in texts)
    assert any("Idle" in text for text in texts)


def test_e6_s4_adhoc_macro_prompts_title_and_starts_without_calendar() -> None:
    macro = _macro_by_name("Start Ad-hoc Recording")
    texts = _action_texts(macro)
    assert any("Enter meeting title for ad-hoc recording" in text for text in texts)
    assert any('meetingctl start --title "$KMVAR_AdHocTitle" --platform meet --json' in text for text in texts)


def test_e6_s5_autodetect_macro_disabled_by_default() -> None:
    macro = _macro_by_name("Auto-detect Meeting (DISABLED)")
    assert macro.get("IsActive") is False
    triggers = macro.get("Triggers", [])
    trigger_apps = [
        trigger.get("Application", {}).get("BundleIdentifier")
        for trigger in triggers
        if isinstance(trigger, dict)
    ]
    assert "us.zoom.xos" in trigger_apps
    assert "com.microsoft.teams" in trigger_apps
