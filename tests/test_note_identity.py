from __future__ import annotations

from datetime import datetime
from pathlib import Path

from meetingctl.note.identity import (
    build_note_filename,
    ensure_collision_safe_path,
    generate_meeting_id,
    sanitize_title,
)


def test_generate_meeting_id_is_deterministic() -> None:
    meeting_id_1 = generate_meeting_id(
        title="Weekly Client Sync",
        start_iso="2026-02-08T10:00:00+00:00",
    )
    meeting_id_2 = generate_meeting_id(
        title="Weekly Client Sync",
        start_iso="2026-02-08T10:00:00+00:00",
    )
    assert meeting_id_1 == meeting_id_2


def test_sanitize_title_for_filename() -> None:
    assert sanitize_title(" Design/Review: Q1 *Plan* ") == "Design Review Q1 Plan"


def test_build_note_filename_uses_expected_format() -> None:
    filename = build_note_filename(
        start_dt=datetime(2026, 2, 8, 10, 30),
        title="Weekly Client Sync",
        meeting_id="m-123abc",
    )
    assert filename == "2026-02-08 1030 - Weekly Client Sync - m-123abc.md"


def test_collision_strategy_returns_next_available(tmp_path: Path) -> None:
    original = tmp_path / "2026-02-08 1030 - Weekly Client Sync - m-123abc.md"
    original.write_text("exists")
    next_path = ensure_collision_safe_path(original)
    assert next_path.name == "2026-02-08 1030 - Weekly Client Sync - m-123abc (2).md"
