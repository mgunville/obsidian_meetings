from __future__ import annotations

from pathlib import Path

import pytest

from meetingctl.transcription import TranscriptionError, WhisperTranscriptionRunner


def test_transcription_missing_wav_is_actionable(tmp_path: Path) -> None:
    runner = WhisperTranscriptionRunner(runner=lambda *args, **kwargs: None)
    with pytest.raises(TranscriptionError) as excinfo:
        runner.transcribe(
            wav_path=tmp_path / "missing.wav",
            transcript_path=tmp_path / "transcript.txt",
        )
    assert "Missing WAV input" in str(excinfo.value)


def test_transcription_invokes_runner_for_existing_wav(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "transcript.txt"
    runner = WhisperTranscriptionRunner(runner=lambda args, check=True: calls.append(args))

    output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)

    assert output == transcript_path
    assert calls
    assert str(wav) in calls[0]
