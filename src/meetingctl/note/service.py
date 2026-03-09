from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from meetingctl.local_time import local_timezone
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
    return local_timezone()


def _recording_filename_tz():
    tz_name = os.environ.get("MEETINGCTL_RECORDING_FILENAME_TIMEZONE", "").strip()
    if not tz_name:
        return _local_tz()
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return _local_tz()


def _voicememo_filename_tz():
    tz_name = os.environ.get("MEETINGCTL_VOICEMEMO_FILENAME_TIMEZONE", "").strip()
    if not tz_name:
        return _local_tz()
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return _local_tz()


def _load_incident_voice_memo_entries() -> set[str]:
    manifest = os.environ.get("MEETINGCTL_VOICEMEMO_UTC_MANIFEST", "").strip()
    if not manifest:
        return set()
    manifest_path = Path(manifest).expanduser()
    if not manifest_path.exists():
        return set()
    entries: set[str] = set()
    for line in manifest_path.read_text().splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        entries.add(value)
        entries.add(Path(value).name)
        entries.add(str(Path(value).expanduser().resolve()))
    return entries


def _is_incident_voice_memo(path: Path) -> bool:
    entries = _load_incident_voice_memo_entries()
    if not entries:
        return False
    resolved = str(path.expanduser().resolve())
    return resolved in entries or path.name in entries


def _existing_note_for_meeting_id(meeting_id: str) -> Path | None:
    note_dir = _note_directory()
    pattern = re.compile(rf" - {re.escape(meeting_id)}(?: \(\d+\))?\.md$")
    matches = sorted(
        p for p in note_dir.glob(f"*{meeting_id}*.md") if pattern.search(p.name)
    )
    return matches[0] if matches else None


def _vault_path() -> Path:
    return Path(os.environ.get("VAULT_PATH", ".")).expanduser().resolve()


def _default_meetings_folder_parts() -> tuple[str, ...]:
    folder = Path(os.environ.get("DEFAULT_MEETINGS_FOLDER", "meetings"))
    return tuple(part.lower() for part in folder.parts if part)


def _is_under_default_meetings_folder(note_path: Path) -> bool:
    default_parts = _default_meetings_folder_parts()
    if not default_parts:
        return False
    try:
        rel_parts = tuple(part.lower() for part in note_path.resolve().relative_to(_vault_path()).parts)
    except Exception:
        return False
    return rel_parts[: len(default_parts)] == default_parts


