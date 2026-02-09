from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Protocol

from meetingctl.runtime_state import RuntimeStateStore


class Recorder(Protocol):
    def start(self, session_name: str) -> None:
        ...

    def stop(self, session_name: str) -> None:
        ...


SESSION_BY_PLATFORM = {
    "teams": "Teams+Mic",
    "zoom": "Zoom+Mic",
    "meet": "Browser+Mic",
    "webex": "Browser+Mic",
    "system": "System+Mic",
}


def _duration_human(started_at: str | None, now: datetime) -> str:
    if not started_at:
        return "0m"
    total_minutes = int((now - datetime.fromisoformat(started_at)).total_seconds() // 60)
    if total_minutes < 60:
        return f"{max(total_minutes, 0)}m"
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes}m"


def status_payload(store: RuntimeStateStore, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(UTC)
    state = store.load_state() or {}
    started_at = state.get("started_at") if isinstance(state.get("started_at"), str) else None
    recording = bool(state.get("recording"))
    if not recording:
        return {
            "recording": False,
            "meeting_id": None,
            "title": None,
            "platform": None,
            "duration_human": "0m",
            "note_path": None,
        }

    return {
        "recording": True,
        "meeting_id": state.get("meeting_id"),
        "title": state.get("title"),
        "platform": state.get("platform"),
        "duration_human": _duration_human(started_at, now),
        "note_path": state.get("note_path"),
    }


def start_recording_flow(
    *,
    store: RuntimeStateStore,
    recorder: Recorder,
    event: dict[str, object],
    meeting_id: str,
    note_path: str,
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or datetime.now(UTC)
    state = store.load_state()
    if state and state.get("recording"):
        raise RuntimeError("A meeting is already in progress.")

    raw_platform = str(event.get("platform", "system")).lower()
    fallback_used = raw_platform not in SESSION_BY_PLATFORM
    platform = raw_platform if not fallback_used else "system"
    session_name = SESSION_BY_PLATFORM[platform]

    with store.lock():
        recorder.start(session_name)
        store.write_state(
            {
                "recording": True,
                "meeting_id": meeting_id,
                "title": event.get("title"),
                "platform": platform,
                "note_path": note_path,
                "started_at": now.isoformat(),
                "session_name": session_name,
            }
        )

    return {
        "recording": True,
        "meeting_id": meeting_id,
        "title": event.get("title"),
        "platform": platform,
        "note_path": note_path,
        "fallback_used": fallback_used,
    }


def start_wrapper(
    *,
    store: RuntimeStateStore,
    recorder: Recorder,
    event_resolver: Callable[[], dict[str, object]],
    note_creator: Callable[[dict[str, object]], dict[str, str]],
    now: datetime | None = None,
) -> dict[str, object]:
    event = event_resolver()
    note_info = note_creator(event)
    return start_recording_flow(
        store=store,
        recorder=recorder,
        event=event,
        meeting_id=note_info["meeting_id"],
        note_path=note_info["note_path"],
        now=now,
    )


def stop_recording_flow(
    *,
    store: RuntimeStateStore,
    recorder: Recorder,
    process_trigger: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    state = store.load_state()
    if not state or not state.get("recording"):
        return {
            "recording": False,
            "warning": "No active recording. Start a meeting before calling stop.",
        }

    session_name = str(state.get("session_name", SESSION_BY_PLATFORM["system"]))
    with store.lock():
        recorder.stop(session_name)
        store.clear_state()

    payload = {
        "recording": False,
        "meeting_id": state.get("meeting_id"),
        "title": state.get("title"),
        "platform": state.get("platform"),
        "note_path": state.get("note_path"),
        "processing_triggered": True,
    }
    if process_trigger is not None:
        try:
            process_trigger(payload)
        except Exception as exc:  # pragma: no cover - defensive path
            payload["processing_triggered"] = False
            payload["warning"] = f"Recording stopped but processing trigger failed: {exc}"
    return payload
