from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from meetingctl.note.identity import (
    build_note_filename,
    ensure_collision_safe_path,
    generate_meeting_id,
)
from meetingctl.note.template import render_meeting_note


def create_note_from_event(event: dict[str, object]) -> dict[str, str]:
    vault_path = Path(os.environ.get("VAULT_PATH", ".")).expanduser().resolve()
    meetings_folder = Path(os.environ.get("DEFAULT_MEETINGS_FOLDER", "meetings"))
    note_dir = (vault_path / meetings_folder).resolve()
    note_dir.mkdir(parents=True, exist_ok=True)

    title = str(event.get("title", "Untitled Meeting"))
    start_iso = str(event.get("start"))
    end_iso = str(event.get("end"))
    meeting_id = generate_meeting_id(title=title, start_iso=start_iso)
    start_dt = datetime.fromisoformat(start_iso).replace(tzinfo=None)
    filename = build_note_filename(start_dt=start_dt, title=title, meeting_id=meeting_id)
    note_path = ensure_collision_safe_path(note_dir / filename)

    rendered = render_meeting_note(
        {
            "meeting_id": meeting_id,
            "title": title,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "calendar_name": str(event.get("calendar_name", "")),
            "platform": str(event.get("platform", "unknown")),
            "join_url": str(event.get("join_url", "")),
            "recording_wav_rel": str(event.get("recording_wav_rel", "")),
            "start_human": str(event.get("start_human", "")),
            "end_human": str(event.get("end_human", "")),
        }
    )
    note_path.write_text(rendered)
    return {"meeting_id": meeting_id, "note_path": str(note_path)}
