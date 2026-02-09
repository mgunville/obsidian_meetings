from __future__ import annotations

import json
from pathlib import Path

from meetingctl.note.patcher import patch_note_file


NOTE_TEXT = """## Minutes
<!-- MINUTES_START -->
> _Pending_
<!-- MINUTES_END -->
"""


def test_patch_note_dry_run_has_no_write_side_effects(tmp_path: Path) -> None:
    note_path = tmp_path / "note.md"
    note_path.write_text(NOTE_TEXT)
    original = note_path.read_text()

    result = patch_note_file(
        note_path=note_path,
        updates={"minutes": "Updated"},
        dry_run=True,
    )

    assert note_path.read_text() == original
    expected = json.loads((Path(__file__).parent / "fixtures" / "patch_note_dry_run.json").read_text())
    expected["note_path"] = str(note_path)
    assert result == expected


def test_patch_note_write_mode_updates_file(tmp_path: Path) -> None:
    note_path = tmp_path / "note.md"
    note_path.write_text(NOTE_TEXT)

    result = patch_note_file(
        note_path=note_path,
        updates={"minutes": "Updated"},
        dry_run=False,
    )

    assert "Updated" in note_path.read_text()
    assert result["write_performed"] is True
