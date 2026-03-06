from __future__ import annotations

import json
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
        except subprocess.TimeoutExpired as exc:
            timeout = _transcription_timeout_seconds()
            raise TranscriptionError(
                f"Whisper timed out after {timeout}s for {wav_path}"
            ) from exc
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
        except subprocess.TimeoutExpired as exc:
            timeout = _transcription_timeout_seconds()
            raise TranscriptionError(
                f"WhisperX timed out after {timeout}s for {wav_path}"
            ) from exc
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


class SidecarDiarizationTranscriptionRunner:
    def __init__(
        self,
        *,
        script_path: str,
        runner: Callable[..., object] | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        require_speaker_labels: bool = True,
    ) -> None:
        self.script_path = script_path
        self.runner = runner or _subprocess_run_captured
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.require_speaker_labels = require_speaker_labels

    def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
        if not wav_path.exists():
            raise TranscriptionError(
                f"Missing WAV input: {wav_path}. Stop recording before transcription."
            )
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        return self._run_sidecar(wav_path=wav_path, transcript_path=transcript_path, transcript_json_path=None)

    def diarize_existing_transcript(self, *, wav_path: Path, transcript_path: Path) -> Path:
        transcript_json_path = transcript_path.with_suffix(".json")
        if not transcript_json_path.exists():
            raise TranscriptionError(
                f"Cannot diarize existing transcript without JSON segments: {transcript_json_path}"
            )
        return self._run_sidecar(
            wav_path=wav_path,
            transcript_path=transcript_path,
            transcript_json_path=transcript_json_path,
        )

    def _build_command(
        self,
        *,
        wav_path: Path,
        transcript_path: Path,
        transcript_json_path: Path | None,
    ) -> list[str]:
        command = [self.script_path, str(wav_path), "--meeting-id", transcript_path.stem]
        if transcript_json_path is not None:
            command.extend(["--transcript-json", str(transcript_json_path)])
        if self.min_speakers is not None:
            command.extend(["--min-speakers", str(self.min_speakers)])
        if self.max_speakers is not None:
            command.extend(["--max-speakers", str(self.max_speakers)])
        if not self.require_speaker_labels:
            command.append("--allow-transcript-without-diarization")
        return command

    def _run_sidecar(
        self,
        *,
        wav_path: Path,
        transcript_path: Path,
        transcript_json_path: Path | None,
    ) -> Path:
        command = self._build_command(
            wav_path=wav_path,
            transcript_path=transcript_path,
            transcript_json_path=transcript_json_path,
        )
        try:
            result = self.runner(command, check=True)
        except subprocess.TimeoutExpired as exc:
            timeout = _transcription_timeout_seconds()
            raise TranscriptionError(
                f"Diarization sidecar timed out after {timeout}s for {wav_path}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = _extract_transcriber_failure_detail(_process_text(exc))
            raise TranscriptionError(f"Diarization sidecar failed for {wav_path}: {detail}") from exc

        manifest = _extract_sidecar_manifest(_process_text(result))
        if manifest is None:
            raise TranscriptionError(
                f"Diarization sidecar did not return a parseable manifest for {wav_path}"
            )
        diarization_succeeded = bool(manifest.get("diarization_succeeded", False))
        if self.require_speaker_labels and not diarization_succeeded:
            detail = str(manifest.get("diarization_error", "")).strip() or "unknown diarization failure"
            raise TranscriptionError(f"Diarization failed for {wav_path}: {detail}")

        sources = {
            ".txt": _resolve_sidecar_artifact_path(Path(str(manifest.get("transcript_txt", ""))).expanduser()),
            ".srt": _resolve_sidecar_artifact_path(Path(str(manifest.get("transcript_srt", ""))).expanduser()),
            ".json": _resolve_sidecar_artifact_path(Path(str(manifest.get("transcript_json", ""))).expanduser()),
        }
        for ext, source_path in sources.items():
            if not source_path.exists():
                raise TranscriptionError(f"Diarization sidecar missing expected artifact: {source_path}")
            diarized_target = transcript_path.with_name(f"{transcript_path.stem}.diarized{ext}")
            diarized_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, diarized_target)

            active_target = transcript_path if ext == ".txt" else transcript_path.with_suffix(ext)
            shutil.copyfile(source_path, active_target)
        return transcript_path


