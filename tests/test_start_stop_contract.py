from __future__ import annotations

import json
from pathlib import Path

from meetingctl.commands import start_recording_flow, stop_recording_flow
from meetingctl.runtime_state import RuntimeStateStore


class FakeRecorder:
    def start(self, session_name: str) -> None:
        self.started = session_name

    def stop(self, session_name: str) -> None:
        self.stopped = session_name


def _fixture(name: str) -> dict[str, object]:
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


def test_start_json_contract(tmp_path: Path) -> None:
    payload = start_recording_flow(
        store=RuntimeStateStore(tmp_path / "current.json"),
        recorder=FakeRecorder(),
        event={"title": "Weekly Sync", "platform": "teams"},
        meeting_id="m-123",
        note_path="/tmp/weekly-sync.md",
    )
    assert payload == _fixture("start_success.json")


def test_stop_json_contract_idle(tmp_path: Path) -> None:
    payload = stop_recording_flow(
        store=RuntimeStateStore(tmp_path / "current.json"),
        recorder=FakeRecorder(),
    )
    assert payload == _fixture("stop_idle.json")


def test_stop_json_contract_success(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
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
    payload = stop_recording_flow(store=store, recorder=FakeRecorder())
    assert payload == _fixture("stop_success.json")
