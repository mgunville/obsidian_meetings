from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass(frozen=True)
class NormalizeResult:
    examined: int
    changed: int
    skipped: int


def _clean_name(value: str) -> str:
    return value.lstrip("_").strip()


def _infer_work_context(rel_path: Path) -> dict[str, str | None]:
    parts = rel_path.parts
    if len(parts) < 2 or parts[0] != "_Work":
        return {"firm": None, "client": None, "engagement": None}

    firm = _clean_name(parts[1])
    client: str | None = None
    engagement: str | None = None

    if len(parts) >= 4 and parts[2] == "Clients":
        if parts[3] == "_Leads":
            engagement = "Lead"
            if len(parts) >= 5:
                client = _clean_name(parts[4])
        else:
            engagement = "Client"
            client = _clean_name(parts[3])

    return {"firm": firm, "client": client, "engagement": engagement}


def _looks_like_meeting(rel_path: Path, frontmatter: str) -> bool:
    if re.search(r"(?m)^meeting_id:\s*", frontmatter):
        return True
    if rel_path.parts and rel_path.parts[0].lower() == "meetings":
        return True
    if re.search(r"\s-\s*m-[a-f0-9]{8,}(?:\s+\(\d+\))?\.md$", rel_path.name, re.I):
        return True
    return False


def _title_from_filename(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"\s+\(\d+\)$", "", stem)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}(?:\s+\d{4})?\s+-\s+", "", stem)
    stem = re.sub(r"\s+-\s+m-[a-f0-9]{8,}(?:\s+\([^)]*\))?\s*$", "", stem, flags=re.I)
    return stem.strip()


def _parse_frontmatter_block(text: str) -> tuple[str | None, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    return match.group(1), text[match.end() :]


def _get_value(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", frontmatter)
    if not match:
        return None
    return match.group(1).strip()


def _set_value(frontmatter: str, key: str, value: str) -> str:
    line = f"{key}: {value}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    if pattern.search(frontmatter):
        return pattern.sub(line, frontmatter, count=1)

    lines = frontmatter.splitlines()
    insert_at = 1 if lines and lines[0].startswith("type:") else 0
    lines.insert(insert_at, line)
    return "\n".join(lines)


def _ensure_default_fields(frontmatter: str) -> str:
    defaults: list[tuple[str, str]] = [
        ("note_type", '""'),
        ("client", '""'),
        ("firm", '""'),
        ("engagement", '""'),
        ("topic", "[]"),
        ("opportunity_id", '""'),
        ("project_id", '""'),
        ("team", "[]"),
        ("related_notes", "[]"),
    ]
    out = frontmatter
    for key, value in defaults:
        if _get_value(out, key) is None:
            out = _set_value(out, key, value)
    return out


def normalize_frontmatter(
    *,
    vault_path: Path,
    note_paths: list[Path],
    sync_title_from_filename: bool = True,
) -> NormalizeResult:
    changed = 0
    examined = 0
    skipped = 0

    for note_path in note_paths:
        resolved = note_path.expanduser().resolve()
        try:
            rel = resolved.relative_to(vault_path)
        except ValueError:
            skipped += 1
            continue
        if "_artifacts" in rel.parts or resolved.suffix.lower() != ".md":
            skipped += 1
            continue

        original = resolved.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = _parse_frontmatter_block(original)
        if frontmatter is None:
            skipped += 1
            continue
        examined += 1

        out = _ensure_default_fields(frontmatter)
        meeting = _looks_like_meeting(rel, out)

        inferred = _infer_work_context(rel)
        if inferred["firm"] is not None:
            out = _set_value(out, "firm", f'"{inferred["firm"]}"')
        if inferred["client"] is not None:
            out = _set_value(out, "client", f'"{inferred["client"]}"')
        if inferred["engagement"] is not None:
            out = _set_value(out, "engagement", f'"{inferred["engagement"]}"')

        if meeting:
            out = _set_value(out, "note_type", '"meeting"')

        if sync_title_from_filename and meeting:
            title = _title_from_filename(resolved)
            if title:
                escaped = title.replace('"', '\\"')
                out = _set_value(out, "title", f'"{escaped}"')

        if out != frontmatter:
            resolved.write_text(f"---\n{out}\n---\n{body}", encoding="utf-8")
            changed += 1

    return NormalizeResult(examined=examined, changed=changed, skipped=skipped)

