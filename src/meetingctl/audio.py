from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import Callable


def _probe_bitrate_kbps(
    *,
    mp3_path: Path,
    ffprobe_binary: str,
    runner: Callable[..., object] | None,
) -> int | None:
    run = runner or subprocess.run
    result = run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=bit_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(mp3_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    output = str(getattr(result, "stdout", "")).strip()
    if not output:
        return None
    try:
        return int(output) // 1000
    except ValueError:
        return None


def convert_wav_to_mp3(
    *,
    wav_path: Path,
    mp3_path: Path | None = None,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    target_bitrate_kbps: int = 192,
    upgrade_if_bitrate_at_or_below_kbps: int = 128,
    runner: Callable[..., object] | None = None,
    probe_runner: Callable[..., object] | None = None,
) -> Path:
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV not found: {wav_path}")
    target = mp3_path or wav_path.with_suffix(".mp3")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target_bitrate_kbps <= 0:
        raise ValueError("target_bitrate_kbps must be greater than zero")

    if target.exists():
        existing_bitrate = _probe_bitrate_kbps(
            mp3_path=target,
            ffprobe_binary=ffprobe_binary,
            runner=probe_runner,
        )
        if existing_bitrate is not None and existing_bitrate > upgrade_if_bitrate_at_or_below_kbps:
            if wav_path.suffix.lower() == ".wav":
                wav_path.unlink()
            return target

    run = runner or subprocess.run
    bitrate_value = f"{target_bitrate_kbps}k"
    temp_target = Path(
        tempfile.NamedTemporaryFile(
            prefix=f".{target.stem}-",
            suffix=".mp3",
            dir=target.parent,
            delete=False,
        ).name
    )
    run(
        [
            ffmpeg_binary,
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate_value,
            str(temp_target),
        ],
        check=True,
    )
    temp_target.replace(target)
    if wav_path.suffix.lower() == ".wav":
        wav_path.unlink()
    return target
