from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def test_normalize_frontmatter_infers_work_context_from_path(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    vault = tmp_path / "vault"
    note = (
        vault
        / "_Work"
        / "AHEAD"
        / "Clients"
        / "_Leads"
        / "_Tiffany"
        / "2026-02-25 1349 - Tiffany Craig and Mike DR Bubble Opportunity SOW Chat - m-4651e52568.md"
    )
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "\n".join(
            [
                "---",
                "type: \"work\"",
                "meeting_id: \"m-4651e52568\"",
                "title: \"wrong\"",
                "---",
                "",
                "# Note",
            ]
        )
        + "\n"
    )

    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path / "recordings"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "meetingctl",
            "normalize-frontmatter",
            "--note-path",
            str(note),
            "--json",
        ],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed"] == 1

    updated = note.read_text()
    assert 'firm: "AHEAD"' in updated
    assert 'client: "Tiffany"' in updated
    assert 'engagement: "Lead"' in updated
    assert 'note_type: "meeting"' in updated
    assert 'title: "Tiffany Craig and Mike DR Bubble Opportunity SOW Chat"' in updated


def test_normalize_frontmatter_supports_scope_scan(monkeypatch, tmp_path: Path, capsys) -> None:
    vault = tmp_path / "vault"
    note = vault / "Meetings" / "2026-02-24 1130 - Weekly Connect JSM Change Management Comms Training - m-2bf88c2062.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "\n".join(
            [
                "---",
                "type: meeting",
                "meeting_id: \"m-2bf88c2062\"",
                "---",
                "",
                "# Note",
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("RECORDINGS_PATH", str(tmp_path / "recordings"))
    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "normalize-frontmatter", "--scope", "Meetings", "--json"],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["examined"] == 1
    assert payload["changed"] == 1
    updated = note.read_text()
    assert 'note_type: "meeting"' in updated
    assert 'title: "Weekly Connect JSM Change Management Comms Training"' in updated
