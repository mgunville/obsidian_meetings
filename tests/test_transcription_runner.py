from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from meetingctl.transcription import (
    FallbackTranscriptionRunner,
    PreferDiarizedTranscriptionRunner,
    SidecarDiarizationTranscriptionRunner,
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


def test_transcription_reports_corrupt_media_when_transcript_missing(tmp_path: Path) -> None:
    wav = tmp_path / "bad.m4a"
    wav.write_text("bad")
    transcript_path = tmp_path / "out" / "transcript.txt"

    def _runner(args, check=True):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="",
            stderr="[mov,mp4,m4a] moov atom not found\nError opening input files: Invalid data found when processing input",
        )

    runner = WhisperTranscriptionRunner(runner=_runner)
    with pytest.raises(TranscriptionError) as excinfo:
        runner.transcribe(wav_path=wav, transcript_path=transcript_path)
    assert "corrupted or incomplete" in str(excinfo.value)


def test_transcription_reports_decode_failure_on_nonzero_exit(tmp_path: Path) -> None:
    wav = tmp_path / "bad2.m4a"
    wav.write_text("bad")
    transcript_path = tmp_path / "out" / "transcript.txt"

    def _runner(args, check=True):
        raise subprocess.CalledProcessError(
            183,
            args,
            output="",
            stderr="Error opening input files: Invalid data found when processing input",
        )

    runner = WhisperTranscriptionRunner(runner=_runner)
    with pytest.raises(TranscriptionError) as excinfo:
        runner.transcribe(wav_path=wav, transcript_path=transcript_path)
    assert "invalid media data" in str(excinfo.value)


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


def test_sidecar_runner_promotes_diarized_outputs(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "m-abc123.txt"
    job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True, exist_ok=True)
    side_txt = job_dir / "transcript_diarized.txt"
    side_srt = job_dir / "transcript_diarized.srt"
    side_json = job_dir / "transcript_diarized.json"
    side_txt.write_text("[00:00:00-00:00:01] SPEAKER_00: hello")
    side_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nSPEAKER_00: hello\n")
    side_json.write_text('{"segments":[{"speaker":"SPEAKER_00","text":"hello"}]}')

    manifest = {
        "transcript_txt": str(side_txt),
        "transcript_srt": str(side_srt),
        "transcript_json": str(side_json),
        "diarization_succeeded": True,
    }

    def _runner(args, check=True):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(manifest),
            stderr="",
        )

    runner = SidecarDiarizationTranscriptionRunner(
        script_path="/tmp/diarize_sidecar.sh",
        runner=_runner,
    )
    output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)

    assert output == transcript_path
    assert transcript_path.exists()
    assert transcript_path.read_text() == side_txt.read_text()
    assert transcript_path.with_suffix(".srt").exists()
    assert transcript_path.with_suffix(".json").exists()
    assert transcript_path.with_name("m-abc123.diarized.txt").exists()
    assert transcript_path.with_name("m-abc123.diarized.srt").exists()
    assert transcript_path.with_name("m-abc123.diarized.json").exists()


def test_sidecar_runner_can_diarize_existing_transcript_json(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "m-abc123.txt"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.with_suffix(".json").write_text('{"segments":[{"start":0.0,"end":1.0,"text":"hi"}]}')
    job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True, exist_ok=True)
    side_txt = job_dir / "transcript_diarized.txt"
    side_srt = job_dir / "transcript_diarized.srt"
    side_json = job_dir / "transcript_diarized.json"
    side_txt.write_text("[00:00:00-00:00:01] SPEAKER_00: hi")
    side_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nSPEAKER_00: hi\n")
    side_json.write_text('{"segments":[{"speaker":"SPEAKER_00","text":"hi"}]}')

    manifest = {
        "transcript_txt": str(side_txt),
        "transcript_srt": str(side_srt),
        "transcript_json": str(side_json),
        "diarization_succeeded": True,
    }

    calls: list[list[str]] = []

    def _runner(args, check=True):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(manifest),
            stderr="",
        )

    runner = SidecarDiarizationTranscriptionRunner(
        script_path="/tmp/diarize_sidecar.sh",
        runner=_runner,
    )
    output = runner.diarize_existing_transcript(wav_path=wav, transcript_path=transcript_path)

    assert output == transcript_path
    assert calls
    assert "--transcript-json" in calls[0]
    assert str(transcript_path.with_suffix(".json")) in calls[0]
    assert transcript_path.read_text() == side_txt.read_text()


