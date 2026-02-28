from __future__ import annotations

from datetime import UTC, timedelta, timezone
from pathlib import Path

from meetingctl.note.service import (
    create_note_from_event,
    infer_datetime_from_recording_path,
    preview_note_from_event,
)


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
    assert 'firm: "AHEAD"' in content


def test_infer_datetime_from_recording_path_uses_local_timezone(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "20260210-1130_Audio.wav"
    path.write_bytes(b"")
    local_tz = timezone(timedelta(hours=-6))
    monkeypatch.setattr("meetingctl.note.service._local_tz", lambda: local_tz)

    inferred, source = infer_datetime_from_recording_path(path)

    assert source == "filename"
    assert inferred.hour == 11
    assert inferred.minute == 30
    assert inferred.utcoffset() == timedelta(hours=-6)
    assert inferred.tzinfo != UTC


def test_infer_datetime_from_recording_path_uses_filename_timezone_override(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "20260210-1130_Audio.wav"
    path.write_bytes(b"")
    monkeypatch.setenv("MEETINGCTL_RECORDING_FILENAME_TIMEZONE", "America/Chicago")
    monkeypatch.setattr("meetingctl.note.service._local_tz", lambda: timezone.utc)

    inferred, source = infer_datetime_from_recording_path(path)

    assert source == "filename"
    assert inferred.hour == 11
    assert inferred.minute == 30
    assert inferred.utcoffset() == timedelta(hours=-6)


def test_infer_datetime_from_voice_memo_filename_defaults_to_local_tz(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "20260209 143519-9ED804D9.m4a"
    path.write_bytes(b"")
    monkeypatch.delenv("MEETINGCTL_VOICEMEMO_FILENAME_TIMEZONE", raising=False)
    monkeypatch.setattr("meetingctl.note.service._local_tz", lambda: timezone.utc)

    inferred, source = infer_datetime_from_recording_path(path)

    assert source == "filename_voice_memo"
    assert inferred.isoformat() == "2026-02-09T14:35:19+00:00"


def test_infer_datetime_from_voice_memo_filename_allows_timezone_override(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "20260209 143519-9ED804D9.m4a"
    path.write_bytes(b"")
    monkeypatch.setenv("MEETINGCTL_VOICEMEMO_FILENAME_TIMEZONE", "America/Chicago")

    inferred, source = infer_datetime_from_recording_path(path)

    assert source == "filename_voice_memo"
    assert inferred.utcoffset() == timedelta(hours=-6)
    assert inferred.hour == 14
    assert inferred.minute == 35
    assert inferred.second == 19


def test_infer_datetime_from_voice_memo_filename_uses_incident_manifest_utc(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "20260209 143519-9ED804D9.m4a"
    path.write_bytes(b"")
    manifest = tmp_path / "incident.txt"
    manifest.write_text("20260209 143519-9ED804D9.m4a\n")
    monkeypatch.setenv("MEETINGCTL_VOICEMEMO_FILENAME_TIMEZONE", "America/Chicago")
    monkeypatch.setenv("MEETINGCTL_VOICEMEMO_UTC_MANIFEST", str(manifest))

    inferred, source = infer_datetime_from_recording_path(path)

    assert source == "filename_voice_memo"
    assert inferred.isoformat() == "2026-02-09T14:35:19+00:00"


def test_create_note_from_event_reuses_existing_meeting_id_note(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    event = {
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

    first = create_note_from_event(event)
    second = create_note_from_event(event)

    assert first["meeting_id"] == second["meeting_id"]
    assert first["note_path"] == second["note_path"]
    meetings_dir = tmp_path / "meetings"
    assert len(list(meetings_dir.glob("*.md"))) == 1


def test_preview_note_from_event_uses_local_time_in_filename(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    local_tz = timezone(timedelta(hours=-6))
    monkeypatch.setattr("meetingctl.note.service._local_tz", lambda: local_tz)

    preview = preview_note_from_event(
        {
            "title": "Consulting SP PC call",
            "start": "2026-02-10T16:00:00+00:00",
            "end": "2026-02-10T17:00:00+00:00",
        },
        meeting_id="m-test123",
    )
    assert "2026-02-10 1000 - Consulting SP PC call - m-test123.md" in preview["note_path"]
