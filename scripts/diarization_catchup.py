#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _collapse_recording_variants(paths: list[Path]) -> list[Path]:
    families: dict[str, list[Path]] = {}
    for path in paths:
        ext = path.suffix.lower()
        if ext not in {".wav", ".m4a"}:
            continue
        key = str(path.with_suffix("").resolve())
        families.setdefault(key, []).append(path.resolve())

    def _score(path: Path) -> tuple[int, str]:
        ext = path.suffix.lower()
        if ext == ".wav":
            return (0, str(path))
        if ext == ".m4a":
            return (1, str(path))
        return (2, str(path))

    selected = [sorted(candidates, key=_score)[0] for candidates in families.values()]
    selected.sort(key=lambda path: path.stat().st_mtime)
    return selected


def _find_meeting_id_from_done_marker(audio_path: Path) -> str:
    marker = audio_path.with_name(f"{audio_path.name}.done.json")
    if not marker.exists():
        return ""
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return ""
    meeting_id = str(payload.get("meeting_id", "")).strip()
    return meeting_id


def _build_note_audio_index(vault_path: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    meeting_id_pattern = re.compile(r'^meeting_id:\s*"?([^"\n]+)"?\s*$')
    audio_line_pattern = re.compile(r"^-\s+audio:\s+(.+)$")
    for note in vault_path.rglob("*.md"):
        if ".obsidian" in note.parts or "_artifacts" in note.parts:
            continue
        meeting_id = ""
        audio_path = ""
        try:
            for line in note.read_text(encoding="utf-8", errors="replace").splitlines()[:250]:
                if not meeting_id:
                    match = meeting_id_pattern.match(line.strip())
                    if match:
                        meeting_id = match.group(1).strip()
                audio_match = audio_line_pattern.match(line.strip())
                if audio_match:
                    audio_path = audio_match.group(1).strip()
                if meeting_id and audio_path:
                    break
        except OSError:
            continue
        if not meeting_id or not audio_path or audio_path.startswith("[["):
            continue
        resolved = Path(audio_path).expanduser()
        if not resolved.is_absolute():
            continue
        index[str(resolved.resolve())] = meeting_id
    return index


def _extract_manifest_from_output(text: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "transcript_txt" in payload:
            return payload
    return None


def _artifact_dir_for_meeting(vault_path: Path, meeting_id: str) -> Path:
    root = os.environ.get("MEETINGCTL_ARTIFACTS_ROOT", "Meetings/_artifacts").strip() or "Meetings/_artifacts"
    return (vault_path / root / meeting_id).resolve()


def _resolve_existing_transcript_json(vault_path: Path, meeting_id: str) -> Path | None:
    if not meeting_id:
        return None
    artifact_dir = _artifact_dir_for_meeting(vault_path, meeting_id)
    candidates = [
        artifact_dir / f"{meeting_id}.json",
        artifact_dir / f"{meeting_id}.basic.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def _resolve_files(recordings_root: Path, extensions: list[str], file_list: str) -> list[Path]:
    if file_list.strip():
        manifest_path = Path(file_list).expanduser().resolve()
        if not manifest_path.exists():
            raise ValueError(f"File list does not exist: {manifest_path}")
        files: list[Path] = []
        for raw in manifest_path.read_text(encoding="utf-8").splitlines():
            candidate = raw.strip()
            if not candidate or candidate.startswith("#"):
                continue
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = (manifest_path.parent / path).resolve()
            else:
                path = path.resolve()
            if path.suffix.lower().lstrip(".") not in extensions:
                continue
            if path.exists():
                files.append(path)
        return _collapse_recording_variants(files)

    files = [path.resolve() for ext in extensions for path in recordings_root.glob(f"*.{ext}")]
    return _collapse_recording_variants(files)


def run(args: argparse.Namespace) -> dict[str, Any]:
    recordings_root = Path(args.recordings_root).expanduser().resolve()
    vault_path = Path(args.vault_path).expanduser().resolve()
    recordings_root.mkdir(parents=True, exist_ok=True)

    extensions = [value.strip().lower().lstrip(".") for value in args.extensions.split(",") if value.strip()]
    if not extensions:
        extensions = ["wav", "m4a"]

    files = _resolve_files(recordings_root, extensions, args.file_list)
    if args.max_files > 0:
        files = files[: args.max_files]

    note_audio_index = _build_note_audio_index(vault_path)
    results: list[dict[str, Any]] = []
    failed = 0
    skipped = 0
    copied = 0
    replaced = 0

    for audio_path in files:
        meeting_id = _find_meeting_id_from_done_marker(audio_path)
        if not meeting_id:
            meeting_id = note_audio_index.get(str(audio_path.resolve()), "")

        cmd = ["bash", str((ROOT / "scripts" / "diarize_sidecar.sh").resolve()), str(audio_path)]
        if meeting_id:
            cmd.extend(["--meeting-id", meeting_id])
        transcript_json = None
        if args.prefer_existing_transcript_json:
            transcript_json = _resolve_existing_transcript_json(vault_path, meeting_id)
            if transcript_json is not None:
                cmd.extend(["--transcript-json", str(transcript_json)])
        if args.require_existing_transcript_json and transcript_json is None:
            item: dict[str, Any] = {
                "audio_path": str(audio_path),
                "meeting_id": meeting_id,
                "command": cmd,
                "ok": False,
                "skipped": True,
                "copied_to_artifacts": False,
                "replaced_active": False,
                "error": "missing existing transcript JSON",
            }
            skipped += 1
            results.append(item)
            continue
        if args.require_pyannote:
            cmd.append("--require-pyannote")
        if args.allow_transcript_without_diarization:
            cmd.append("--allow-transcript-without-diarization")

        item: dict[str, Any] = {
            "audio_path": str(audio_path),
            "meeting_id": meeting_id,
            "transcript_json_used": str(transcript_json) if transcript_json is not None else "",
            "command": cmd,
            "ok": False,
            "skipped": False,
            "copied_to_artifacts": False,
            "replaced_active": False,
            "error": "",
        }

        if args.dry_run:
            item["ok"] = True
            results.append(item)
            continue

        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
        merged_output = "\n".join(
            part for part in [completed.stdout.strip(), completed.stderr.strip()] if part
        )
        manifest = _extract_manifest_from_output(merged_output)

        if completed.returncode != 0 or manifest is None:
            failed += 1
            item["error"] = merged_output.splitlines()[-1] if merged_output else "sidecar run failed"
            results.append(item)
            continue

        item["ok"] = True
        item["manifest"] = manifest
        transcript_txt = Path(str(manifest.get("transcript_txt", ""))).expanduser().resolve()
        transcript_srt = Path(str(manifest.get("transcript_srt", ""))).expanduser().resolve()
        transcript_json = Path(str(manifest.get("transcript_json", ""))).expanduser().resolve()

        if args.apply_to_artifacts and meeting_id:
            artifact_dir = _artifact_dir_for_meeting(vault_path, meeting_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)

            copied_txt = _copy_if_exists(transcript_txt, artifact_dir / f"{meeting_id}.diarized.txt")
            copied_srt = _copy_if_exists(transcript_srt, artifact_dir / f"{meeting_id}.diarized.srt")
            copied_json = _copy_if_exists(transcript_json, artifact_dir / f"{meeting_id}.diarized.json")
            if copied_txt or copied_srt or copied_json:
                item["copied_to_artifacts"] = True
                copied += 1

            if args.replace_active and copied_txt:
                canonical_txt = artifact_dir / f"{meeting_id}.txt"
                canonical_srt = artifact_dir / f"{meeting_id}.srt"
                canonical_json = artifact_dir / f"{meeting_id}.json"
                basic_txt = artifact_dir / f"{meeting_id}.basic.txt"
                basic_srt = artifact_dir / f"{meeting_id}.basic.srt"
                basic_json = artifact_dir / f"{meeting_id}.basic.json"

                if canonical_txt.exists() and not basic_txt.exists():
                    _copy_if_exists(canonical_txt, basic_txt)
                if canonical_srt.exists() and not basic_srt.exists():
                    _copy_if_exists(canonical_srt, basic_srt)
                if canonical_json.exists() and not basic_json.exists():
                    _copy_if_exists(canonical_json, basic_json)

                _copy_if_exists(artifact_dir / f"{meeting_id}.diarized.txt", canonical_txt)
                _copy_if_exists(artifact_dir / f"{meeting_id}.diarized.srt", canonical_srt)
                _copy_if_exists(artifact_dir / f"{meeting_id}.diarized.json", canonical_json)
                item["replaced_active"] = True
                replaced += 1

        results.append(item)

    manifests_dir = (ROOT / "shared_data" / "diarization" / "manifests").resolve()
    manifests_dir.mkdir(parents=True, exist_ok=True)
    report_path = manifests_dir / f"catchup_{_now_stamp()}.json"
    payload = {
        "recordings_root": str(recordings_root),
        "vault_path": str(vault_path),
        "discovered_files": len(files),
        "processed": len(results),
        "failed": failed,
        "skipped": skipped,
        "copied_to_artifacts": copied,
        "replaced_active": replaced,
        "apply_to_artifacts": args.apply_to_artifacts,
        "replace_active": args.replace_active,
        "prefer_existing_transcript_json": args.prefer_existing_transcript_json,
        "require_existing_transcript_json": args.require_existing_transcript_json,
        "require_pyannote": args.require_pyannote,
        "dry_run": args.dry_run,
        "report_path": str(report_path),
        "results": results,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run sidecar diarization over historical recordings")
    parser.add_argument("--recordings-root", default=os.environ.get("RECORDINGS_PATH", "~/Notes/audio"))
    parser.add_argument("--vault-path", default=os.environ.get("VAULT_PATH", "~/Notes/notes-vault"))
    parser.add_argument("--extensions", default="wav,m4a")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--file-list", default="")
    parser.add_argument("--apply-to-artifacts", action="store_true", default=True)
    parser.add_argument("--no-apply-to-artifacts", action="store_false", dest="apply_to_artifacts")
    parser.add_argument("--replace-active", action="store_true")
    parser.add_argument("--prefer-existing-transcript-json", action="store_true", default=True)
    parser.add_argument("--no-prefer-existing-transcript-json", action="store_false", dest="prefer_existing_transcript_json")
    parser.add_argument("--require-existing-transcript-json", action="store_true")
    parser.add_argument("--require-pyannote", action="store_true")
    parser.add_argument("--allow-transcript-without-diarization", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = run(args)
    except Exception as exc:
        error = {"error": str(exc)}
        print(json.dumps(error))
        return 2

    if args.json:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