def test_sidecar_runner_resolves_container_shared_manifest_paths(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "m-abc123.txt"
    repo_root = Path(__file__).resolve().parents[1]
    unique_dir = repo_root / "shared_data" / "diarization" / "jobs" / f"test-path-map-{uuid.uuid4().hex[:8]}"
    try:
        unique_dir.mkdir(parents=True, exist_ok=True)
        side_txt = unique_dir / "transcript_diarized.txt"
        side_srt = unique_dir / "transcript_diarized.srt"
        side_json = unique_dir / "transcript_diarized.json"
        side_txt.write_text("[00:00:00-00:00:01] SPEAKER_00: hello")
        side_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nSPEAKER_00: hello\n")
        side_json.write_text('{"segments":[{"speaker":"SPEAKER_00","text":"hello"}]}')

        manifest = {
            "transcript_txt": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.txt",
            "transcript_srt": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.srt",
            "transcript_json": f"/shared/diarization/jobs/{unique_dir.name}/transcript_diarized.json",
            "diarization_succeeded": True,
        }

        def _runner(args, check=True):
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(manifest),
                stderr="",
            )

        runner = SidecarDiarizationTranscriptionRunner(
            script_path="/tmp/diarize_sidecar.sh",
            runner=_runner,
        )
        output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)

        assert output == transcript_path
        assert transcript_path.exists()
        assert transcript_path.read_text() == side_txt.read_text()
        assert transcript_path.with_name("m-abc123.diarized.txt").exists()
    finally:
        shutil.rmtree(unique_dir, ignore_errors=True)


def test_prefer_diarized_runner_falls_back_to_whisper(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "m-abc123.txt"

    class _FailRunner:
        def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
            raise TranscriptionError("diarization failed")

    class _OkRunner:
        def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("fallback transcript")
            transcript_path.with_suffix(".srt").write_text("1\n")
            transcript_path.with_suffix(".json").write_text("{}")
            return transcript_path

    runner = PreferDiarizedTranscriptionRunner(
        diarized=_FailRunner(),
        fallback=_OkRunner(),
        fallback_on_error=True,
        keep_baseline=True,
    )
    output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)
    assert output == transcript_path
    assert transcript_path.read_text() == "fallback transcript"


def test_prefer_diarized_runner_attempts_post_fallback_diarization(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_text("dummy")
    transcript_path = tmp_path / "out" / "m-abc123.txt"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True, exist_ok=True)
    side_txt = job_dir / "transcript_diarized.txt"
    side_srt = job_dir / "transcript_diarized.srt"
    side_json = job_dir / "transcript_diarized.json"
    side_txt.write_text("[00:00:00-00:00:01] SPEAKER_00: diarized")
    side_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nSPEAKER_00: diarized\n")
    side_json.write_text('{"segments":[{"speaker":"SPEAKER_00","text":"diarized"}]}')
    manifest = {
        "transcript_txt": str(side_txt),
        "transcript_srt": str(side_srt),
        "transcript_json": str(side_json),
        "diarization_succeeded": True,
    }

    sidecar_calls: list[list[str]] = []

    def _sidecar_runner(args, check=True):
        sidecar_calls.append(args)
        if "--transcript-json" not in args:
            raise subprocess.CalledProcessError(1, args, output="", stderr="sidecar ASR failed")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(manifest),
            stderr="",
        )

    class _FallbackRunner:
        def transcribe(self, *, wav_path: Path, transcript_path: Path) -> Path:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("fallback transcript")
            transcript_path.with_suffix(".srt").write_text("1\n")
            transcript_path.with_suffix(".json").write_text('{"segments":[{"start":0.0,"end":1.0,"text":"hi"}]}')
            return transcript_path

    sidecar = SidecarDiarizationTranscriptionRunner(
        script_path="/tmp/diarize_sidecar.sh",
        runner=_sidecar_runner,
    )
    runner = PreferDiarizedTranscriptionRunner(
        diarized=sidecar,
        fallback=_FallbackRunner(),
        fallback_on_error=True,
        keep_baseline=False,
    )
    output = runner.transcribe(wav_path=wav, transcript_path=transcript_path)

    assert output == transcript_path
    assert len(sidecar_calls) == 2
    assert "--transcript-json" not in sidecar_calls[0]
    assert "--transcript-json" in sidecar_calls[1]
    assert transcript_path.read_text() == side_txt.read_text()


def test_create_transcription_runner_selects_sidecar_backend(monkeypatch) -> None:
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_BACKEND", "sidecar")
    monkeypatch.setenv("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "1")
    monkeypatch.setenv("MEETINGCTL_DIARIZATION_KEEP_BASELINE", "1")
    monkeypatch.setenv("MEETINGCTL_DIARIZATION_SIDECAR_SCRIPT", "/tmp/diarize_sidecar.sh")

    runner = create_transcription_runner()

    assert isinstance(runner, PreferDiarizedTranscriptionRunner)
