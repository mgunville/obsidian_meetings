from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def test_audit_notes_reports_duplicates(monkeypatch, tmp_path: Path, capsys) -> None:
    meetings = tmp_path / "meetings"
    meetings.mkdir(parents=True, exist_ok=True)
    (meetings / "2026-02-09 0835 - Sync - m-aaaaaaaaaa.md").write_text("# one")
    (meetings / "2026-02-09 0835 - Sync - m-aaaaaaaaaa (2).md").write_text("# two")
    (meetings / "2026-02-09 0930 - Other - m-bbbbbbbbbb.md").write_text("# three")

    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setattr("sys.argv", ["meetingctl", "audit-notes", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["discovered_notes"] == 3
    assert payload["unique_meeting_ids"] == 2
    assert payload["duplicate_meeting_ids"] == 1
    assert payload["duplicates"][0]["meeting_id"] == "m-aaaaaaaaaa"
    assert len(payload["duplicates"][0]["note_paths"]) == 2


def test_audit_notes_handles_missing_dir(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setattr("sys.argv", ["meetingctl", "audit-notes", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["discovered_notes"] == 0
    assert payload["duplicate_meeting_ids"] == 0
