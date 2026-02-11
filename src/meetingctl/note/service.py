from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re

from meetingctl.note.identity import (
    build_note_filename,
    ensure_collision_safe_path,
    generate_meeting_id,
)
from meetingctl.note.template import render_meeting_note


def _note_directory() -> Path:
    vault_path = Path(os.environ.get("VAULT_PATH", ".")).expanduser().resolve()
    meetings_folder = Path(os.environ.get("DEFAULT_MEETINGS_FOLDER", "meetings"))
    note_dir = (vault_path / meetings_folder).resolve()
    note_dir.mkdir(parents=True, exist_ok=True)
    return note_dir


def _local_tz():
    return datetime.now().astimezone().tzinfo or UTC


def _to_local_naive(iso_value: str) -> datetime:
    dt = datetime.fromisoformat(iso_value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(_local_tz())
    return dt.replace(tzinfo=None)


def _write_note(
    *,
    title: str,
    start_iso: str,
    end_iso: str,
    calendar_name: str,
    platform: str,
    join_url: str,
    recording_wav_rel: str,
    start_human: str,
    end_human: str,
    meeting_id: str,
) -> dict[str, str]:
    note_dir = _note_directory()
    start_dt = _to_local_naive(start_iso)
    filename = build_note_filename(start_dt=start_dt, title=title, meeting_id=meeting_id)
    note_path = ensure_collision_safe_path(note_dir / filename)
    rendered = render_meeting_note(
        {
            "meeting_id": meeting_id,
            "title": title,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "calendar_name": calendar_name,
            "platform": platform,
            "join_url": join_url,
            "recording_wav_rel": recording_wav_rel,
            "start_human": start_human,
            "end_human": end_human,
        }
    )
    note_path.write_text(rendered)
    return {"meeting_id": meeting_id, "note_path": str(note_path)}


def preview_note_from_event(
    event: dict[str, object],
    *,
    meeting_id: str | None = None,
) -> dict[str, str]:
    title = str(event.get("title", "Untitled Meeting"))
    start_iso = str(event.get("start"))
    resolved_meeting_id = meeting_id or generate_meeting_id(title=title, start_iso=start_iso)
    start_dt = _to_local_naive(start_iso)
    filename = build_note_filename(start_dt=start_dt, title=title, meeting_id=resolved_meeting_id)
    note_path = ensure_collision_safe_path(_note_directory() / filename)
    return {"meeting_id": resolved_meeting_id, "note_path": str(note_path)}


def create_note_from_event(event: dict[str, object]) -> dict[str, str]:
    title = str(event.get("title", "Untitled Meeting"))
    start_iso = str(event.get("start"))
    end_iso = str(event.get("end"))
    meeting_id = preview_note_from_event(event)["meeting_id"]
    return _write_note(
        title=title,
        start_iso=start_iso,
        end_iso=end_iso,
        calendar_name=str(event.get("calendar_name", "")),
        platform=str(event.get("platform", "unknown")),
        join_url=str(event.get("join_url", "")),
        recording_wav_rel=str(event.get("recording_wav_rel", "")),
        start_human=str(event.get("start_human", "")),
        end_human=str(event.get("end_human", "")),
        meeting_id=meeting_id,
    )


def create_adhoc_note(
    *,
    title: str,
    platform: str,
    meeting_id: str | None = None,
    start: datetime | None = None,
) -> dict[str, str]:
    start = start or datetime.now(UTC)
    end = start + timedelta(minutes=30)
    start_iso = start.isoformat()
    event = {
        "title": title,
        "start": start_iso,
        "end": end.isoformat(),
        "calendar_name": "Ad Hoc",
        "platform": platform,
        "join_url": "",
        "recording_wav_rel": "",
        "start_human": start.strftime("%Y-%m-%d %H:%M"),
        "end_human": end.strftime("%Y-%m-%d %H:%M"),
    }
    resolved_meeting_id = meeting_id or generate_meeting_id(title=title, start_iso=start_iso)
    return _write_note(
        title=title,
        start_iso=start_iso,
        end_iso=str(event["end"]),
        calendar_name=str(event["calendar_name"]),
        platform=str(event["platform"]),
        join_url=str(event["join_url"]),
        recording_wav_rel=str(event["recording_wav_rel"]),
        start_human=str(event["start_human"]),
        end_human=str(event["end_human"]),
        meeting_id=resolved_meeting_id,
    )


def infer_datetime_from_recording_path(path: Path) -> tuple[datetime, str]:
    tz = _local_tz()
    match = re.search(r"(\d{8})[_-](\d{4})", path.stem)
    if match:
        stamp = f"{match.group(1)}{match.group(2)}"
        try:
            return datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=tz), "filename"
        except ValueError:
            pass
    stat = path.stat()
    birthtime = getattr(stat, "st_birthtime", None)
    if isinstance(birthtime, (float, int)) and birthtime > 0:
        return datetime.fromtimestamp(float(birthtime), tz=tz), "birthtime"
    return datetime.fromtimestamp(stat.st_mtime, tz=tz), "mtime"


def create_backfill_note_for_recording(
    *,
    recording_path: Path,
    platform: str = "system",
) -> dict[str, str]:
    inferred_start, _ = infer_datetime_from_recording_path(recording_path)
    readable_title = recording_path.stem.replace("_", " ").replace("-", " ").strip() or "Backfill Meeting"
    return create_adhoc_note(
        title=readable_title,
        platform=platform,
        start=inferred_start,
    )
