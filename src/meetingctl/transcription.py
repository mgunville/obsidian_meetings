from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
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
        self.runner = runner or _subprocess_run_captured

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
        try:
            result = self.runner(command, check=True)
        except subprocess.CalledProcessError as exc:
            detail = _extract_transcriber_failure_detail(_process_text(exc))
            raise TranscriptionError(f"Whisper failed for {wav_path}: {detail}") from exc
        _promote_transcript_artifacts(
            output_dir=transcript_path.parent,
            generated_stem=generated_stem,
            target_stem=target_stem,
        )
        if not transcript_path.exists():
            detail = _extract_transcriber_failure_detail(_process_text(result))
            raise TranscriptionError(
                f"Whisper did not produce a transcript for {wav_path}: {detail}"
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
        self.runner = runner or _subprocess_run_captured
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
        try:
            result = self.runner(command, check=True)
        except subprocess.CalledProcessError as exc:
            detail = _extract_transcriber_failure_detail(_process_text(exc))
            raise TranscriptionError(f"WhisperX failed for {wav_path}: {detail}") from exc
        _promote_transcript_artifacts(
            output_dir=transcript_path.parent,
            generated_stem=generated_stem,
            target_stem=target_stem,
        )
        if not transcript_path.exists():
            detail = _extract_transcriber_failure_detail(_process_text(result))
            raise TranscriptionError(
                f"WhisperX did not produce a transcript for {wav_path}: {detail}"
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


def _resolve_cli_binary(name: str) -> str:
    direct = shutil.which(name)
    if direct:
        return direct
    candidates = [
        Path(sys.executable).parent / name,
        Path(sys.prefix) / "bin" / name,
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return name


def create_transcription_runner() -> TranscriptionRunner:
    backend = os.environ.get("MEETINGCTL_TRANSCRIPTION_BACKEND", "whisper").strip().lower()
    model = os.environ.get("MEETINGCTL_TRANSCRIPTION_MODEL", "base").strip() or "base"
    if backend == "whisperx":
        model_ref = _resolve_whisperx_model_ref(default_model=model)
        compute_type = os.environ.get("MEETINGCTL_WHISPERX_COMPUTE_TYPE", "").strip() or None
        vad_method = os.environ.get("MEETINGCTL_WHISPERX_VAD_METHOD", "silero").strip() or "silero"
        primary = WhisperXTranscriptionRunner(
            binary=_resolve_cli_binary("whisperx"),
            model=model_ref,
            compute_type=compute_type,
            vad_method=vad_method,
        )
        allow_fallback = os.environ.get("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "1").strip().lower()
        if allow_fallback not in {"0", "false", "no"}:
            return FallbackTranscriptionRunner(
                primary=primary,
                fallback=WhisperTranscriptionRunner(binary=_resolve_cli_binary("whisper"), model=model),
            )
        return primary
    return WhisperTranscriptionRunner(binary=_resolve_cli_binary("whisper"), model=model)


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


def _subprocess_run_captured(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, check=False, capture_output=True, text=True)
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def _process_text(result: object) -> str:
    stdout = getattr(result, "stdout", "")
    stderr = getattr(result, "stderr", "")
    output = getattr(result, "output", "")
    parts = []
    if isinstance(stdout, str) and stdout.strip():
        parts.append(stdout)
    if isinstance(stderr, str) and stderr.strip():
        parts.append(stderr)
    if isinstance(output, str) and output.strip():
        parts.append(output)
    return "\n".join(parts)


def _extract_transcriber_failure_detail(log_text: str) -> str:
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    if any("moov atom not found" in line.lower() for line in lines):
        return "audio file appears corrupted or incomplete (moov atom not found)"
    if any("invalid data found when processing input" in line.lower() for line in lines):
        return "invalid media data (ffmpeg could not decode input)"
    if any("failed to load audio" in line.lower() for line in lines):
        return "audio decode failure"
    if lines:
        return lines[-1]
    return "transcriber exited without creating transcript"
