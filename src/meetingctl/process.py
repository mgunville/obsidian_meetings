from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from meetingctl.audio import convert_wav_to_mp3


@dataclass(frozen=True)
class ProcessContext:
    meeting_id: str
    note_path: Path
    wav_path: Path
    transcript_path: Path
    mp3_path: Path


@dataclass(frozen=True)
class ProcessResult:
    meeting_id: str
    transcript_path: Path
    mp3_path: Path
    note_path: Path
    reused_transcript: bool
    reused_summary: bool


def run_processing(
    *,
    context: ProcessContext,
    transcribe: Callable[[Path, Path], Path],
    summarize: Callable[[Path], dict[str, object]],
    patch_note: Callable[[Path, dict[str, object]], None],
    convert_audio: Callable[[Path, Path], Path] | None = None,
) -> ProcessResult:
    reused_transcript = context.transcript_path.exists()
    if not reused_transcript:
        transcribe(context.wav_path, context.transcript_path)

    summary_payload = summarize(context.transcript_path)
    reused_summary = bool(summary_payload.get("reused", False))
    patch_note(context.note_path, summary_payload)
    converter = convert_audio or (lambda wav, mp3: convert_wav_to_mp3(wav_path=wav, mp3_path=mp3))
    mp3_path = converter(context.wav_path, context.mp3_path)

    return ProcessResult(
        meeting_id=context.meeting_id,
        transcript_path=context.transcript_path,
        mp3_path=mp3_path,
        note_path=context.note_path,
        reused_transcript=reused_transcript,
        reused_summary=reused_summary,
    )
