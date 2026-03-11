#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _artifacts_root(vault_path: Path) -> Path:
    root = os.environ.get("MEETINGCTL_ARTIFACTS_ROOT", "Meetings/_artifacts").strip() or "Meetings/_artifacts"
    return (vault_path / root).resolve()


def _meeting_id_from_note(note_path: Path) -> str:
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
        return ""
    return ""


def _note_meeting_ids(vault_path: Path) -> set[str]:
    found: set[str] = set()
    for note_path in vault_path.rglob("*.md"):
        if "_artifacts" in note_path.parts or ".obsidian" in note_path.parts:
            continue
        meeting_id = _meeting_id_from_note(note_path)
        if meeting_id:
            found.add(meeting_id)
    return found


def run(args: argparse.Namespace) -> dict[str, Any]:
    vault_path = Path(args.vault_path).expanduser().resolve()
    artifacts_root = _artifacts_root(vault_path)
    note_meeting_ids = _note_meeting_ids(vault_path)

    orphan_dirs: list[str] = []
    deleted_dirs: list[str] = []
    if artifacts_root.exists():
        for path in sorted(artifacts_root.iterdir()):
            if not path.is_dir():
                continue
            meeting_id = path.name.strip()
            if not meeting_id.startswith("m-"):
                continue
            if meeting_id in note_meeting_ids:
                continue
            orphan_dirs.append(str(path.resolve()))
            if args.apply:
                shutil.rmtree(path)
                deleted_dirs.append(str(path.resolve()))

    manifests_dir = (ROOT / "shared_data" / "diarization" / "manifests").resolve()
    manifests_dir.mkdir(parents=True, exist_ok=True)
    report_path = manifests_dir / f"prune_orphan_artifacts_{_now_stamp()}.json"
    payload = {
        "vault_path": str(vault_path),
        "artifacts_root": str(artifacts_root),
        "note_meeting_ids": len(note_meeting_ids),
        "discovered_orphan_dirs": len(orphan_dirs),
        "deleted_dirs": len(deleted_dirs),
        "apply": args.apply,
        "report_path": str(report_path),
        "orphans": orphan_dirs,
        "deleted": deleted_dirs,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Delete artifact folders whose meeting notes no longer exist anywhere in the vault")
    parser.add_argument("--vault-path", default=os.environ.get("VAULT_PATH", "~/Notes/notes-vault"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    payload = run(args)
    if args.json:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
