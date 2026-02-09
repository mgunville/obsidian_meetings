from __future__ import annotations

from pathlib import Path

from meetingctl.commands import start_wrapper, stop_recording_flow
from meetingctl.runtime_state import RuntimeStateStore


class FakeRecorder:
    def start(self, session_name: str) -> None:
        self.started = session_name

    def stop(self, session_name: str) -> None:
        self.stopped = session_name


def test_start_wrapper_consumes_event_and_note_dependencies(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    recorder = FakeRecorder()

    payload = start_wrapper(
        store=store,
        recorder=recorder,
        event_resolver=lambda: {"title": "Design Sync", "platform": "unknown"},
        note_creator=lambda event: {"meeting_id": "m-123", "note_path": "/tmp/design-sync.md"},
    )

    assert payload["meeting_id"] == "m-123"
    assert payload["fallback_used"] is True


def test_stop_processing_trigger_failure_is_safe(tmp_path: Path) -> None:
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

    payload = stop_recording_flow(
        store=store,
        recorder=recorder,
        process_trigger=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert payload["recording"] is False
    assert payload["processing_triggered"] is False
    assert "warning" in payload
