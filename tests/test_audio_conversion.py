from __future__ import annotations

from pathlib import Path

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
