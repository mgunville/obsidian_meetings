from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli


def test_ingest_watch_once_queues_wav_and_m4a(monkeypatch, tmp_path: Path, capsys) -> None:
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
    assert payload["queued_jobs"] == 3
    assert payload["failed_jobs"] == 0
    last_poll = payload["last_poll"]
    assert last_poll["discovered_audio"] == 3
    assert last_poll["discovered_wav"] == 3
    assert last_poll["queued_jobs"] == 3
    queued = queue.read_text().strip().splitlines()
    assert len(queued) == 3
    queued_paths = {json.loads(line)["wav_path"] for line in queued}
    assert any(path.endswith(".wav") for path in queued_paths)
    assert any(path.endswith(".m4a") for path in queued_paths)
    ingested_lines = ingested.read_text().strip().splitlines()
    assert len(ingested_lines) == 3


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
