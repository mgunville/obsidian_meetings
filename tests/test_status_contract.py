from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from meetingctl.commands import status_payload
from meetingctl.runtime_state import RuntimeStateStore


def _load_fixture(name: str) -> dict[str, object]:
    fixture_path = Path(__file__).parent / "fixtures" / name
    return json.loads(fixture_path.read_text())


def test_status_json_idle_contract(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    assert status_payload(store, now=datetime(2026, 2, 8, 10, 0, tzinfo=UTC)) == _load_fixture(
        "status_idle.json"
    )


def test_status_json_active_contract(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    store.write_state(
        {
            "recording": True,
            "meeting_id": "m-123",
            "title": "Design Sync",
            "platform": "teams",
            "note_path": "/tmp/design-sync.md",
            "started_at": "2026-02-08T09:00:00+00:00",
        }
    )

    assert status_payload(store, now=datetime(2026, 2, 8, 10, 0, tzinfo=UTC)) == _load_fixture(
        "status_active.json"
    )
