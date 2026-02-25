from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from meetingctl.audio import convert_wav_to_mp3


def test_convert_wav_to_mp3_deletes_wav_on_success(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    mp3 = tmp_path / "audio.mp3"
    wav.write_text("wav")

    def fake_runner(args: list[str], check: bool = True) -> None:
        mp3.write_text("mp3")

    out = convert_wav_to_mp3(wav_path=wav, mp3_path=mp3, runner=fake_runner)
    assert out == mp3
    assert mp3.exists()
    assert not wav.exists()


def test_convert_wav_to_mp3_keeps_wav_on_failure(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    mp3 = tmp_path / "audio.mp3"
    wav.write_text("wav")

    def failing_runner(args: list[str], check: bool = True) -> None:
        raise RuntimeError("ffmpeg failed")

    with pytest.raises(RuntimeError):
        convert_wav_to_mp3(wav_path=wav, mp3_path=mp3, runner=failing_runner)
    assert wav.exists()
    assert not mp3.exists()


def test_convert_wav_to_mp3_skips_reencode_when_existing_mp3_is_high_quality(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    mp3 = tmp_path / "audio.mp3"
    wav.write_text("wav")
    mp3.write_text("existing")
    run_calls: list[list[str]] = []

    def fake_runner(args: list[str], check: bool = True) -> None:
        run_calls.append(args)

    def fake_probe_runner(
        args: list[str], capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="196000\n", stderr="")

    out = convert_wav_to_mp3(
        wav_path=wav,
        mp3_path=mp3,
        runner=fake_runner,
        probe_runner=fake_probe_runner,
    )
    assert out == mp3
    assert mp3.read_text() == "existing"
    assert not wav.exists()
    assert not run_calls


def test_convert_wav_to_mp3_keeps_m4a_source(tmp_path: Path) -> None:
    m4a = tmp_path / "audio.m4a"
    mp3 = tmp_path / "audio.mp3"
    m4a.write_text("m4a")

    def fake_runner(args: list[str], check: bool = True) -> None:
        mp3.write_text("mp3")

    out = convert_wav_to_mp3(wav_path=m4a, mp3_path=mp3, runner=fake_runner)
    assert out == mp3
    assert mp3.exists()
    assert m4a.exists()
