#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _artifacts_root(vault_path: Path) -> Path:
    root = os.environ.get("MEETINGCTL_ARTIFACTS_ROOT", "Meetings/_artifacts").strip() or "Meetings/_artifacts"
    return (vault_path / root).resolve()


def _load_targets(report_path: Path, max_items: int) -> list[dict[str, str]]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    targets: list[dict[str, str]] = []
    for row in payload.get("results", []):
        if row.get("skipped"):
            continue
        targets.append(
            {
                "audio_path": str(row.get("audio_path", "")),
                "meeting_id": str(row.get("meeting_id", "")),
            }
        )
        if max_items > 0 and len(targets) >= max_items:
            break
    return targets


def _status_for_target(*, vault_path: Path, meeting_id: str) -> dict[str, Any]:
    artifact_dir = _artifacts_root(vault_path) / meeting_id
    diarized_txt = artifact_dir / f"{meeting_id}.diarized.txt"
    diarized_json = artifact_dir / f"{meeting_id}.diarized.json"
    diarized_srt = artifact_dir / f"{meeting_id}.diarized.srt"
    completed = diarized_txt.exists() or diarized_json.exists() or diarized_srt.exists()
    latest_mtime = 0.0
    for path in (diarized_txt, diarized_json, diarized_srt):
        if path.exists():
            latest_mtime = max(latest_mtime, path.stat().st_mtime)
    return {
        "status": "completed" if completed else "pending",
        "artifact_dir": str(artifact_dir),
        "latest_artifact_at": datetime.fromtimestamp(latest_mtime, UTC).isoformat() if latest_mtime else "",
    }


def _write_snapshot(*, snapshot_path: Path, payload: dict[str, Any]) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    report_path = Path(args.report_path).expanduser().resolve()
    if not report_path.exists():
        raise FileNotFoundError(f"Report path does not exist: {report_path}")
    vault_path = Path(args.vault_path).expanduser().resolve()
    output_path = Path(args.output_path).expanduser().resolve()
    targets = _load_targets(report_path, args.max_items)
    started_at = _now_iso()

    while True:
        completed = 0
        items: list[dict[str, Any]] = []
        for index, target in enumerate(targets, start=1):
            item = dict(target)
            item["index"] = index
            item.update(_status_for_target(vault_path=vault_path, meeting_id=target["meeting_id"]))
            if item["status"] == "completed":
                completed += 1
            items.append(item)

        pending_items = [item for item in items if item["status"] != "completed"]
        payload = {
            "started_at": started_at,
            "polled_at": _now_iso(),
            "report_path": str(report_path),
            "vault_path": str(vault_path),
            "max_items": args.max_items,
            "completed": completed,
            "total": len(items),
            "remaining": len(items) - completed,
            "percent_complete": round((completed / len(items)) * 100, 1) if items else 100.0,
            "next_pending": pending_items[0] if pending_items else {},
            "items": items,
        }
        _write_snapshot(snapshot_path=output_path, payload=payload)
        if completed >= len(items):
            break
        time.sleep(max(args.interval_seconds, 1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Poll diarization batch progress and write snapshots.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--vault-path", default=os.environ.get("VAULT_PATH", "~/Notes/notes-vault"))
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--output-path", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
