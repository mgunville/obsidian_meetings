from __future__ import annotations

from datetime import datetime
import hashlib
import re
from pathlib import Path


def sanitize_title(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", title).strip()
    return re.sub(r"\s+", " ", cleaned) or "Untitled Meeting"


def generate_meeting_id(*, title: str, start_iso: str) -> str:
    token = f"{start_iso}|{sanitize_title(title).lower()}"
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:10]
    return f"m-{digest}"


def build_note_filename(*, start_dt: datetime, title: str, meeting_id: str) -> str:
    return f"{start_dt.strftime('%Y-%m-%d %H%M')} - {sanitize_title(title)} - {meeting_id}.md"


def ensure_collision_safe_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
