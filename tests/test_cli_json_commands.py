from __future__ import annotations

import json
from pathlib import Path

from meetingctl import cli
from meetingctl.runtime_state import RuntimeStateStore


class FakeRecorder:
    def start(self, session_name: str) -> None:
        self.started = session_name

    def stop(self, session_name: str) -> None:
        self.stopped = session_name


def _fixture(name: str) -> dict[str, object]:
    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


def test_cli_status_json_contract(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("MEETINGCTL_STATE_FILE", str(tmp_path / "current.json"))
    monkeypatch.setattr(cli, "AudioHijackRecorder", lambda: FakeRecorder())
    monkeypatch.setattr("sys.argv", ["meetingctl", "status", "--json"])

    rc = cli.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == _fixture("status_idle.json")


def test_cli_start_then_stop_json(monkeypatch, tmp_path: Path, capsys) -> None:
    state_file = tmp_path / "current.json"
    queue_file = tmp_path / "process_queue.jsonl"
    monkeypatch.setenv("MEETINGCTL_STATE_FILE", str(state_file))
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setattr(cli, "AudioHijackRecorder", lambda: FakeRecorder())

    monkeypatch.setattr(
        "sys.argv",
        [
            "meetingctl",
            "start",
            "--meeting-id",
            "m-123",
            "--title",
            "Weekly Sync",
            "--platform",
            "teams",
            "--note-path",
            "/tmp/weekly-sync.md",
            "--json",
        ],
    )
    assert cli.main() == 0
    start_payload = json.loads(capsys.readouterr().out)
    assert start_payload == _fixture("start_success.json")

    store = RuntimeStateStore(state_file)
    assert store.load_state() is not None

    monkeypatch.setattr("sys.argv", ["meetingctl", "stop", "--json"])
    assert cli.main() == 0
    stop_payload = json.loads(capsys.readouterr().out)
    assert stop_payload == _fixture("stop_success.json")
    queued = queue_file.read_text().strip().splitlines()
    assert len(queued) == 1
    assert json.loads(queued[0]) == stop_payload


def test_cli_start_uses_event_and_note_flow_when_title_missing(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    state_file = tmp_path / "current.json"
    monkeypatch.setenv("MEETINGCTL_STATE_FILE", str(state_file))
    monkeypatch.setattr(cli, "AudioHijackRecorder", lambda: FakeRecorder())
    monkeypatch.setattr(
        cli,
        "resolve_now_or_next_event",
        lambda now, window_minutes: {
            "title": "Calendar Meeting",
            "platform": "unknown",
            "start": "2026-02-08T10:00:00+00:00",
            "end": "2026-02-08T10:30:00+00:00",
            "calendar_name": "Work",
            "join_url": "",
        },
    )
    monkeypatch.setattr(
        cli,
        "create_note_from_event",
        lambda event: {"meeting_id": "m-evt", "note_path": "/tmp/cal.md"},
    )
    monkeypatch.setattr("sys.argv", ["meetingctl", "start", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["meeting_id"] == "m-evt"
    assert payload["fallback_used"] is True


def test_cli_start_adhoc_without_note_path_creates_note(monkeypatch, tmp_path: Path, capsys) -> None:
    state_file = tmp_path / "current.json"
    queue_file = tmp_path / "process_queue.jsonl"
    monkeypatch.setenv("MEETINGCTL_STATE_FILE", str(state_file))
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("DEFAULT_MEETINGS_FOLDER", "meetings")
    monkeypatch.setattr(cli, "AudioHijackRecorder", lambda: FakeRecorder())

    monkeypatch.setattr(
        "sys.argv",
        [
            "meetingctl",
            "start",
            "--meeting-id",
            "m-adhoc",
            "--title",
            "Adhoc Session",
            "--platform",
            "meet",
            "--json",
        ],
    )
    assert cli.main() == 0
    start_payload = json.loads(capsys.readouterr().out)
    assert start_payload["meeting_id"] == "m-adhoc"
    assert isinstance(start_payload["note_path"], str)
    assert start_payload["note_path"]

    monkeypatch.setattr("sys.argv", ["meetingctl", "stop", "--json"])
    assert cli.main() == 0
    _ = json.loads(capsys.readouterr().out)
    queued = queue_file.read_text().strip().splitlines()
    assert len(queued) == 1
    queued_payload = json.loads(queued[0])
    assert queued_payload["meeting_id"] == "m-adhoc"
    assert queued_payload["note_path"]


def test_cli_failed_jobs_lists_dead_letter_items(monkeypatch, tmp_path: Path, capsys) -> None:
    dead_letter = tmp_path / "process_queue.deadletter.jsonl"
    dead_letter.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "failed_at": "2026-02-28T12:00:00+00:00",
                        "error": "boom",
                        "payload": {"meeting_id": "m-1", "note_path": "/tmp/a.md"},
                    }
                ),
                json.dumps(
                    {
                        "failed_at": "2026-02-28T12:05:00+00:00",
                        "error": "bad audio",
                        "payload": {"meeting_id": "m-2", "note_path": "/tmp/b.md"},
                    }
                ),
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_DEAD_LETTER_FILE", str(dead_letter))
    monkeypatch.setattr("sys.argv", ["meetingctl", "failed-jobs", "--limit", "1", "--json"])

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["payload"]["meeting_id"] == "m-2"


def test_cli_failed_jobs_requeue_moves_items_back_to_queue(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    dead_letter = tmp_path / "process_queue.deadletter.jsonl"
    queue_file = tmp_path / "process_queue.jsonl"
    dead_letter.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "failed_at": "2026-02-28T12:00:00+00:00",
                        "error": "boom",
                        "payload": {"meeting_id": "m-1", "note_path": "/tmp/a.md"},
                    }
                ),
                json.dumps(
                    {
                        "failed_at": "2026-02-28T12:05:00+00:00",
                        "error": "bad audio",
                        "payload": {"meeting_id": "m-2", "note_path": "/tmp/b.md"},
                    }
                ),
            ]
        )
        + "\n"
    )
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_DEAD_LETTER_FILE", str(dead_letter))
    monkeypatch.setenv("MEETINGCTL_PROCESS_QUEUE_FILE", str(queue_file))
    monkeypatch.setattr(
        "sys.argv",
        ["meetingctl", "failed-jobs-requeue", "--meeting-id", "m-2", "--json"],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requeued"] == 1
    assert payload["remaining_failed"] == 1
    assert payload["meeting_ids"] == ["m-2"]
    queued = [json.loads(line) for line in queue_file.read_text().strip().splitlines()]
    assert len(queued) == 1
    assert queued[0]["meeting_id"] == "m-2"
    remaining_failed = [json.loads(line) for line in dead_letter.read_text().strip().splitlines()]
    assert len(remaining_failed) == 1
    assert remaining_failed[0]["payload"]["meeting_id"] == "m-1"
