from __future__ import annotations

import os
import subprocess
from typing import Protocol


class CommandRunner(Protocol):
    def __call__(self, args: list[str], check: bool = ...) -> subprocess.CompletedProcess[str]:
        ...


class AudioHijackRecorder:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or subprocess.run

    def start(self, session_name: str) -> None:
        if os.environ.get("MEETINGCTL_RECORDING_DRY_RUN") == "1":
            return
        self._runner(
            [
                "osascript",
                "-e",
                f'tell application "Audio Hijack" to start (first session whose name is "{session_name}")',
            ],
            check=True,
        )

    def stop(self, session_name: str) -> None:
        if os.environ.get("MEETINGCTL_RECORDING_DRY_RUN") == "1":
            return
        self._runner(
            [
                "osascript",
                "-e",
                f'tell application "Audio Hijack" to stop (first session whose name is "{session_name}")',
            ],
            check=True,
        )
