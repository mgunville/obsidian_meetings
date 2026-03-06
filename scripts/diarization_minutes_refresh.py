#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _find_note_for_meeting_id(vault_path: Path, meeting_id: str) -> Path | None:
    pattern = re.compile(rf"\s-\s*{re.escape(meeting_id)}(?:\s+\(\d+\))?\.md$", re.IGNORECASE)
    candidates: list[Path] = []
    for path in vault_path.rglob("*.md"):
        if "_artifacts" in path.parts or ".obsidian" in path.parts:
            continue
        if pattern.search(path.name):
            candidates.append(path.resolve())
    if not candidates:
        return None
    return sorted(candidates)[0]


def _resolve_meeting_ids(vault_path: Path, meeting_ids: list[str], max_items: int) -> list[str]:
    if meeting_ids:
        resolved = []
        seen: set[str] = set()
        for value in meeting_ids:
            candidate = value.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            resolved.append(candidate)
        return resolved

    artifacts_root = os.environ.get("MEETINGCTL_ARTIFACTS_ROOT", "Meetings/_artifacts").strip() or "Meetings/_artifacts"
    base = (vault_path / artifacts_root).resolve()
    if not base.exists():
        return []
    found: list[str] = []
    for diarized_file in sorted(base.rglob("m-*.diarized.txt")):
        meeting_id = diarized_file.name.replace(".diarized.txt", "")
        found.append(meeting_id)
        if max_items > 0 and len(found) >= max_items:
            break
    return found


def run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from meetingctl.note.patcher import patch_note_file
        from meetingctl.summary_client import generate_summary
        from meetingctl.summary_parser import summary_to_patch_regions
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing runtime dependencies. Run with the project venv, e.g. `./.venv/bin/python scripts/diarization_minutes_refresh.py ...`"
        ) from exc

    vault_path = Path(args.vault_path).expanduser().resolve()
    artifacts_root = os.environ.get("MEETINGCTL_ARTIFACTS_ROOT", "Meetings/_artifacts").strip() or "Meetings/_artifacts"
    artifacts_base = (vault_path / artifacts_root).resolve()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    meeting_ids = _resolve_meeting_ids(vault_path, args.meeting_id, args.max_items)
    results: list[dict[str, Any]] = []
    compared = 0
    applied = 0
    failed = 0

    markdown_lines = [
        f"# Diarization Minutes Compare Report ({_now_stamp()})",
        "",
        f"- Vault: `{vault_path}`",
        f"- Artifacts root: `{artifacts_base}`",
        f"- Apply diarized: `{args.apply_diarized}`",
        "",
    ]

    for meeting_id in meeting_ids:
        artifact_dir = artifacts_base / meeting_id
        baseline_path = artifact_dir / f"{meeting_id}.txt"
        diarized_path = artifact_dir / f"{meeting_id}.diarized.txt"
        note_path = _find_note_for_meeting_id(vault_path, meeting_id)

        item: dict[str, Any] = {
            "meeting_id": meeting_id,
            "artifact_dir": str(artifact_dir),
            "note_path": str(note_path) if note_path else "",
            "ok": False,
            "applied": False,
            "error": "",
        }

        if not diarized_path.exists() or not baseline_path.exists() or note_path is None:
            item["error"] = "missing baseline/diarized transcript or note"
            failed += 1
            results.append(item)
            continue

        try:
            baseline_summary = generate_summary(baseline_path.read_text(encoding="utf-8", errors="replace"), api_key=api_key)
            diarized_summary = generate_summary(diarized_path.read_text(encoding="utf-8", errors="replace"), api_key=api_key)
        except Exception as exc:
            item["error"] = str(exc)
            failed += 1
            results.append(item)
            continue

        compared += 1
        item["ok"] = True
        item["baseline_decisions"] = len(baseline_summary.get("decisions", []))
        item["diarized_decisions"] = len(diarized_summary.get("decisions", []))
        item["baseline_action_items"] = len(baseline_summary.get("action_items", []))
        item["diarized_action_items"] = len(diarized_summary.get("action_items", []))

        markdown_lines.append(f"## {meeting_id}")
        markdown_lines.append("")
        markdown_lines.append(f"- Note: `{note_path}`")
        markdown_lines.append(f"- Baseline transcript: `{baseline_path}`")
        markdown_lines.append(f"- Diarized transcript: `{diarized_path}`")
        markdown_lines.append(
            f"- Decisions: baseline={len(baseline_summary.get('decisions', []))}, diarized={len(diarized_summary.get('decisions', []))}"
        )
        markdown_lines.append(
            f"- Action items: baseline={len(baseline_summary.get('action_items', []))}, diarized={len(diarized_summary.get('action_items', []))}"
        )
        markdown_lines.append("")
        markdown_lines.append("### Baseline Minutes")
        markdown_lines.append("")
        markdown_lines.append(str(baseline_summary.get("minutes", "")).strip())
        markdown_lines.append("")
        markdown_lines.append("### Diarized Minutes")
        markdown_lines.append("")
        markdown_lines.append(str(diarized_summary.get("minutes", "")).strip())
        markdown_lines.append("")

        if args.apply_diarized:
            try:
                patch_note_file(
                    note_path=note_path,
                    updates=summary_to_patch_regions(diarized_summary),
                    dry_run=False,
                )
                item["applied"] = True
                applied += 1
            except Exception as exc:
                item["error"] = f"apply failed: {exc}"

        results.append(item)

    manifests_dir = (ROOT / "shared_data" / "diarization" / "manifests").resolve()
    manifests_dir.mkdir(parents=True, exist_ok=True)
    json_report = manifests_dir / f"minutes_compare_{_now_stamp()}.json"
    md_report = manifests_dir / f"minutes_compare_{_now_stamp()}.md"

    payload = {
        "vault_path": str(vault_path),
        "artifacts_root": str(artifacts_base),
        "meeting_ids": meeting_ids,
        "compared": compared,
        "applied": applied,
        "failed": failed,
        "apply_diarized": args.apply_diarized,
        "json_report": str(json_report),
        "markdown_report": str(md_report),
        "results": results,
    }
    json_report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_report.write_text("\n".join(markdown_lines).strip() + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare baseline vs diarized transcript summaries and optionally apply")
    parser.add_argument("--vault-path", default=os.environ.get("VAULT_PATH", "~/Notes/notes-vault"))
    parser.add_argument("--meeting-id", action="append", default=[])
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--apply-diarized", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = run(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    if args.json:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
