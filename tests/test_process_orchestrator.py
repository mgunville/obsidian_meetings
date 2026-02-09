from __future__ import annotations

from pathlib import Path

from meetingctl.process import ProcessContext, run_processing


def test_process_orchestrator_idempotent_rerun_reuses_transcript(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("# Note")
    wav = tmp_path / "audio.wav"
    wav.write_text("wav")
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("existing transcript")
    mp3 = tmp_path / "audio.mp3"
    transcribe_calls: list[tuple[Path, Path]] = []
    patch_calls: list[dict[str, object]] = []

    result = run_processing(
        context=ProcessContext(
            meeting_id="m-123",
            note_path=note,
            wav_path=wav,
            transcript_path=transcript,
            mp3_path=mp3,
        ),
        transcribe=lambda wav_path, transcript_path: transcribe_calls.append(
            (wav_path, transcript_path)
        )
        or transcript_path,
        summarize=lambda transcript_path: {"minutes": "ok", "reused": True},
        patch_note=lambda note_path, payload: patch_calls.append(payload),
        convert_audio=lambda wav_path, mp3_path: mp3_path,
    )

    assert result.reused_transcript is True
    assert result.reused_summary is True
    assert not transcribe_calls
    assert patch_calls and patch_calls[0]["minutes"] == "ok"


def test_process_orchestrator_runs_full_chain_when_transcript_missing(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("# Note")
    wav = tmp_path / "audio.wav"
    wav.write_text("wav")
    transcript = tmp_path / "transcript.txt"
    mp3 = tmp_path / "audio.mp3"
    steps: list[str] = []

    run_processing(
        context=ProcessContext(
            meeting_id="m-123",
            note_path=note,
            wav_path=wav,
            transcript_path=transcript,
            mp3_path=mp3,
        ),
        transcribe=lambda wav_path, transcript_path: steps.append("transcribe") or transcript_path,
        summarize=lambda transcript_path: steps.append("summarize") or {"minutes": "ok"},
        patch_note=lambda note_path, payload: steps.append("patch"),
        convert_audio=lambda wav_path, mp3_path: steps.append("convert") or mp3_path,
    )

    assert steps == ["transcribe", "summarize", "patch", "convert"]