class PreferDiarizedTranscriptionRunner:
    def __init__(
        self,
        *,
        diarized: TranscriptionRunner,
        fallback: TranscriptionRunner,
        fallback_on_error: bool,
        keep_baseline: bool,
    ) -> None:
        self.diarized = diarized
        self.fallback = fallback
        self.fallback_on_error = fallback_on_error
        self.keep_baseline = keep_baseline

    def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
        try:
            output = self.diarized.transcribe(wav_path=wav_path, transcript_path=transcript_path)
            if self.keep_baseline:
                self._write_baseline(wav_path=wav_path, transcript_path=transcript_path)
            return output
        except Exception:
            if not self.fallback_on_error:
                raise
            output = self.fallback.transcribe(wav_path=wav_path, transcript_path=transcript_path)
            self._best_effort_diarize_existing_transcript(wav_path=wav_path, transcript_path=transcript_path)
            return output

    def _write_baseline(self, *, wav_path: Path, transcript_path: Path) -> None:
        baseline_path = transcript_path.with_name(f"{transcript_path.stem}.basic.txt")
        if baseline_path.exists():
            return
        try:
            self.fallback.transcribe(wav_path=wav_path, transcript_path=baseline_path)
        except Exception:
            # Baseline capture is best-effort and should not block the primary diarized path.
            return

    def _best_effort_diarize_existing_transcript(self, *, wav_path: Path, transcript_path: Path) -> None:
        if not isinstance(self.diarized, SidecarDiarizationTranscriptionRunner):
            return
        try:
            self.diarized.diarize_existing_transcript(wav_path=wav_path, transcript_path=transcript_path)
        except Exception:
            return


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
    allow_fallback = os.environ.get("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "1").strip().lower()
    fallback_enabled = allow_fallback not in {"0", "false", "no"}

    if backend in {"sidecar", "diarized", "diarization-sidecar"}:
        fallback = WhisperTranscriptionRunner(binary=_resolve_cli_binary("whisper"), model=model)
        script_override = os.environ.get("MEETINGCTL_DIARIZATION_SIDECAR_SCRIPT", "").strip()
        script_path = script_override or str(_default_sidecar_script_path())
        min_speakers = _env_optional_int("MEETINGCTL_DIARIZATION_MIN_SPEAKERS")
        max_speakers = _env_optional_int("MEETINGCTL_DIARIZATION_MAX_SPEAKERS")
        require_speaker_labels = _truthy_env(
            "MEETINGCTL_DIARIZATION_REQUIRE_SPEAKER_LABELS",
            default=True,
        )
        keep_baseline = _truthy_env("MEETINGCTL_DIARIZATION_KEEP_BASELINE", default=True)
        diarized = SidecarDiarizationTranscriptionRunner(
            script_path=script_path,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            require_speaker_labels=require_speaker_labels,
        )
        return PreferDiarizedTranscriptionRunner(
            diarized=diarized,
            fallback=fallback,
            fallback_on_error=fallback_enabled,
            keep_baseline=keep_baseline,
        )

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
        if fallback_enabled:
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


def _default_sidecar_script_path() -> Path:
    return (Path(__file__).resolve().parents[2] / "scripts" / "diarize_sidecar.sh").resolve()


def _resolve_sidecar_artifact_path(path: Path) -> Path:
    if path.exists():
        return path
    repo_root = Path(__file__).resolve().parents[2]
    raw = str(path)
    if raw.startswith("/shared/"):
        candidate = repo_root / "shared_data" / raw.removeprefix("/shared/")
        if candidate.exists():
            return candidate
    if raw.startswith("/workspace/"):
        candidate = repo_root / raw.removeprefix("/workspace/")
        if candidate.exists():
            return candidate
    return path


def _env_optional_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _truthy_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _extract_sidecar_manifest(log_text: str) -> dict[str, object] | None:
    for line in reversed(log_text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if "transcript_txt" in payload and "transcript_json" in payload:
            return payload
    return None


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
    completed = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=_transcription_timeout_seconds(),
    )
    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def _transcription_timeout_seconds() -> int:
    raw = os.environ.get("MEETINGCTL_TRANSCRIPTION_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return 1800
    try:
        value = int(raw)
    except ValueError:
        return 1800
    return max(value, 30)


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
