from __future__ import annotations

import json
from pathlib import Path

import pytest

from meetingctl.queue_worker import QueueLockError, process_queue_jobs


def _write_queue(path: Path, payloads: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(payload) for payload in payloads]
    path.write_text("\n".join(lines) + "\n")


def test_queue_worker_processes_jobs_and_removes_processed(tmp_path: Path) -> None:
    queue_file = tmp_path / "queue.jsonl"
    _write_queue(
        queue_file,
        [{"meeting_id": "m-1"}, {"meeting_id": "m-2"}],
    )
    seen: list[str] = []

    result = process_queue_jobs(
        queue_file=queue_file,
        handler=lambda payload: seen.append(str(payload["meeting_id"])),
        max_jobs=1,
    )

    assert seen == ["m-1"]
    assert result == {"processed_jobs": 1, "failed_jobs": 0, "remaining_jobs": 1}
    remaining = queue_file.read_text().strip().splitlines()
    assert len(remaining) == 1
    assert json.loads(remaining[0])["meeting_id"] == "m-2"


def test_queue_worker_failure_keeps_failed_job_in_queue(tmp_path: Path) -> None:
    queue_file = tmp_path / "queue.jsonl"
    _write_queue(
        queue_file,
        [{"meeting_id": "m-1"}, {"meeting_id": "m-2"}],
    )

    calls = 0

    def handler(payload: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        if payload["meeting_id"] == "m-2":
            raise RuntimeError("boom")

    result = process_queue_jobs(queue_file=queue_file, handler=handler, max_jobs=2)

    assert calls == 2
    assert result["processed_jobs"] == 1
    assert result["failed_jobs"] == 1
    assert result["remaining_jobs"] == 1
    remaining = queue_file.read_text().strip().splitlines()
    assert len(remaining) == 1
    assert json.loads(remaining[0])["meeting_id"] == "m-2"


def test_queue_worker_raises_on_lock_contention(tmp_path: Path) -> None:
    queue_file = tmp_path / "queue.jsonl"
    _write_queue(queue_file, [{"meeting_id": "m-1"}])
    lock_file = queue_file.with_suffix(".lock")
    lock_file.write_text("held")

    with pytest.raises(QueueLockError):
        process_queue_jobs(queue_file=queue_file, handler=lambda payload: None, max_jobs=1)
