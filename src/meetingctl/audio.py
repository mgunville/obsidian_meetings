from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable


def convert_wav_to_mp3(
    *,
    wav_path: Path,
    mp3_path: Path | None = None,
    ffmpeg_binary: str = "ffmpeg",
    runner: Callable[..., object] | None = None,
) -> Path:
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV not found: {wav_path}")
    target = mp3_path or wav_path.with_suffix(".mp3")
    target.parent.mkdir(parents=True, exist_ok=True)
    run = runner or subprocess.run
    run(
        [ffmpeg_binary, "-y", "-i", str(wav_path), str(target)],
        check=True,
    )
    wav_path.unlink()
    return target
