from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def test_ingest_watch_once_collapses_same_stem_and_prefers_wav(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    ingested = tmp_path / "ingested.jsonl"
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    monkeypatch.setenv("MEETINGCTL_INGESTED_FILES_FILE", str(ingested))

    (recordings / "20260210_1000-call.wav").write_text("wav")
    (recordings / "20260210_1000-call.m4a").write_text("m4a")
    (recordings / "20260210_1015-call.m4a").write_text("m4a")

    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "ingest-watch", "--once", "--min-age-seconds", "0", "--json"],
    )
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["polls"] == 1
    assert payload["queued_jobs"] == 2
    assert payload["failed_jobs"] == 0
    last_poll = payload["last_poll"]
    assert last_poll["discovered_audio"] == 2
    assert last_poll["discovered_wav"] == 2
    assert last_poll["queued_jobs"] == 2
    queued = queue.read_text().strip().splitlines()
    assert len(queued) == 2
    queued_paths = {json.loads(line)["wav_path"] for line in queued}
    assert any(path.endswith(".wav") for path in queued_paths)
    assert any(path.endswith(".m4a") for path in queued_paths)
    assert str((recordings / "20260210_1000-call.wav").resolve()) in queued_paths
    assert str((recordings / "20260210_1000-call.m4a").resolve()) not in queued_paths
    ingested_lines = ingested.read_text().strip().splitlines()
    assert len(ingested_lines) == 2


def test_ingest_watch_skips_already_ingested_and_too_new(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    ingested = tmp_path / "ingested.jsonl"
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    monkeypatch.setenv("MEETINGCTL_INGESTED_FILES_FILE", str(ingested))

    wav = recordings / "20260210_1030-call.wav"
    wav.write_text("wav")
    ingested.write_text(
        json.dumps({"wav_path": str(wav.resolve()), "meeting_id": "m-old"}) + "\n"
    )

    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "ingest-watch", "--once", "--min-age-seconds", "3600", "--json"],
    )
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queued_jobs"] == 0
    assert payload["last_poll"]["skipped_already_ingested"] == 1


def test_ingest_watch_reuses_existing_start_time_note_for_calendar_match(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    ingested = tmp_path / "ingested.jsonl"
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "Meetings")
    monkeypatch.setenv("MEETINGCTL_LOCAL_TIMEZONE", "America/Chicago")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    monkeypatch.setenv("MEETINGCTL_INGESTED_FILES_FILE", str(ingested))

    wav = recordings / "20260303-0900_Audio.wav"
    wav.write_text("wav")
    existing_note = (
        vault / "_Work" / "AHEAD" / "Clients" / "Acme" / "2026-03-03 0900 - Acme Sync - m-abc123def4.md"
    )
    existing_note.parent.mkdir(parents=True, exist_ok=True)
    existing_note.write_text(
        "\n".join(
            [
                "---",
                'meeting_id: "m-abc123def4"',
                "---",
                "<!-- MINUTES_START -->",
                "> _Pending_",
                "<!-- MINUTES_END -->",
                "<!-- DECISIONS_START -->",
                "> _Pending_",
                "<!-- DECISIONS_END -->",
                "<!-- ACTION_ITEMS_START -->",
                "> _Pending_",
                "<!-- ACTION_ITEMS_END -->",
                "<!-- REFERENCES_START -->",
                "> _Pending_",
                "<!-- REFERENCES_END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "resolve_event_near_now",
        lambda now, forward_minutes, backward_minutes: {
            "title": "Acme Sync",
            "start": "2026-03-03T15:00:00+00:00",
            "end": "2026-03-03T15:30:00+00:00",
            "calendar_name": "Work",
            "platform": "teams",
            "join_url": "",
            "match_stage": 1,
            "match_distance_minutes": 0.0,
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "ingest-watch", "--once", "--match-calendar", "--min-age-seconds", "0", "--json"],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queued_jobs"] == 1
    assert payload["reused_existing_notes"] == 1
    assert len(payload["existing_note_match_logs"]) == 1
    queued = json.loads(queue.read_text().strip())
    assert queued["meeting_id"] == "m-abc123def4"
    assert Path(queued["note_path"]).resolve() == existing_note.resolve()


def test_ingest_watch_calendar_match_uses_now_reference_not_filename(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    ingested = tmp_path / "ingested.jsonl"
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    monkeypatch.setenv("MEETINGCTL_INGESTED_FILES_FILE", str(ingested))
    monkeypatch.setenv("MEETINGCTL_NOW_ISO", "2026-03-03T15:49:00+00:00")

    wav = recordings / "20260303-1545_Audio.m4a"
    wav.write_text("m4a")

    captured: dict[str, object] = {}

    def _fake_match(now, forward_minutes, backward_minutes):
        captured["now"] = now.isoformat()
        captured["forward"] = forward_minutes
        captured["backward"] = backward_minutes
        return None

    monkeypatch.setattr(cli, "resolve_event_near_now", _fake_match)
    monkeypatch.setattr(
        "sys.argv",
        [
            "meetingctl",
            "ingest-watch",
            "--once",
            "--match-calendar",
            "--min-age-seconds",
            "0",
            "--json",
        ],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["last_poll"]["calendar_match_reference"] == "now"
    assert payload["last_poll"]["calendar_forward_minutes"] == 10
    assert payload["last_poll"]["calendar_backward_minutes"] == 15
    assert captured["now"] == "2026-03-03T15:49:00+00:00"
    assert captured["forward"] == 10
    assert captured["backward"] == 15
