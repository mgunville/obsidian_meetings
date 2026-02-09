from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


NOTE_TEXT = """## Minutes
<!-- MINUTES_START -->
> _Pending_
<!-- MINUTES_END -->

## Decisions
<!-- DECISIONS_START -->
> _Pending_
<!-- DECISIONS_END -->

## Action items
<!-- ACTION_ITEMS_START -->
> _Pending_
<!-- ACTION_ITEMS_END -->

## Transcript
<!-- TRANSCRIPT_START -->
> _Pending_
<!-- TRANSCRIPT_END -->
"""


def test_patch_note_cli_dry_run_json(monkeypatch, tmp_path: Path, capsys) -> None:
    note_path = tmp_path / "note.md"
    summary_path = tmp_path / "summary.json"
    note_path.write_text(NOTE_TEXT)
    summary_path.write_text(
        json.dumps(
            {
                "minutes": "Minutes text",
                "decisions": ["Ship beta"],
                "action_items": ["Prepare launch memo"],
            }
        )
    )
    original = note_path.read_text()

    monkeypatch.setattr(
        "sys.argv",
        [
            "meetingctl",
            "patch-note",
            "--note-path",
            str(note_path),
            "--summary-json",
            str(summary_path),
            "--dry-run",
            "--json",
        ],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["write_performed"] is False
    assert note_path.read_text() == original


def test_patch_note_cli_reports_parse_error(monkeypatch, tmp_path: Path, capsys) -> None:
    note_path = tmp_path / "note.md"
    summary_path = tmp_path / "summary.json"
    note_path.write_text(NOTE_TEXT)
    summary_path.write_text("{invalid")

    monkeypatch.setattr(
        "sys.argv",
        [
            "meetingctl",
            "patch-note",
            "--note-path",
            str(note_path),
            "--summary-json",
            str(summary_path),
            "--json",
        ],
    )

    assert cli.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert "error" in payload
