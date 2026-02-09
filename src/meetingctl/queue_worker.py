from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterator


class QueueLockError(RuntimeError):
    pass


def _atomic_write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=path.parent
    ) as tmp:
        for line in lines:
            tmp.write(line)
            tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


@contextmanager
def _queue_lock(lock_file: Path) -> Iterator[None]:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise QueueLockError(f"Queue lock already held: {lock_file}") from exc
    try:
        os.close(fd)
        yield
    finally:
        if lock_file.exists():
            lock_file.unlink()


def process_queue_jobs(
    *,
    queue_file: Path,
    handler: Callable[[dict[str, object]], None],
    max_jobs: int = 1,
) -> dict[str, object]:
    lock_file = queue_file.with_suffix(".lock")
    with _queue_lock(lock_file):
        if not queue_file.exists():
            return {"processed_jobs": 0, "failed_jobs": 0, "remaining_jobs": 0}

        raw_lines = [line.strip() for line in queue_file.read_text().splitlines() if line.strip()]
        if not raw_lines:
            queue_file.unlink(missing_ok=True)
            return {"processed_jobs": 0, "failed_jobs": 0, "remaining_jobs": 0}

        processed = 0
        failed = 0
        failure_reason = None

        while processed < min(max_jobs, len(raw_lines)):
            line = raw_lines[processed]
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Queue payload must be a JSON object")
                handler(payload)
            except Exception as exc:
                failed = 1
                failure_reason = str(exc)
                break
            processed += 1

        remaining_lines = raw_lines[processed:]
        if remaining_lines:
            _atomic_write_lines(queue_file, remaining_lines)
        else:
            queue_file.unlink(missing_ok=True)

        result = {
            "processed_jobs": processed,
            "failed_jobs": failed,
            "remaining_jobs": len(remaining_lines),
        }
        if failure_reason:
            result["failure_reason"] = failure_reason
        return result
