from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable


class TranscriptionError(RuntimeError):
    pass


class WhisperTranscriptionRunner:
    def __init__(
        self,
        *,
        binary: str = "whisper",
        model: str = "base",
        runner: Callable[..., object] | None = None,
    ) -> None:
        self.binary = binary
        self.model = model
        self.runner = runner or subprocess.run

    def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
        if not wav_path.exists():
            raise TranscriptionError(
                f"Missing WAV input: {wav_path}. Stop recording before transcription."
            )
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self.runner(
            [
                self.binary,
                str(wav_path),
                "--model",
                self.model,
                "--output",
                str(transcript_path),
            ],
            check=True,
        )
        return transcript_path
