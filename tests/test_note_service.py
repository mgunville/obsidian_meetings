from __future__ import annotations

from pathlib import Path

from meetingctl.note.service import create_note_from_event


def test_create_note_from_event_writes_rendered_note(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")

    result = create_note_from_event(
        {
            "title": "Weekly Sync",
            "start": "2026-02-08T10:00:00+00:00",
            "end": "2026-02-08T10:30:00+00:00",
            "calendar_name": "Work",
            "platform": "teams",
            "join_url": "https://teams.microsoft.com/l/meetup-join/abc",
            "recording_wav_rel": "recordings/a.wav",
            "start_human": "10:00",
            "end_human": "10:30",
        }
    )

    note_path = Path(result["note_path"])
    assert note_path.exists()
    content = note_path.read_text()
    assert "meeting_id:" in content
    assert "Weekly Sync" in content
