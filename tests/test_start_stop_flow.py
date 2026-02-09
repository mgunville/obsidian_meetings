from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from meetingctl.commands import start_recording_flow, stop_recording_flow
from meetingctl.runtime_state import RuntimeStateStore


class FakeRecorder:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []

    def start(self, session_name: str) -> None:
        self.started.append(session_name)

    def stop(self, session_name: str) -> None:
        self.stopped.append(session_name)


def test_start_flow_surfaces_fallback_and_writes_state(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    recorder = FakeRecorder()

    payload = start_recording_flow(
        store=store,
        recorder=recorder,
        event={"title": "Weekly Sync", "platform": "unknown"},
        meeting_id="m-123",
        note_path="/tmp/weekly-sync.md",
        now=datetime(2026, 2, 8, 10, 0, tzinfo=UTC),
    )

    assert payload["recording"] is True
    assert payload["fallback_used"] is True
    assert payload["platform"] == "system"
    assert recorder.started == ["System+Mic"]
    state = store.load_state()
    assert state is not None
    assert state["meeting_id"] == "m-123"


def test_stop_flow_returns_safe_warning_when_idle(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    recorder = FakeRecorder()

    payload = stop_recording_flow(store=store, recorder=recorder)

    assert payload["recording"] is False
    assert "warning" in payload
    assert recorder.stopped == []


def test_stop_flow_stops_active_recording_and_clears_state(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    recorder = FakeRecorder()
    store.write_state(
        {
            "recording": True,
            "meeting_id": "m-123",
            "title": "Weekly Sync",
            "platform": "teams",
            "note_path": "/tmp/weekly-sync.md",
            "started_at": "2026-02-08T10:00:00+00:00",
            "session_name": "Teams+Mic",
        }
    )

    payload = stop_recording_flow(store=store, recorder=recorder)
    assert payload["recording"] is False
    assert payload["meeting_id"] == "m-123"
    assert recorder.stopped == ["Teams+Mic"]
    assert store.load_state() is None
