from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Callable, Protocol


class TranscriptionError(RuntimeError):
    pass


class TranscriptionRunner(Protocol):
    def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path: ...


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
        generated_stem = wav_path.stem
        target_stem = transcript_path.stem
        self.runner(
            [
                self.binary,
                str(wav_path),
                "--model",
                self.model,
                "--output_dir",
                str(transcript_path.parent),
                "--output_format",
                "all",
            ],
            check=True,
        )
        _promote_transcript_artifacts(
            output_dir=transcript_path.parent,
            generated_stem=generated_stem,
            target_stem=target_stem,
        )
        if not transcript_path.exists():
            raise TranscriptionError(
                "Whisper completed but transcript file was not created at expected path: "
                f"{transcript_path}"
            )
        return transcript_path


class WhisperXTranscriptionRunner:
    def __init__(
        self,
        *,
        binary: str = "whisperx",
        model: str = "base",
        runner: Callable[..., object] | None = None,
        compute_type: str | None = None,
        vad_method: str = "silero",
    ) -> None:
        self.binary = binary
        self.model = model
        self.runner = runner or subprocess.run
        self.compute_type = compute_type
        self.vad_method = vad_method

    def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
        if not wav_path.exists():
            raise TranscriptionError(
                f"Missing WAV input: {wav_path}. Stop recording before transcription."
            )
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        generated_stem = wav_path.stem
        target_stem = transcript_path.stem
        command = [
            self.binary,
            str(wav_path),
            "--model",
            self.model,
            "--output_dir",
            str(transcript_path.parent),
            "--output_format",
            "all",
        ]
        if self.compute_type:
            command.extend(["--compute_type", self.compute_type])
        if self.vad_method:
            command.extend(["--vad_method", self.vad_method])
        self.runner(command, check=True)
        _promote_transcript_artifacts(
            output_dir=transcript_path.parent,
            generated_stem=generated_stem,
            target_stem=target_stem,
        )
        if not transcript_path.exists():
            raise TranscriptionError(
                "WhisperX completed but transcript file was not created at expected path: "
                f"{transcript_path}"
            )
        return transcript_path


class FallbackTranscriptionRunner:
    def __init__(self, *, primary: TranscriptionRunner, fallback: TranscriptionRunner) -> None:
        self.primary = primary
        self.fallback = fallback

    def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
        try:
            return self.primary.transcribe(wav_path=wav_path, transcript_path=transcript_path)
        except Exception:
            return self.fallback.transcribe(wav_path=wav_path, transcript_path=transcript_path)


def create_transcription_runner() -> TranscriptionRunner:
    backend = os.environ.get("MEETINGCTL_TRANSCRIPTION_BACKEND", "whisper").strip().lower()
    model = os.environ.get("MEETINGCTL_TRANSCRIPTION_MODEL", "base").strip() or "base"
    if backend == "whisperx":
        model_ref = _resolve_whisperx_model_ref(default_model=model)
        compute_type = os.environ.get("MEETINGCTL_WHISPERX_COMPUTE_TYPE", "").strip() or None
        vad_method = os.environ.get("MEETINGCTL_WHISPERX_VAD_METHOD", "silero").strip() or "silero"
        primary = WhisperXTranscriptionRunner(
            model=model_ref,
            compute_type=compute_type,
            vad_method=vad_method,
        )
        allow_fallback = os.environ.get("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "1").strip().lower()
        if allow_fallback not in {"0", "false", "no"}:
            return FallbackTranscriptionRunner(
                primary=primary,
                fallback=WhisperTranscriptionRunner(model=model),
            )
        return primary
    return WhisperTranscriptionRunner(model=model)


def _resolve_whisperx_model_ref(*, default_model: str) -> str:
    explicit = os.environ.get("MEETINGCTL_WHISPERX_MODEL_PATH", "").strip()
    if explicit:
        explicit_path = Path(explicit).expanduser().resolve()
        if explicit_path.exists():
            return str(explicit_path)
    repo_local = Path(__file__).resolve().parents[2] / "config" / "models" / "whisperx" / "faster-whisper-base"
    if repo_local.exists():
        return str(repo_local)
    return default_model


def _promote_transcript_artifacts(
    *,
    output_dir: Path,
    generated_stem: str,
    target_stem: str,
) -> None:
    for ext in (".txt", ".srt", ".json"):
        generated_path = output_dir / f"{generated_stem}{ext}"
        target_path = output_dir / f"{target_stem}{ext}"
        if not generated_path.exists():
            continue
        if generated_path == target_path:
            continue
        target_path.unlink(missing_ok=True)
        generated_path.replace(target_path)
