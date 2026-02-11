from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def _write_queue(path: Path, payloads: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(payload) for payload in payloads) + "\n")


def test_process_queue_cli_runs_real_pipeline_success(monkeypatch, tmp_path: Path, capsys) -> None:
    queue_file = tmp_path / "process_queue.jsonl"
    processed_file = tmp_path / "processed.jsonl"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    note = tmp_path / "meeting.md"
    note.write_text(
        "\n".join(
            [
                "# Note",
                "<!-- MINUTES_START -->",
                "",
                "<!-- MINUTES_END -->",
                "<!-- DECISIONS_START -->",
                "",
                "<!-- DECISIONS_END -->",
                "<!-- ACTION_ITEMS_START -->",
                "",
                "<!-- ACTION_ITEMS_END -->",
                "<!-- TRANSCRIPT_START -->",
                "",
                "<!-- TRANSCRIPT_END -->",
            ]
        )
        + "\n"
    )
    wav = recordings / "m-1.wav"
    wav.write_text("wav")
    _write_queue(queue_file, [{"meeting_id": "m-1", "note_path": str(note)}])
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class FakeRunner:
        def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
            transcript_path.write_text("transcript")
            return transcript_path

    monkeypatch.setattr("meetingctl.cli.create_transcription_runner", lambda: FakeRunner())
    monkeypatch.setattr(
        "meetingctl.cli.generate_summary",
        lambda transcript, api_key: {
            "minutes": "Summary",
            "decisions": ["Decision A"],
            "action_items": ["Do thing"],
        },
    )
    def _fake_convert(*, wav_path: Path, mp3_path: Path) -> Path:
        wav_path.unlink()
        mp3_path.write_text("mp3")
        return mp3_path

    monkeypatch.setattr("meetingctl.cli.convert_wav_to_mp3", _fake_convert)
    monkeypatch.setattr("sys.argv", ["meetingctl", "process-queue", "--max-jobs", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"processed_jobs": 1, "failed_jobs": 0, "remaining_jobs": 0}

    assert (recordings / "m-1.txt").read_text() == "transcript"
    assert (recordings / "m-1.mp3").read_text() == "mp3"
    assert not wav.exists()
    patched = note.read_text()
    assert "Summary" in patched
    assert "- Decision A" in patched
    assert "- Do thing" in patched
    assert f"- mp3_path: {recordings / 'm-1.mp3'}" in patched
    assert "- status: complete" in patched

    processed_lines = processed_file.read_text().strip().splitlines()
    assert len(processed_lines) == 1
    processed = json.loads(processed_lines[0])
    assert processed["meeting_id"] == "m-1"
    assert processed["mp3_path"].endswith("/m-1.mp3")
    assert processed["transcript_path"].endswith("/m-1.txt")


def test_process_queue_cli_reports_failure_and_keeps_payload(monkeypatch, tmp_path: Path, capsys) -> None:
    queue_file = tmp_path / "process_queue.jsonl"
    processed_file = tmp_path / "processed.jsonl"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    note = tmp_path / "meeting.md"
    note.write_text("# Note")
    _write_queue(queue_file, [{"meeting_id": "m-2", "note_path": str(note)}])
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("sys.argv", ["meetingctl", "process-queue", "--max-jobs", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_jobs"] == 0
    assert payload["failed_jobs"] == 1
    assert payload["remaining_jobs"] == 1
    assert "Missing WAV input:" in payload["failure_reason"]
    remaining = queue_file.read_text().strip().splitlines()
    assert len(remaining) == 1


def test_process_queue_cli_supports_transcribe_dry_run(monkeypatch, tmp_path: Path, capsys) -> None:
    queue_file = tmp_path / "process_queue.jsonl"
    processed_file = tmp_path / "processed.jsonl"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    note = tmp_path / "meeting.md"
    note.write_text(
        "\n".join(
            [
                "# Note",
                "<!-- MINUTES_START -->",
                "",
                "<!-- MINUTES_END -->",
                "<!-- DECISIONS_START -->",
                "",
                "<!-- DECISIONS_END -->",
                "<!-- ACTION_ITEMS_START -->",
                "",
                "<!-- ACTION_ITEMS_END -->",
                "<!-- TRANSCRIPT_START -->",
                "",
                "<!-- TRANSCRIPT_END -->",
            ]
        )
        + "\n"
    )
    wav = recordings / "m-3.wav"
    wav.write_text("wav")
    _write_queue(queue_file, [{"meeting_id": "m-3", "note_path": str(note)}])
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setenv("MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN", "1")
    monkeypatch.setenv(
        "MEETINGCTL_PROCESSING_SUMMARY_JSON",
        '{"minutes":"Dry summary","decisions":[],"action_items":[]}',
    )
    monkeypatch.setenv("MEETINGCTL_PROCESSING_CONVERT_DRY_RUN", "1")
    monkeypatch.setattr("sys.argv", ["meetingctl", "process-queue", "--max-jobs", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"processed_jobs": 1, "failed_jobs": 0, "remaining_jobs": 0}
    assert (recordings / "m-3.txt").exists()
    assert (recordings / "m-3.mp3").exists()
    assert not wav.exists()


def test_process_queue_cli_fails_when_expected_wav_missing(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    queue_file = tmp_path / "process_queue.jsonl"
    processed_file = tmp_path / "processed.jsonl"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    note = tmp_path / "meeting.md"
    note.write_text(
        "\n".join(
            [
                "# Note",
                "<!-- MINUTES_START -->",
                "> _Pending_",
                "<!-- MINUTES_END -->",
                "<!-- DECISIONS_START -->",
                "> _Pending_",
                "<!-- DECISIONS_END -->",
                "<!-- ACTION_ITEMS_START -->",
                "> _Pending_",
                "<!-- ACTION_ITEMS_END -->",
                "<!-- TRANSCRIPT_START -->",
                "> _Pending_",
                "<!-- TRANSCRIPT_END -->",
            ]
        )
        + "\n"
    )
    (recordings / "capture-20260209-1700.wav").write_text("wav")
    _write_queue(queue_file, [{"meeting_id": "m-4", "note_path": str(note)}])
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setattr("sys.argv", ["meetingctl", "process-queue", "--max-jobs", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_jobs"] == 0
    assert payload["failed_jobs"] == 1
    assert payload["remaining_jobs"] == 1
    assert "Missing WAV input:" in payload["failure_reason"]
    assert (recordings / "capture-20260209-1700.wav").exists()


def test_process_queue_cli_rejects_note_path_outside_vault(monkeypatch, tmp_path: Path, capsys) -> None:
    queue_file = tmp_path / "process_queue.jsonl"
    processed_file = tmp_path / "processed.jsonl"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    outside_note = tmp_path.parent / "outside.md"
    outside_note.write_text("# Outside")
    (recordings / "m-5.wav").write_text("wav")
    _write_queue(queue_file, [{"meeting_id": "m-5", "note_path": str(outside_note)}])
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setattr("sys.argv", ["meetingctl", "process-queue", "--max-jobs", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_jobs"] == 0
    assert payload["failed_jobs"] == 1
    assert payload["remaining_jobs"] == 1
    assert "Note path must be inside vault path" in payload["failure_reason"]


def test_process_queue_cli_rejects_wav_path_outside_recordings(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    queue_file = tmp_path / "process_queue.jsonl"
    processed_file = tmp_path / "processed.jsonl"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    outside_wav = tmp_path.parent / "outside.wav"
    outside_wav.write_text("wav")
    note = tmp_path / "meeting.md"
    note.write_text("# Note")
    _write_queue(
        queue_file,
        [{"meeting_id": "m-6", "note_path": str(note), "wav_path": str(outside_wav)}],
    )
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("MEETINGCTL_PROCESSED_JOBS_FILE", str(processed_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("RECORDINGS_PATH", str(recordings))
    monkeypatch.setattr("sys.argv", ["meetingctl", "process-queue", "--max-jobs", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed_jobs"] == 0
    assert payload["failed_jobs"] == 1
    assert payload["remaining_jobs"] == 1
    assert "WAV path must be within recordings path" in payload["failure_reason"]
