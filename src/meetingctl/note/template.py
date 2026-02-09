from __future__ import annotations

from pathlib import Path


DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "templates" / "meeting.md"


def _render_placeholders(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
    return rendered


def render_meeting_note(values: dict[str, str], template_path: Path | None = None) -> str:
    template_file = template_path or DEFAULT_TEMPLATE_PATH
    template = template_file.read_text()
    return _render_placeholders(template, values)
