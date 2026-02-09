from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Iterator


class StateLockError(RuntimeError):
    pass


class RuntimeStateStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.lock_file = state_file.with_suffix(".lock")

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise StateLockError(
                f"Runtime state is locked at {self.lock_file}. If stale, remove the lock file."
            ) from exc
        try:
            os.close(fd)
            yield
        finally:
            if self.lock_file.exists():
                self.lock_file.unlink()

    def write_state(self, payload: dict[str, object]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, dir=self.state_file.parent
        ) as tmp:
            json.dump(payload, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.state_file)

    def load_state(self) -> dict[str, object] | None:
        if not self.state_file.exists():
            return None
        return json.loads(self.state_file.read_text())

    def clear_state(self) -> None:
        if self.state_file.exists():
            self.state_file.unlink()

    def is_stale(self, max_age_seconds: int) -> bool:
        state = self.load_state()
        if not state or not state.get("recording"):
            return False
        started_at = state.get("started_at")
        if not isinstance(started_at, str):
            return False
        started = datetime.fromisoformat(started_at)
        return (datetime.now(UTC) - started).total_seconds() > max_age_seconds
