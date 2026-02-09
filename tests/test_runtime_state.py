from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from meetingctl.runtime_state import RuntimeStateStore, StateLockError


def test_runtime_state_roundtrip(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    payload = {
        "recording": True,
        "meeting_id": "m-123",
        "title": "Design Sync",
        "platform": "teams",
        "note_path": "/tmp/note.md",
        "started_at": "2026-02-08T10:00:00+00:00",
    }

    store.write_state(payload)
    assert store.load_state() == payload


def test_runtime_state_lock_prevents_concurrent_access(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    with store.lock():
        with pytest.raises(StateLockError):
            with store.lock():
                pass


def test_runtime_state_detects_stale_recording(tmp_path: Path) -> None:
    store = RuntimeStateStore(tmp_path / "current.json")
    started_at = datetime.now(UTC) - timedelta(hours=13)
    store.write_state(
        {
            "recording": True,
            "meeting_id": "m-123",
            "title": "Design Sync",
            "platform": "teams",
            "note_path": "/tmp/note.md",
            "started_at": started_at.isoformat(),
        }
    )
    assert store.is_stale(max_age_seconds=12 * 3600)
