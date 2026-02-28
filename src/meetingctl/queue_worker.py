from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterator, Literal


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
    failure_mode: Literal["stop", "dead_letter"] = "stop",
    dead_letter_file: Path | None = None,
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
        failed_payloads: list[dict[str, object]] = []

        consumed = 0
        while consumed < min(max_jobs, len(raw_lines)):
            line = raw_lines[consumed]
            payload: dict[str, object] | None = None
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Queue payload must be a JSON object")
                handler(payload)
            except Exception as exc:
                failed += 1
                failure_reason = str(exc)
                if failure_mode == "dead_letter":
                    failed_payloads.append(
                        {
                            "failed_at": datetime.now(UTC).isoformat(),
                            "error": str(exc),
                            "payload": payload if isinstance(payload, dict) else {"raw_line": line},
                        }
                    )
                else:
                    break
            else:
                processed += 1
            consumed += 1

        remaining_lines = raw_lines[consumed:]
        if failure_mode == "stop" and failed > 0:
            # Put unprocessed lines back including failed line at head.
            remaining_lines = raw_lines[processed:]
        if remaining_lines:
            _atomic_write_lines(queue_file, remaining_lines)
        else:
            queue_file.unlink(missing_ok=True)

        if failed_payloads and dead_letter_file is not None:
            dead_letter_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(dead_letter_file.parent, 0o700)
            except OSError:
                pass
            with dead_letter_file.open("a", encoding="utf-8") as fh:
                for item in failed_payloads:
                    fh.write(json.dumps(item))
                    fh.write("\n")
            try:
                os.chmod(dead_letter_file, 0o600)
            except OSError:
                pass

        result = {
            "processed_jobs": processed,
            "failed_jobs": failed,
            "remaining_jobs": len(remaining_lines),
        }
        if failure_reason:
            result["failure_reason"] = failure_reason
        return result
