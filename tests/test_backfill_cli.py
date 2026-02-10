from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def test_backfill_cli_queues_recordings(monkeypatch, tmp_path: Path, capsys) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    (recordings / "20260208_1015-team-sync.wav").write_text("wav")
    (recordings / "20260208_1115-demo.wav").write_text("wav")

    monkeypatch.setattr("sys.argv", ["meetingctl", "backfill", "--json"])
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["discovered_files"] == 2
    assert payload["queued_jobs"] == 2
    assert payload["failed_jobs"] == 0
    assert payload["process_now"] is False
    queued_lines = queue.read_text().strip().splitlines()
    assert len(queued_lines) == 2


def test_backfill_cli_process_now_runs_pipeline(monkeypatch, tmp_path: Path, capsys) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    processed = tmp_path / "processed.jsonl"
    wav = recordings / "20260208_0915-retro.wav"
    wav.write_text("wav")
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed))
    monkeypatch.setenv("MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN", "1")
    monkeypatch.setenv("MEETINGCTL_PROCESSING_CONVERT_DRY_RUN", "1")
    monkeypatch.setenv(
        "MEETINGCTL_PROCESSING_SUMMARY_JSON",
        '{"minutes":"Backfill summary","decisions":[],"action_items":[]}',
    )

    monkeypatch.setattr("sys.argv", ["meetingctl", "backfill", "--process-now", "--json"])
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_jobs"] == 1
    assert payload["failed_jobs"] == 0
    assert payload["queued_jobs"] == 0
    assert not wav.exists()


def test_backfill_cli_match_calendar_dry_run_plans_without_side_effects(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    wav = recordings / "20260208_1015-team-sync.wav"
    wav.write_text("wav")
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    monkeypatch.setattr(
        cli,
        "resolve_event_near_timestamp",
        lambda at, window_minutes: {
            "title": "Team Sync",
            "start": "2026-02-08T10:15:00+00:00",
            "end": "2026-02-08T10:45:00+00:00",
            "calendar_name": "Work",
            "join_url": "https://teams.microsoft.com/l/meetup-join/abc",
            "platform": "teams",
            "match_distance_minutes": 0.0,
        },
    )

    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "backfill", "--match-calendar", "--rename", "--dry-run", "--json"],
    )
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["matched_calendar"] == 1
    assert payload["queued_jobs"] == 0
    assert payload["processed_jobs"] == 0
    assert len(payload["plans"]) == 1
    assert payload["plans"][0]["matched_calendar"] is True
    assert wav.exists()
    assert not queue.exists()


def test_backfill_cli_match_calendar_rename_updates_recording_name(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "queue.jsonl"
    wav = recordings / "20260208_1015-team-sync.wav"
    wav.write_text("wav")
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue))
    monkeypatch.setattr(
        cli,
        "resolve_event_near_timestamp",
        lambda at, window_minutes: {
            "title": "Team Sync",
            "start": "2026-02-08T10:15:00+00:00",
            "end": "2026-02-08T10:45:00+00:00",
            "calendar_name": "Work",
            "join_url": "https://teams.microsoft.com/l/meetup-join/abc",
            "platform": "teams",
            "match_distance_minutes": 0.0,
        },
    )

    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "backfill", "--match-calendar", "--rename", "--json"],
    )
    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["matched_calendar"] == 1
    assert payload["queued_jobs"] == 1
    queued = json.loads(queue.read_text().strip())
    renamed_wav = Path(queued["wav_path"])
    assert renamed_wav.exists()
    assert not wav.exists()
