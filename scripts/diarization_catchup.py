#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from meetingctl.note.service import create_backfill_note_for_recording

ROOT = Path(__file__).resolve().parents[1]
_AUDIO_TIMESTAMP_PATTERNS = (
    re.compile(r"(?P<stamp>\d{8}-\d{4})"),
    re.compile(r"Recording\s+(?P<stamp>\d{14})"),
)
_NOTE_TIME_FALLBACK_TOLERANCE_SECONDS = 30 * 60
_SYSTEMIC_ERROR_RULES = (
    {
        "code": "onepassword_auth_timeout",
        "patterns": (
            "secure_exec: timed out waiting for 1Password auth",
            "secure_exec: 1Password CLI is not signed in",
        ),
        "summary": "1Password authentication is blocking Hugging Face token resolution for diarization.",
        "action": (
            "Run `op whoami`/`op signin`, or configure `MEETINGCTL_HF_TOKEN_FILE` "
            "with a local token so the batch can run headless."
        ),
        "stop_run": True,
        "systemic": True,
    },
    {
        "code": "docker_unavailable",
        "patterns": ("docker is required", "Cannot connect to the Docker daemon"),
        "summary": "Docker is unavailable, so the diarization sidecar cannot run.",
        "action": "Start Docker Desktop and rerun the catchup batch.",
        "stop_run": True,
        "systemic": True,
    },
    {
        "code": "lightning_checkpoint_upgrade_required",
        "patterns": ("Lightning automatically upgraded your loaded checkpoint",),
        "summary": "The diarization container has a Lightning/WhisperX checkpoint compatibility issue.",
        "action": (
            "Rebuild or repin the diarization image to compatible Lightning/WhisperX versions. "
            "As a workaround, rerun with `--require-existing-transcript-json` so only transcript-json-first "
            "files are processed."
        ),
        "stop_run": False,
        "systemic": False,
    },
)


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


