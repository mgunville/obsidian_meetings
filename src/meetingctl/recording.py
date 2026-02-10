from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Protocol


class CommandRunner(Protocol):
    def __call__(self, args: list[str], check: bool = ...) -> subprocess.CompletedProcess[str]:
        ...


def _jxa_session_script(*, action: str, session_name: str) -> str:
    escaped = session_name.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
const app = Application("Audio Hijack");
const session = app.sessionWithName("{escaped}");
if (!session.exists()) {{
  throw new Error("Session not found: {escaped}");
}}
session.{action}();
""".strip()


class AudioHijackRecorder:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or subprocess.run

    def _run_configured_script(self, env_var: str) -> bool:
        script_path = os.environ.get(env_var, "").strip()
        if not script_path:
            return False
        resolved = Path(script_path).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Configured Audio Hijack script not found: {resolved}")
        self._runner(
            [
                "open",
                "-a",
                "Audio Hijack",
                str(resolved),
            ],
            check=True,
        )
        return True

    def start(self, session_name: str) -> None:
        if os.environ.get("MEETINGCTL_RECORDING_DRY_RUN") == "1":
            return
        if self._run_configured_script("MEETINGCTL_AUDIO_HIJACK_START_SCRIPT"):
            return
        self._runner(
            [
                "osascript",
                "-l",
                "JavaScript",
                "-e",
                _jxa_session_script(action="start", session_name=session_name),
            ],
            check=True,
        )

    def stop(self, session_name: str) -> None:
        if os.environ.get("MEETINGCTL_RECORDING_DRY_RUN") == "1":
            return
        if self._run_configured_script("MEETINGCTL_AUDIO_HIJACK_STOP_SCRIPT"):
            return
        self._runner(
            [
                "osascript",
                "-l",
                "JavaScript",
                "-e",
                _jxa_session_script(action="stop", session_name=session_name),
            ],
            check=True,
        )
