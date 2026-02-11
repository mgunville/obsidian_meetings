from __future__ import annotations

import os
from pathlib import Path


DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "templates" / "meeting.md"


def _render_placeholders(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
    return rendered


def render_meeting_note(values: dict[str, str], template_path: Path | None = None) -> str:
    env_template = os.environ.get("MEETINGCTL_NOTE_TEMPLATE_PATH", "").strip()
    resolved_template: Path | None = template_path
    if resolved_template is None and env_template:
        env_path = Path(env_template).expanduser().resolve()
        if env_path.exists():
            resolved_template = env_path
    template_file = resolved_template or DEFAULT_TEMPLATE_PATH
    template = template_file.read_text()
    return _render_placeholders(template, values)