def _event_local_start_key(start_iso: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(start_iso)
    if dt.tzinfo is not None:
        dt = dt.astimezone(_local_tz())
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H%M")


def _meeting_id_from_note_path(note_path: Path) -> str | None:
    filename_match = re.search(r"\s-\s*(m-[a-f0-9]{10})(?:\s+\(\d+\))?\.md$", note_path.name, re.IGNORECASE)
    if filename_match:
        return filename_match.group(1)
    try:
        for line in note_path.read_text(encoding="utf-8", errors="replace").splitlines()[:80]:
            frontmatter_match = re.match(r'^meeting_id:\s*"?([^"\n]+)"?\s*$', line.strip())
            if not frontmatter_match:
                continue
            candidate = frontmatter_match.group(1).strip()
            if candidate.startswith("m-"):
                return candidate
    except OSError:
        return None
    return None


def _note_start_key(note_path: Path) -> tuple[str, str] | None:
    filename_match = re.match(r"^(\d{4}-\d{2}-\d{2})[ _-](\d{4})\b", note_path.name)
    if filename_match:
        return filename_match.group(1), filename_match.group(2)

    try:
        lines = note_path.read_text(encoding="utf-8", errors="replace").splitlines()[:120]
    except OSError:
        return None

    for line in lines:
        start_match = re.match(r'^start:\s*"?([^"\n]+)"?\s*$', line.strip())
        if not start_match:
            continue
        raw_start = start_match.group(1).strip()
        try:
            return _event_local_start_key(raw_start)
        except ValueError:
            return None
    return None


def _has_managed_meeting_regions(note_path: Path) -> bool:
    try:
        text = note_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    required_markers = (
        "<!-- MINUTES_START -->",
        "<!-- MINUTES_END -->",
        "<!-- DECISIONS_START -->",
        "<!-- DECISIONS_END -->",
        "<!-- ACTION_ITEMS_START -->",
        "<!-- ACTION_ITEMS_END -->",
        "<!-- REFERENCES_START -->",
        "<!-- REFERENCES_END -->",
    )
    return all(marker in text for marker in required_markers)


def resolve_existing_note_for_event_start(event: dict[str, object]) -> dict[str, object] | None:
    start_iso = str(event.get("start", "")).strip()
    title = str(event.get("title", "Untitled Meeting"))
    if not start_iso:
        return None
    try:
        target_key = _event_local_start_key(start_iso)
    except ValueError:
        return None

    candidates: list[Path] = []
    vault_root = _vault_path()
    for candidate in vault_root.rglob("*.md"):
        parts_lower = {part.lower() for part in candidate.parts}
        if ".obsidian" in parts_lower or "_artifacts" in parts_lower:
            continue
        if _note_start_key(candidate) != target_key:
            continue
        if not _has_managed_meeting_regions(candidate):
            continue
        candidates.append(candidate.resolve())

    if not candidates:
        return None

    def _sort_key(path: Path) -> tuple[int, str]:
        default_folder_rank = 1 if _is_under_default_meetings_folder(path) else 0
        try:
            rel = path.relative_to(vault_root).as_posix()
        except ValueError:
            rel = str(path)
        return (default_folder_rank, rel.lower())

    selected = sorted(candidates, key=_sort_key)[0]
    meeting_id = _meeting_id_from_note_path(selected) or generate_meeting_id(
        title=title,
        start_iso=start_iso,
    )
    return {
        "meeting_id": meeting_id,
        "note_path": str(selected),
        "candidate_count": len(candidates),
        "tie_break_rule": "prefer_non_default_meetings_folder_then_path",
    }


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
    existing_note = _existing_note_for_meeting_id(meeting_id)
    if existing_note:
        return {"meeting_id": meeting_id, "note_path": str(existing_note)}
    start_dt = _to_local_naive(start_iso)
    filename = build_note_filename(start_dt=start_dt, title=title, meeting_id=meeting_id)
    note_path = ensure_collision_safe_path(note_dir / filename)
    rendered = render_meeting_note(
        {
            "firm_default": os.environ.get("MEETINGCTL_DEFAULT_FIRM", "AHEAD").strip() or "AHEAD",
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
    existing_note = _existing_note_for_meeting_id(resolved_meeting_id)
    if existing_note:
        return {"meeting_id": resolved_meeting_id, "note_path": str(existing_note)}
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
    filename_tz = _recording_filename_tz()
    voice_memo_match = re.search(r"(\d{8})\s+(\d{6})", path.stem)
    if voice_memo_match:
        stamp = f"{voice_memo_match.group(1)}{voice_memo_match.group(2)}"
        try:
            voice_memo_tz = UTC if _is_incident_voice_memo(path) else _voicememo_filename_tz()
            return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(
                tzinfo=voice_memo_tz
            ), "filename_voice_memo"
        except ValueError:
            pass
    match = re.search(r"(\d{8})[_-](\d{4})", path.stem)
    if match:
        stamp = f"{match.group(1)}{match.group(2)}"
        try:
            return datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=filename_tz), "filename"
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
    title: str | None = None,
) -> dict[str, str]:
    inferred_start, _ = infer_datetime_from_recording_path(recording_path)
    readable_title = (
        title
        or recording_path.stem.replace("_", " ").replace("-", " ").strip()
        or "Backfill Meeting"
    )
    return create_adhoc_note(
        title=readable_title,
        platform=platform,
        start=inferred_start,
    )