def _parse_note_start(value: str) -> datetime | None:
    text = value.strip().strip('"')
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _build_note_lookup(vault_path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    index: dict[str, str] = {}
    notes: list[dict[str, Any]] = []
    meeting_id_pattern = re.compile(r'^meeting_id:\s*"?([^"\n]+)"?\s*$')
    start_pattern = re.compile(r'^start:\s*"?([^"\n]+)"?\s*$')
    audio_line_pattern = re.compile(r"^-\s+audio:\s+(.+)$")
    for note in vault_path.rglob("*.md"):
        if ".obsidian" in note.parts or "_artifacts" in note.parts:
            continue
        meeting_id = ""
        start = None
        audio_path = ""
        try:
            for line in note.read_text(encoding="utf-8", errors="replace").splitlines()[:250]:
                if not meeting_id:
                    match = meeting_id_pattern.match(line.strip())
                    if match:
                        meeting_id = match.group(1).strip()
                if start is None:
                    start_match = start_pattern.match(line.strip())
                    if start_match:
                        start = _parse_note_start(start_match.group(1))
                audio_match = audio_line_pattern.match(line.strip())
                if audio_match:
                    audio_path = audio_match.group(1).strip()
                if meeting_id and start is not None and audio_path:
                    break
        except OSError:
            continue
        if meeting_id and start is not None:
            notes.append(
                {
                    "meeting_id": meeting_id,
                    "start": start,
                    "note_path": str(note.resolve()),
                }
            )
        if not meeting_id or not audio_path or audio_path.startswith("[["):
            continue
        resolved = Path(audio_path).expanduser()
        if not resolved.is_absolute():
            continue
        index[str(resolved.resolve())] = meeting_id
    return index, notes


def _infer_recording_start(audio_path: Path) -> datetime | None:
    name = audio_path.name
    for pattern in _AUDIO_TIMESTAMP_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        stamp = match.group("stamp")
        try:
            if len(stamp) == 13:
                return datetime.strptime(stamp, "%Y%m%d-%H%M")
            if len(stamp) == 14:
                return datetime.strptime(stamp, "%Y%m%d%H%M%S")
        except ValueError:
            return None
    return None


def _find_meeting_id_by_note_start(audio_path: Path, notes: list[dict[str, Any]]) -> str:
    inferred_start = _infer_recording_start(audio_path)
    if inferred_start is None:
        return ""
    candidates: list[tuple[float, str]] = []
    for note in notes:
        note_start = note.get("start")
        if not isinstance(note_start, datetime):
            continue
        note_local = note_start.replace(tzinfo=None)
        delta_seconds = abs((note_local - inferred_start).total_seconds())
        if delta_seconds <= _NOTE_TIME_FALLBACK_TOLERANCE_SECONDS:
            candidates.append((delta_seconds, str(note.get("meeting_id", "")).strip()))
    if len(candidates) != 1:
        return ""
    return candidates[0][1]


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


def _resolve_sidecar_output_path(raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip()).expanduser()
    if not str(candidate):
        return candidate
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    if parts[:3] == ("/", "shared", "diarization"):
        mapped = ROOT / "shared_data" / "diarization"
        if len(parts) > 3:
            mapped = mapped.joinpath(*parts[3:])
        return mapped.resolve()
    return candidate.resolve()


def _match_known_error_snippet(text: str) -> str:
    if not text.strip():
        return ""
    for rule in _SYSTEMIC_ERROR_RULES:
        for pattern in rule["patterns"]:
            match = re.search(re.escape(pattern), text, re.IGNORECASE)
            if match:
                return match.group(0)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _classify_issue(*, error_text: str, skipped: bool) -> dict[str, Any]:
    if skipped and "shorter than minimum duration" in error_text:
        return {
            "code": "short_recording",
            "summary": "Recording is shorter than the configured minimum duration.",
            "action": "No fix required unless you want to lower `--min-duration-seconds`.",
            "stop_run": False,
            "systemic": False,
        }
    if skipped and error_text == "existing diarized artifacts present":
        return {
            "code": "already_diarized",
            "summary": "Diarized artifacts already exist for this meeting.",
            "action": "No fix required.",
            "stop_run": False,
            "systemic": False,
        }
    if skipped and error_text == "missing existing transcript JSON":
        return {
            "code": "missing_transcript_json",
            "summary": "File has no baseline transcript JSON for transcript-json-first diarization.",
            "action": (
                "Generate baseline transcript JSON first, or rerun without "
                "`--require-existing-transcript-json`."
            ),
            "stop_run": False,
            "systemic": False,
        }
    for rule in _SYSTEMIC_ERROR_RULES:
        for pattern in rule["patterns"]:
            if pattern.lower() in error_text.lower():
                return dict(rule)
    return {
        "code": "sidecar_failure",
        "summary": "Sidecar diarization failed for one or more files.",
        "action": "Inspect `results[*].command` and rerun an individual failing command for detail.",
        "stop_run": False,
        "systemic": False,
    }


def _build_issue_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    first_seen: dict[str, dict[str, Any]] = {}
    for item in results:
        code = str(item.get("issue_code", "")).strip()
        if not code:
            continue
        counts[code] += 1
        if code not in first_seen:
            first_seen[code] = item

    summary: list[dict[str, Any]] = []
    for code, count in counts.most_common():
        item = first_seen[code]
        summary.append(
            {
                "code": code,
                "count": count,
                "systemic": bool(item.get("issue_systemic", False)),
                "stop_run": bool(item.get("issue_stop_run", False)),
                "summary": str(item.get("issue_summary", "")),
                "action": str(item.get("issue_action", "")),
                "sample_error": str(item.get("error", "")),
            }
        )
    return summary


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


def _resolve_existing_diarized_artifacts(vault_path: Path, meeting_id: str) -> tuple[Path, Path, Path] | None:
    if not meeting_id:
        return None
    artifact_dir = _artifact_dir_for_meeting(vault_path, meeting_id)
    txt = artifact_dir / f"{meeting_id}.diarized.txt"
    srt = artifact_dir / f"{meeting_id}.diarized.srt"
    json_path = artifact_dir / f"{meeting_id}.diarized.json"
    if txt.exists() and srt.exists() and json_path.exists():
        return txt.resolve(), srt.resolve(), json_path.resolve()
    return None


def _promote_diarized_to_active(*, vault_path: Path, meeting_id: str) -> bool:
    existing = _resolve_existing_diarized_artifacts(vault_path, meeting_id)
    if existing is None:
        return False
    diarized_txt, diarized_srt, diarized_json = existing
    artifact_dir = _artifact_dir_for_meeting(vault_path, meeting_id)
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

    _copy_if_exists(diarized_txt, canonical_txt)
    _copy_if_exists(diarized_srt, canonical_srt)
    _copy_if_exists(diarized_json, canonical_json)
    return True


def _copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def _ensure_note_for_audio(*, vault_path: Path, audio_path: Path, meeting_id: str) -> tuple[str, str]:
    if meeting_id:
        return meeting_id, ""
    previous_vault = os.environ.get("VAULT_PATH")
    os.environ["VAULT_PATH"] = str(vault_path)
    try:
        note_info = create_backfill_note_for_recording(recording_path=audio_path)
    finally:
        if previous_vault is None:
            os.environ.pop("VAULT_PATH", None)
        else:
            os.environ["VAULT_PATH"] = previous_vault
    return str(note_info["meeting_id"]), str(note_info["note_path"])


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

    note_audio_index, notes_by_start = _build_note_lookup(vault_path)
    results: list[dict[str, Any]] = []
    failed = 0
    skipped = 0
    copied = 0
    replaced = 0
    stopped_early = False
    stop_reason = ""
    stop_action = ""

    for audio_path in files:
        meeting_id = _find_meeting_id_from_done_marker(audio_path)
        if not meeting_id:
            meeting_id = note_audio_index.get(str(audio_path.resolve()), "")
        if not meeting_id:
            meeting_id = _find_meeting_id_by_note_start(audio_path, notes_by_start)
        duration_seconds = _audio_duration_seconds(audio_path)
        if args.min_duration_seconds > 0 and duration_seconds is not None and duration_seconds < args.min_duration_seconds:
            item = {
                "audio_path": str(audio_path),
                "meeting_id": meeting_id,
                "audio_duration_seconds": duration_seconds,
                "command": [],
                "ok": False,
                "skipped": True,
                "copied_to_artifacts": False,
                "replaced_active": False,
                "error": f"recording shorter than minimum duration ({duration_seconds:.3f}s < {args.min_duration_seconds}s)",
            }
            issue = _classify_issue(error_text=str(item["error"]), skipped=True)
            item["issue_code"] = issue["code"]
            item["issue_summary"] = issue["summary"]
            item["issue_action"] = issue["action"]
            item["issue_stop_run"] = issue["stop_run"]
            item["issue_systemic"] = issue["systemic"]
            skipped += 1
            results.append(item)
            continue

        note_path = ""
        meeting_id, note_path = _ensure_note_for_audio(
            vault_path=vault_path,
            audio_path=audio_path,
            meeting_id=meeting_id,
        )

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
            issue = _classify_issue(error_text=str(item["error"]), skipped=True)
            item["issue_code"] = issue["code"]
            item["issue_summary"] = issue["summary"]
            item["issue_action"] = issue["action"]
            item["issue_stop_run"] = issue["stop_run"]
            item["issue_systemic"] = issue["systemic"]
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
            "note_path": note_path,
            "audio_duration_seconds": duration_seconds,
            "transcript_json_used": str(transcript_json) if transcript_json is not None else "",
            "command": cmd,
            "ok": False,
            "skipped": False,
            "copied_to_artifacts": False,
            "replaced_active": False,
            "error": "",
        }

        existing_diarized = _resolve_existing_diarized_artifacts(vault_path, meeting_id)
        if existing_diarized is not None:
            item["ok"] = True
            item["skipped"] = True
            item["error"] = "existing diarized artifacts present"
            issue = _classify_issue(error_text=str(item["error"]), skipped=True)
            item["issue_code"] = issue["code"]
            item["issue_summary"] = issue["summary"]
            item["issue_action"] = issue["action"]
            item["issue_stop_run"] = issue["stop_run"]
            item["issue_systemic"] = issue["systemic"]
            if args.replace_active and meeting_id and _promote_diarized_to_active(vault_path=vault_path, meeting_id=meeting_id):
                item["replaced_active"] = True
                replaced += 1
            skipped += 1
            results.append(item)
            continue

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
            item["error"] = _match_known_error_snippet(merged_output) or "sidecar run failed"
            issue = _classify_issue(error_text=merged_output or str(item["error"]), skipped=False)
            item["issue_code"] = issue["code"]
            item["issue_summary"] = issue["summary"]
            item["issue_action"] = issue["action"]
            item["issue_stop_run"] = issue["stop_run"]
            item["issue_systemic"] = issue["systemic"]
            results.append(item)
            if args.stop_on_systemic_error and issue["stop_run"]:
                stopped_early = True
                stop_reason = issue["summary"]
                stop_action = issue["action"]
                break
            continue

        item["ok"] = True
        item["manifest"] = manifest
        transcript_txt = _resolve_sidecar_output_path(str(manifest.get("transcript_txt", "")))
        transcript_srt = _resolve_sidecar_output_path(str(manifest.get("transcript_srt", "")))
        transcript_json = _resolve_sidecar_output_path(str(manifest.get("transcript_json", "")))

        if args.apply_to_artifacts and meeting_id:
            artifact_dir = _artifact_dir_for_meeting(vault_path, meeting_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)

            copied_txt = _copy_if_exists(transcript_txt, artifact_dir / f"{meeting_id}.diarized.txt")
            copied_srt = _copy_if_exists(transcript_srt, artifact_dir / f"{meeting_id}.diarized.srt")
            copied_json = _copy_if_exists(transcript_json, artifact_dir / f"{meeting_id}.diarized.json")
            if copied_txt or copied_srt or copied_json:
                item["copied_to_artifacts"] = True
                copied += 1

            if args.replace_active and copied_txt and _promote_diarized_to_active(vault_path=vault_path, meeting_id=meeting_id):
                item["replaced_active"] = True
                replaced += 1

        results.append(item)

    manifests_dir = (ROOT / "shared_data" / "diarization" / "manifests").resolve()
    manifests_dir.mkdir(parents=True, exist_ok=True)
    report_path = manifests_dir / f"catchup_{_now_stamp()}.json"
    issue_summary = _build_issue_summary(results)
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
        "stop_on_systemic_error": args.stop_on_systemic_error,
        "stopped_early": stopped_early,
        "remaining_files": max(len(files) - len(results), 0),
        "stop_reason": stop_reason,
        "stop_action": stop_action,
        "dry_run": args.dry_run,
        "report_path": str(report_path),
        "issue_summary": issue_summary,
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
    parser.add_argument("--min-duration-seconds", type=float, default=60.0)
    parser.add_argument("--apply-to-artifacts", action="store_true", default=True)
    parser.add_argument("--no-apply-to-artifacts", action="store_false", dest="apply_to_artifacts")
    parser.add_argument("--replace-active", action="store_true")
    parser.add_argument("--prefer-existing-transcript-json", action="store_true", default=True)
    parser.add_argument("--no-prefer-existing-transcript-json", action="store_false", dest="prefer_existing_transcript_json")
    parser.add_argument("--require-existing-transcript-json", action="store_true")
    parser.add_argument("--require-pyannote", action="store_true")
    parser.add_argument("--allow-transcript-without-diarization", action="store_true")
    parser.add_argument("--stop-on-systemic-error", action="store_true", default=True)
    parser.add_argument("--no-stop-on-systemic-error", action="store_false", dest="stop_on_systemic_error")
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
