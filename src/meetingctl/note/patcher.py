from __future__ import annotations

from pathlib import Path


class PatchingError(ValueError):
    pass


REGIONS = {
    "minutes": ("<!-- MINUTES_START -->", "<!-- MINUTES_END -->"),
    "decisions": ("<!-- DECISIONS_START -->", "<!-- DECISIONS_END -->"),
    "action_items": ("<!-- ACTION_ITEMS_START -->", "<!-- ACTION_ITEMS_END -->"),
    "transcript": ("<!-- TRANSCRIPT_START -->", "<!-- TRANSCRIPT_END -->"),
}


def _replace_region(note_text: str, start_marker: str, end_marker: str, content: str) -> str:
    start_idx = note_text.find(start_marker)
    if start_idx == -1:
        raise PatchingError(f"Missing marker: {start_marker}")
    end_idx = note_text.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1:
        raise PatchingError(f"Missing marker: {end_marker}")

    inner_start = start_idx + len(start_marker)
    if inner_start < len(note_text) and note_text[inner_start] == "\n":
        inner_start += 1
    inner_end = end_idx
    if inner_end > 0 and note_text[inner_end - 1] == "\n":
        inner_end -= 1

    replacement = content.rstrip("\n")
    return note_text[:inner_start] + replacement + "\n" + note_text[inner_end:]


def apply_managed_patch(note_text: str, updates: dict[str, str]) -> tuple[str, list[str]]:
    patched = note_text
    changed_regions: list[str] = []
    for region, new_content in updates.items():
        if region not in REGIONS:
            continue
        start_marker, end_marker = REGIONS[region]
        updated = _replace_region(patched, start_marker, end_marker, new_content)
        if updated != patched:
            changed_regions.append(region)
            patched = updated
    return patched, changed_regions


def patch_note_file(*, note_path: Path, updates: dict[str, str], dry_run: bool) -> dict[str, object]:
    original = note_path.read_text()
    patched, changed_regions = apply_managed_patch(original, updates)
    changed = patched != original
    wrote = False
    if changed and not dry_run:
        note_path.write_text(patched)
        wrote = True
    return {
        "note_path": str(note_path),
        "changed": changed,
        "dry_run": dry_run,
        "write_performed": wrote,
        "changed_regions": changed_regions,
    }
