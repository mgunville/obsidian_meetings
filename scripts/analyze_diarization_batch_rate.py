#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Any


def _load_targets(report_path: Path, max_items: int) -> list[dict[str, Any]]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    targets: list[dict[str, Any]] = []
    for row in payload.get("results", []):
        if row.get("skipped"):
            continue
        targets.append(
            {
                "audio_path": str(row.get("audio_path", "")),
                "audio_name": Path(str(row.get("audio_path", ""))).name,
                "meeting_id": str(row.get("meeting_id", "")),
            }
        )
        if max_items > 0 and len(targets) >= max_items:
            break
    return targets


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _audio_duration_seconds(audio_path: Path) -> float | None:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return None


def _latest_manifests_by_audio(jobs_root: Path) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for manifest_path in jobs_root.rglob("manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        input_audio = str(payload.get("input_audio", "")).strip()
        created_at = str(payload.get("created_at", "")).strip()
        if not input_audio or not created_at:
            continue
        audio_name = Path(input_audio).name
        existing = manifests.get(audio_name)
        if existing is None or created_at > str(existing.get("created_at", "")):
            payload["manifest_path"] = str(manifest_path)
            manifests[audio_name] = payload
    return manifests


def run(args: argparse.Namespace) -> dict[str, Any]:
    report_path = Path(args.report_path).expanduser().resolve()
    jobs_root = Path(args.jobs_root).expanduser().resolve()
    targets = _load_targets(report_path, args.max_items)
    manifests = _latest_manifests_by_audio(jobs_root)

    items: list[dict[str, Any]] = []
    completed_items: list[dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        audio_path = Path(target["audio_path"]).expanduser().resolve()
        duration_seconds = _audio_duration_seconds(audio_path)
        manifest = manifests.get(target["audio_name"])
        created_at = _parse_iso(str(manifest.get("created_at", ""))) if manifest else None
        item = {
            "index": index,
            "meeting_id": target["meeting_id"],
            "audio_path": str(audio_path),
            "audio_duration_seconds": duration_seconds,
            "completed_at": created_at.isoformat() if created_at else "",
            "manifest_path": str(manifest.get("manifest_path", "")) if manifest else "",
            "status": "completed" if created_at else "pending",
        }
        items.append(item)
        if created_at:
            completed_items.append(item)

    previous_completed_at = None
    for item in items:
        completed_at = _parse_iso(str(item["completed_at"]))
        if completed_at is None:
            item["estimated_processing_seconds"] = None
            item["realtime_multiple"] = None
            item["slower_than_realtime_multiple"] = None
            continue
        if previous_completed_at is None:
            item["estimated_processing_seconds"] = None
            item["realtime_multiple"] = None
            item["slower_than_realtime_multiple"] = None
        else:
            elapsed_seconds = max((completed_at - previous_completed_at).total_seconds(), 0.0)
            item["estimated_processing_seconds"] = elapsed_seconds
            duration_seconds = item["audio_duration_seconds"]
            if duration_seconds and elapsed_seconds > 0:
                realtime_multiple = duration_seconds / elapsed_seconds
                item["realtime_multiple"] = round(realtime_multiple, 3)
                item["slower_than_realtime_multiple"] = round(elapsed_seconds / duration_seconds, 3)
            else:
                item["realtime_multiple"] = None
                item["slower_than_realtime_multiple"] = None
        previous_completed_at = completed_at

    completed_count = sum(1 for item in items if item["status"] == "completed")
    payload = {
        "report_path": str(report_path),
        "jobs_root": str(jobs_root),
        "polled_at": datetime.now().astimezone().isoformat(),
        "completed": completed_count,
        "total": len(items),
        "items": items,
    }
    if args.output_path:
        output_path = Path(args.output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Estimate diarization batch throughput from completion timestamps.")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--jobs-root", default="shared_data/diarization/jobs")
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--output-path", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
