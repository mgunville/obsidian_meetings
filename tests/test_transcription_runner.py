from __future__ import annotations

from pathlib import Path

import pytest

from meetingctl.transcription import (
    FallbackTranscriptionRunner,
    TranscriptionError,
    WhisperTranscriptionRunner,
    WhisperXTranscriptionRunner,
    create_transcription_runner,
)


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
    generated = transcript_path.parent / "audio.txt"
    generated_srt = transcript_path.parent / "audio.srt"
    generated_json = transcript_path.parent / "audio.json"

    def _runner(args, check=True):
        calls.append(args)
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("hello")
        generated_srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nhello\n")
        generated_json.write_text('{"segments":[]}')

    runner = WhisperTranscriptionRunner(runner=_runner)

    output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)

    assert output == transcript_path
    assert transcript_path.exists()
    assert transcript_path.read_text() == "hello"
    assert (transcript_path.parent / "transcript.srt").exists()
    assert (transcript_path.parent / "transcript.json").exists()
    assert calls
    assert str(wav) in calls[0]
    assert "--output_dir" in calls[0]
    assert "--output_format" in calls[0]
    assert "all" in calls[0]


def test_whisperx_transcription_invokes_runner_for_existing_wav(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "transcript.txt"
    generated = transcript_path.parent / "audio.txt"
    generated_srt = transcript_path.parent / "audio.srt"
    generated_json = transcript_path.parent / "audio.json"

    def _runner(args, check=True):
        calls.append(args)
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("hello-x")
        generated_srt.write_text("1\n00:00:00,000 --> 00:00:00,500\nhello\n")
        generated_json.write_text('{"segments":[]}')

    runner = WhisperXTranscriptionRunner(runner=_runner, compute_type="int8", vad_method="silero")
    output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)

    assert output == transcript_path
    assert transcript_path.exists()
    assert transcript_path.read_text() == "hello-x"
    assert (transcript_path.parent / "transcript.srt").exists()
    assert (transcript_path.parent / "transcript.json").exists()
    assert calls
    assert calls[0][0] == "whisperx"
    assert "--output_dir" in calls[0]
    assert "--output_format" in calls[0]
    assert "all" in calls[0]
    assert "--compute_type" in calls[0]
    assert "int8" in calls[0]
    assert "--vad_method" in calls[0]
    assert "silero" in calls[0]


def test_create_transcription_runner_selects_whisperx(monkeypatch) -> None:
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_BACKEND", "whisperx")
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_MODEL", "small")
    monkeypatch.setenv("MEETINGCTL_WHISPERX_COMPUTE_TYPE", "int8")
    monkeypatch.setenv("MEETINGCTL_WHISPERX_VAD_METHOD", "silero")
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "0")

    runner = create_transcription_runner()

    assert isinstance(runner, WhisperXTranscriptionRunner)
    assert runner.model == "small" or runner.model.endswith("/config/models/whisperx/faster-whisper-base")
    assert runner.compute_type == "int8"
    assert runner.vad_method == "silero"


def test_create_transcription_runner_prefers_local_model_path(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "faster-whisper-base"
    model_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_BACKEND", "whisperx")
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "0")
    monkeypatch.setenv("MEETINGCTL_WHISPERX_MODEL_PATH", str(model_dir))

    runner = create_transcription_runner()

    assert isinstance(runner, WhisperXTranscriptionRunner)
    assert runner.model == str(model_dir.resolve())


def test_create_transcription_runner_defaults_to_whisper(monkeypatch) -> None:
    monkeypatch.delenv("MEETINGCTL_TRANSCRIPTION_BACKEND", raising=False)
    monkeypatch.delenv("MEETINGCTL_TRANSCRIPTION_MODEL", raising=False)
    monkeypatch.delenv("MEETINGCTL_WHISPERX_COMPUTE_TYPE", raising=False)

    runner = create_transcription_runner()

    assert isinstance(runner, WhisperTranscriptionRunner)


def test_create_transcription_runner_uses_whisper_fallback_by_default(monkeypatch) -> None:
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_BACKEND", "whisperx")
    monkeypatch.delenv("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", raising=False)

    runner = create_transcription_runner()

    assert isinstance(runner, FallbackTranscriptionRunner)
    assert isinstance(runner.primary, WhisperXTranscriptionRunner)
    assert isinstance(runner.fallback, WhisperTranscriptionRunner)
