import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Callable

from meetingctl.audio import convert_wav_to_mp3
from meetingctl.commands import (
    start_recording_flow,
    start_wrapper,
    stop_recording_flow,
    status_payload,
)
from meetingctl.calendar.service import (
    CalendarResolutionError,
    resolve_event_candidates_near_timestamp,
    resolve_event_near_timestamp,
    resolve_now_or_next_event,
)
from meetingctl.config import load_config
from meetingctl.doctor import run_doctor
from meetingctl.note.patcher import patch_note_file
from meetingctl.note.service import (
    create_adhoc_note,
    create_backfill_note_for_recording,
    create_note_from_event,
    infer_datetime_from_recording_path,
    preview_note_from_event,
)
from meetingctl.process import ProcessContext, ProcessResult, run_processing
from meetingctl.queue_worker import QueueLockError, process_queue_jobs
from meetingctl.recording import AudioHijackRecorder
from meetingctl.runtime_state import RuntimeStateStore
from meetingctl.summary_client import generate_summary
from meetingctl.summary_parser import SummaryParseError, parse_summary_json, summary_to_patch_regions
from meetingctl.transcription import TranscriptionRunner, create_transcription_runner


def registered_commands() -> list[str]:
    return [
        "start",
        "stop",
        "status",
        "event",
        "doctor",
        "patch-note",
        "process-queue",
        "backfill",
        "ingest-watch",
        "audit-notes",
    ]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meetingctl")
    sub = parser.add_subparsers(dest="command")

    start_parser = sub.add_parser("start")
    start_parser.add_argument("--meeting-id")
    start_parser.add_argument("--title")
    start_parser.add_argument("--platform", default="meet")
    start_parser.add_argument("--note-path")
    start_parser.add_argument(
        "--window-minutes",
        type=int,
        default=_env_int("MEETINGCTL_START_WINDOW_MINUTES", 5),
    )
    start_parser.add_argument("--json", action="store_true")

    stop_parser = sub.add_parser("stop")
    stop_parser.add_argument("--json", action="store_true")

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--json", action="store_true")

    patch_parser = sub.add_parser("patch-note")
    patch_parser.add_argument("--note-path", required=True)
    patch_parser.add_argument("--summary-json", required=True)
    patch_parser.add_argument("--dry-run", action="store_true")
    patch_parser.add_argument("--json", action="store_true")

    process_queue_parser = sub.add_parser("process-queue")
    process_queue_parser.add_argument("--max-jobs", type=int, default=1)
    process_queue_parser.add_argument("--json", action="store_true")

    backfill_parser = sub.add_parser("backfill")
    backfill_parser.add_argument(
        "--extensions",
        default=_env_str("MEETINGCTL_BACKFILL_EXTENSIONS", "wav"),
    )
    backfill_parser.add_argument("--max-files", type=int, default=0)
    backfill_parser.add_argument(
        "--file-list",
        default="",
        help="Path to newline-delimited recording file list; when set, only these files are considered.",
    )
    backfill_parser.add_argument("--process-now", action="store_true")
    backfill_parser.add_argument("--match-calendar", action="store_true")
    backfill_parser.add_argument(
        "--export-unmatched-manifest",
        default="",
        help="Write unmatched recording paths to this manifest file.",
    )
    backfill_parser.add_argument(
        "--review-calendar",
        action="store_true",
        help="Interactive per-file calendar confirmation/selection.",
    )
    backfill_parser.add_argument(
        "--review-max-candidates",
        type=int,
        default=5,
        help="Maximum event candidates shown per file in --review-calendar mode.",
    )
    backfill_parser.add_argument(
        "--window-minutes",
        type=int,
        default=_env_int("MEETINGCTL_MATCH_WINDOW_MINUTES", 30),
    )
    backfill_parser.add_argument("--rename", action="store_true")
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.add_argument(
        "--progress",
        action="store_true",
        help="Emit per-file progress updates to stderr.",
    )
    backfill_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit per-file details to stderr.",
    )
    backfill_parser.add_argument("--json", action="store_true")

    ingest_parser = sub.add_parser("ingest-watch")
    ingest_parser.add_argument("--once", action="store_true")
    ingest_parser.add_argument("--poll-seconds", type=int, default=20)
    ingest_parser.add_argument("--max-polls", type=int, default=0)
    ingest_parser.add_argument(
        "--min-age-seconds",
        type=int,
        default=_env_int("MEETINGCTL_INGEST_MIN_AGE_SECONDS", 15),
    )
    ingest_parser.add_argument(
        "--extensions",
        default=_env_str("MEETINGCTL_INGEST_EXTENSIONS", "wav,m4a"),
    )
    ingest_parser.add_argument("--match-calendar", action="store_true")
    ingest_parser.add_argument(
        "--window-minutes",
        type=int,
        default=_env_int("MEETINGCTL_MATCH_WINDOW_MINUTES", 30),
    )
    ingest_parser.add_argument("--process-now", action="store_true")
    ingest_parser.add_argument("--json", action="store_true")

    audit_parser = sub.add_parser("audit-notes")
    audit_parser.add_argument("--json", action="store_true")

    event_parser = sub.add_parser("event")
    event_parser.add_argument("--now-or-next", type=int, default=5)
    event_parser.add_argument("--json", action="store_true")

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--json", action="store_true")

    return parser


def _state_store() -> RuntimeStateStore:
    state_file = Path(
        os.environ.get("MEETINGCTL_STATE_FILE", "~/.local/state/meetingctl/current.json")
    ).expanduser()
    return RuntimeStateStore(state_file)


def _print_payload(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))
    else:
        print(payload)


def _now_utc() -> datetime:
    override = os.environ.get("MEETINGCTL_NOW_ISO")
    if override:
        return datetime.fromisoformat(override)
    return datetime.now(UTC)


def _process_queue_file() -> Path:
    return Path(
        os.environ.get(
            "MEETINGCTL_PROCESS_QUEUE_FILE", "~/.local/state/meetingctl/process_queue.jsonl"
        )
    ).expanduser()


def _queue_process_trigger() -> Callable[[dict[str, object]], None]:
    queue_file = _process_queue_file()

    def _enqueue(payload: dict[str, object]) -> None:
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        with queue_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload))
            fh.write("\n")

    return _enqueue


def _processed_jobs_log_file() -> Path:
    return Path(
        os.environ.get(
            "MEETINGCTL_PROCESSED_JOBS_FILE", "~/.local/state/meetingctl/processed_jobs.jsonl"
        )
    ).expanduser()


def _ingested_files_log_file() -> Path:
    return Path(
        os.environ.get(
            "MEETINGCTL_INGESTED_FILES_FILE", "~/.local/state/meetingctl/ingested_files.jsonl"
        )
    ).expanduser()


def _require_payload_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Queue payload missing required key: {key}")
    return value


def _resolve_wav_path(
    *,
    payload: dict[str, object],
    recordings_path: Path,
    meeting_id: str,
) -> Path:
    recordings_root = recordings_path.expanduser().resolve()
    explicit = payload.get("wav_path")
    if isinstance(explicit, str) and explicit.strip():
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.exists():
            raise ValueError(f"Missing WAV input: {candidate}. Stop recording before processing queue.")
        if not candidate.is_relative_to(recordings_root):
            raise ValueError(
                f"WAV path must be within recordings path: {recordings_root}."
            )
        return candidate

    expected = recordings_root / f"{meeting_id}.wav"
    if expected.exists():
        return expected

    raise ValueError(f"Missing WAV input: {expected}. Stop recording before processing queue.")


def _resolve_note_path(*, note_path: str, vault_path: Path) -> Path:
    resolved_note_path = Path(note_path).expanduser().resolve()
    resolved_vault_path = vault_path.expanduser().resolve()
    if not resolved_note_path.is_relative_to(resolved_vault_path):
        raise ValueError(
            f"Note path must be inside vault path: {resolved_vault_path}."
        )
    return resolved_note_path


def _process_context_from_payload(payload: dict[str, object]) -> ProcessContext:
    cfg = load_config()
    meeting_id = _require_payload_str(payload, "meeting_id")
    note_path = _resolve_note_path(
        note_path=_require_payload_str(payload, "note_path"),
        vault_path=cfg.vault_path,
    )
    transcript_path = _preferred_transcript_path(meeting_id=meeting_id, cfg=cfg)
    wav_path = _resolve_wav_path(
        payload=payload,
        recordings_path=cfg.recordings_path,
        meeting_id=meeting_id,
    )
    mp3_path = cfg.recordings_path / f"{meeting_id}.mp3"
    return ProcessContext(
        meeting_id=meeting_id,
        note_path=note_path,
        wav_path=wav_path,
        transcript_path=transcript_path,
        mp3_path=mp3_path,
    )


def _text_artifacts_in_vault_enabled() -> bool:
    value = os.environ.get("MEETINGCTL_TEXT_ARTIFACTS_IN_VAULT", "1").strip().lower()
    return value not in {"0", "false", "no"}


def _vault_artifact_dir(*, meeting_id: str) -> Path:
    meetings_folder = os.environ.get("DEFAULT_MEETINGS_FOLDER", "meetings").strip() or "meetings"
    return (
        Path(os.environ.get("VAULT_PATH", ".")).expanduser().resolve()
        / meetings_folder
        / "_artifacts"
        / meeting_id
    )


def _preferred_transcript_path(*, meeting_id: str, cfg) -> Path:
    if _text_artifacts_in_vault_enabled():
        return _vault_artifact_dir(meeting_id=meeting_id) / f"{meeting_id}.txt"
    return cfg.recordings_path / f"{meeting_id}.txt"


def _summary_from_transcript(transcript_path: Path) -> dict[str, object]:
    fixture = os.environ.get("MEETINGCTL_PROCESSING_SUMMARY_JSON")
    if fixture:
        return parse_summary_json(fixture)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return generate_summary(transcript_path.read_text(), api_key=api_key)


def _transcribe_for_processing(
    transcript_runner: TranscriptionRunner,
    wav_path: Path,
    transcript_path: Path,
) -> Path:
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN") == "1":
        transcript_path.write_text("dry-run transcript")
        return transcript_path
    return transcript_runner.transcribe(wav_path=wav_path, transcript_path=transcript_path)


def _convert_for_processing(wav_path: Path, mp3_path: Path) -> Path:
    # Preserve non-WAV sources (e.g., Voice Memos m4a) as canonical artifacts.
    if wav_path.suffix.lower() != ".wav":
        return wav_path
    if os.environ.get("MEETINGCTL_PROCESSING_CONVERT_DRY_RUN") == "1":
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_text("dry-run mp3")
        wav_path.unlink(missing_ok=True)
        return mp3_path
    return convert_wav_to_mp3(
        wav_path=wav_path,
        mp3_path=mp3_path,
    )


def _artifact_status_region(transcript_path: Path) -> str:
    if transcript_path.exists():
        transcript_body = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
        if transcript_body:
            return f"```text\n{transcript_body}\n```"
    return "> _Transcript file is empty._"


def _references_region(transcript_path: Path, audio_path: Path) -> str:
    transcript_srt_path = transcript_path.with_suffix(".srt")
    transcript_json_path = transcript_path.with_suffix(".json")
    meetings_folder = os.environ.get("DEFAULT_MEETINGS_FOLDER", "meetings").strip() or "meetings"
    artifact_root = Path(os.environ.get("VAULT_PATH", ".")).expanduser().resolve() / meetings_folder

    def _link(path: Path) -> str:
        if path.exists():
            try:
                rel = path.resolve().relative_to(artifact_root.resolve())
                rel_str = str(rel)
                return f"[{rel_str}]({rel_str})"
            except Exception:
                pass
        return str(path)

    lines = [f"- transcript_txt: {_link(transcript_path)}"]
    lines.append(f"- transcript_srt: {_link(transcript_srt_path)}" if transcript_srt_path.exists() else "- transcript_srt: (not generated)")
    lines.append(f"- transcript_json: {_link(transcript_json_path)}" if transcript_json_path.exists() else "- transcript_json: (not generated)")
    lines.append(f"- audio: {_link(audio_path)}")
    status = "complete" if transcript_path.exists() and audio_path.exists() else "partial"
    lines.append(f"- status: {status}")
    return "\n".join(lines)


def _default_queue_handler(payload: dict[str, object]) -> None:
    context = _process_context_from_payload(payload)
    transcript_runner = create_transcription_runner()
    result = run_processing(
        context=context,
        transcribe=lambda wav_path, transcript_path: _transcribe_for_processing(
            transcript_runner,
            wav_path,
            transcript_path,
        ),
        summarize=_summary_from_transcript,
        patch_note=lambda note_path, summary_payload: patch_note_file(
            note_path=note_path,
            updates=summary_to_patch_regions(summary_payload),
            dry_run=False,
        ),
        convert_audio=_convert_for_processing,
    )
    patch_note_file(
        note_path=result.note_path,
        updates=(
            {
                "transcript": _artifact_status_region(result.transcript_path),
                "references": _references_region(result.transcript_path, result.mp3_path),
            }
            if "<!-- REFERENCES_START -->" in result.note_path.read_text(encoding="utf-8", errors="replace")
            and "<!-- REFERENCES_END -->" in result.note_path.read_text(encoding="utf-8", errors="replace")
            else {"transcript": _artifact_status_region(result.transcript_path)}
        ),
        dry_run=False,
    )

    log_file = _processed_jobs_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    processed_payload = {
        "meeting_id": result.meeting_id,
        "note_path": str(result.note_path),
        "transcript_path": str(result.transcript_path),
        "mp3_path": str(result.mp3_path),
        "reused_transcript": result.reused_transcript,
        "reused_summary": result.reused_summary,
    }
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(processed_payload))
        fh.write("\n")


def _assert_transcription_backend_ready() -> None:
    def _binary_available(name: str) -> bool:
        if shutil.which(name) is not None:
            return True
        candidates = [
            Path(sys.executable).parent / name,
            Path(sys.prefix) / "bin" / name,
        ]
        return any(candidate.exists() and os.access(candidate, os.X_OK) for candidate in candidates)

    if os.environ.get("MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN") == "1":
        return
    backend = os.environ.get("MEETINGCTL_TRANSCRIPTION_BACKEND", "whisper").strip().lower()
    allow_fallback = os.environ.get("MEETINGCTL_TRANSCRIPTION_FALLBACK_TO_WHISPER", "1").strip().lower()
    fallback_enabled = allow_fallback not in {"0", "false", "no"}
    if backend == "whisperx":
        has_whisperx = _binary_available("whisperx")
        has_whisper = _binary_available("whisper")
        if has_whisperx:
            return
        if fallback_enabled and has_whisper:
            return
        if fallback_enabled:
            raise RuntimeError(
                "Transcription backend unavailable: install `whisperx` or `whisper` in this runtime."
            )
        raise RuntimeError(
            "Transcription backend unavailable: install `whisperx` in this runtime."
        )
    if not _binary_available("whisper"):
        raise RuntimeError(
            "Transcription backend unavailable: install `whisper` in this runtime."
        )


def _queue_job_payload(payload: dict[str, object]) -> None:
    _queue_process_trigger()(payload)


def _load_ingested_paths(log_file: Path) -> set[str]:
    if not log_file.exists():
        return set()
    seen: set[str] = set()
    for line in log_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        wav_path = payload.get("wav_path")
        if isinstance(wav_path, str) and wav_path:
            seen.add(wav_path)
    return seen


def _append_ingested_path(log_file: Path, wav_path: Path, meeting_id: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "wav_path": str(wav_path.resolve()),
        "meeting_id": meeting_id,
        "ingested_at": _now_utc().isoformat(),
    }
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record))
        fh.write("\n")


def _ingest_wav_files_once(
    *,
    min_age_seconds: int,
    extensions: list[str],
    match_calendar: bool,
    window_minutes: int,
    process_now: bool,
) -> dict[str, object]:
    if process_now:
        _assert_transcription_backend_ready()
    cfg = load_config()
    ingested_log = _ingested_files_log_file()
    seen = _load_ingested_paths(ingested_log)

    exts = [ext.lower().lstrip(".") for ext in extensions if ext.strip()]
    if not exts:
        exts = ["wav", "m4a"]
    audio_files = sorted(
        {
            path.resolve()
            for ext in exts
            for path in cfg.recordings_path.glob(f"*.{ext}")
        },
        key=lambda path: path.stat().st_mtime,
    )
    discovered_audio = len(audio_files)
    queued_jobs = 0
    processed_jobs = 0
    skipped_already_ingested = 0
    skipped_too_new = 0
    matched_calendar = 0
    unmatched_calendar = 0
    failed_jobs = 0
    errors: list[dict[str, str]] = []

    now_ts = time.time()
    for audio_file in audio_files:
        audio_key = str(audio_file.resolve())
        if audio_key in seen:
            skipped_already_ingested += 1
            continue
        age_seconds = now_ts - audio_file.stat().st_mtime
        if age_seconds < max(min_age_seconds, 0):
            skipped_too_new += 1
            continue

        try:
            inferred_start, _ = infer_datetime_from_recording_path(audio_file)
            matched_event: dict[str, object] | None = None
            if match_calendar:
                matched_event = resolve_event_near_timestamp(
                    at=inferred_start,
                    window_minutes=max(window_minutes, 0),
                )
                if matched_event:
                    matched_calendar += 1
                else:
                    unmatched_calendar += 1

            note_info = (
                create_note_from_event(matched_event)
                if matched_event
                else create_backfill_note_for_recording(recording_path=audio_file)
            )
            payload = {
                "meeting_id": note_info["meeting_id"],
                "note_path": note_info["note_path"],
                "wav_path": str(audio_file),
            }
            if process_now:
                _default_queue_handler(payload)
                processed_jobs += 1
            else:
                _queue_job_payload(payload)
                queued_jobs += 1
            _append_ingested_path(ingested_log, audio_file, note_info["meeting_id"])
            seen.add(audio_key)
        except Exception as exc:
            failed_jobs += 1
            errors.append({"recording": str(audio_file), "error": str(exc)})

    return {
        "discovered_audio": discovered_audio,
        "discovered_wav": discovered_audio,
        "queued_jobs": queued_jobs,
        "processed_jobs": processed_jobs,
        "failed_jobs": failed_jobs,
        "skipped_already_ingested": skipped_already_ingested,
        "skipped_too_new": skipped_too_new,
        "match_calendar": match_calendar,
        "matched_calendar": matched_calendar,
        "unmatched_calendar": unmatched_calendar,
        "process_now": process_now,
        "min_age_seconds": min_age_seconds,
        "errors": errors,
    }


def _run_ingest_watch(
    *,
    once: bool,
    poll_seconds: int,
    max_polls: int,
    min_age_seconds: int,
    extensions: list[str],
    match_calendar: bool,
    window_minutes: int,
    process_now: bool,
) -> dict[str, object]:
    polls = 0
    aggregate = {
        "polls": 0,
        "queued_jobs": 0,
        "processed_jobs": 0,
        "failed_jobs": 0,
        "skipped_already_ingested": 0,
        "skipped_too_new": 0,
        "matched_calendar": 0,
        "unmatched_calendar": 0,
        "last_poll": {},
    }
    while True:
        poll_result = _ingest_wav_files_once(
            min_age_seconds=min_age_seconds,
            extensions=extensions,
            match_calendar=match_calendar,
            window_minutes=window_minutes,
            process_now=process_now,
        )
        polls += 1
        aggregate["polls"] = polls
        aggregate["queued_jobs"] += int(poll_result["queued_jobs"])
        aggregate["processed_jobs"] += int(poll_result["processed_jobs"])
        aggregate["failed_jobs"] += int(poll_result["failed_jobs"])
        aggregate["skipped_already_ingested"] += int(poll_result["skipped_already_ingested"])
        aggregate["skipped_too_new"] += int(poll_result["skipped_too_new"])
        aggregate["matched_calendar"] += int(poll_result["matched_calendar"])
        aggregate["unmatched_calendar"] += int(poll_result["unmatched_calendar"])
        aggregate["last_poll"] = poll_result

        if once:
            break
        if max_polls > 0 and polls >= max_polls:
            break
        time.sleep(max(poll_seconds, 1))
    return aggregate


def _backfill_recordings(
    *,
    extensions: list[str],
    max_files: int,
    file_list: str,
    process_now: bool,
    match_calendar: bool,
    export_unmatched_manifest: str,
    review_calendar: bool,
    review_max_candidates: int,
    window_minutes: int,
    rename: bool,
    dry_run: bool,
    progress: bool,
    verbose: bool,
) -> dict[str, object]:
    if process_now and not dry_run:
        _assert_transcription_backend_ready()
    if review_calendar and not sys.stdin.isatty():
        raise ValueError("--review-calendar requires an interactive terminal.")
    cfg = load_config()
    exts = [ext.lower().lstrip(".") for ext in extensions if ext.strip()]
    resolved_file_list = ""
    files: list[Path] = []
    if file_list.strip():
        manifest_path = Path(file_list).expanduser().resolve()
        resolved_file_list = str(manifest_path)
        if not manifest_path.exists():
            raise ValueError(f"File list does not exist: {manifest_path}")
        for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
            candidate = raw_line.strip()
            if not candidate or candidate.startswith("#"):
                continue
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = (manifest_path.parent / path).resolve()
            else:
                path = path.resolve()
            if exts and path.suffix.lower().lstrip(".") not in exts:
                continue
            files.append(path)
    else:
        for ext in exts:
            files.extend(cfg.recordings_path.glob(f"*.{ext}"))
        files = sorted(files, key=lambda path: path.stat().st_mtime)
    files = list(dict.fromkeys(path.resolve() for path in files))
    if max_files > 0:
        files = files[:max_files]

    queued_jobs = 0
    processed_jobs = 0
    failed_jobs = 0
    skipped_existing = 0
    matched_calendar = 0
    unmatched_calendar = 0
    skipped_manual = 0
    errors: list[dict[str, str]] = []
    plans: list[dict[str, object]] = []
    unmatched_recordings: list[str] = []
    total = len(files)

    def _emit(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    def _prompt_calendar_decision(
        *,
        recording: Path,
        inferred_start: datetime,
        auto_match: dict[str, object] | None,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, str | None, bool]:
        print("\n" + "=" * 72, file=sys.stderr)
        print(f"Recording: {recording}", file=sys.stderr)
        print(f"Inferred start: {inferred_start.isoformat()}", file=sys.stderr)
        if auto_match:
            print(
                "Auto match: "
                f"{auto_match.get('title', '(untitled)')} "
                f"[{auto_match.get('start', '')} -> {auto_match.get('end', '')}] "
                f"d={auto_match.get('match_distance_minutes', '?')}m",
                file=sys.stderr,
            )
        else:
            print("Auto match: none", file=sys.stderr)
        if candidates:
            print("Candidates:", file=sys.stderr)
            for idx, candidate in enumerate(candidates, start=1):
                print(
                    f"  {idx}. {candidate.get('title', '(untitled)')} "
                    f"[{candidate.get('start', '')} -> {candidate.get('end', '')}] "
                    f"cal={candidate.get('calendar_name', '')} "
                    f"d={candidate.get('match_distance_minutes', '?')}m",
                    file=sys.stderr,
                )
        else:
            print("Candidates: none", file=sys.stderr)

        while True:
            choice = input(
                "Select [1-N] calendar event, [a]d hoc title, [s]kip, "
                "or Enter for auto/ad hoc: "
            ).strip()
            if not choice:
                return auto_match, None, False
            lowered = choice.lower()
            if lowered in {"s", "skip"}:
                return None, None, True
            if lowered in {"a", "adhoc", "ad-hoc"}:
                manual_title = input("Ad hoc meeting title (blank = filename): ").strip()
                return None, manual_title or None, False
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(candidates):
                    return candidates[idx - 1], None, False
            print("Invalid selection. Try again.", file=sys.stderr)

    def _rename_artifact(path: Path, meeting_id: str, dry_run_mode: bool) -> Path:
        target = path.with_name(f"{meeting_id}{path.suffix.lower()}")
        if target == path:
            return path
        if target.exists():
            raise ValueError(f"Refusing to overwrite existing file during rename: {target}")
        if not dry_run_mode:
            path.rename(target)
        return target

    def _rename_recording_family(recording_path: Path, meeting_id: str, dry_run_mode: bool) -> Path:
        moved_recording = _rename_artifact(recording_path, meeting_id, dry_run_mode)
        for ext in (".txt", ".mp3"):
            sibling = recording_path.with_suffix(ext)
            if sibling.exists():
                _rename_artifact(sibling, meeting_id, dry_run_mode)
        return moved_recording

    if progress:
        _emit(f"backfill progress: 0/{total}")

    for index, recording in enumerate(files, start=1):
        try:
            if verbose:
                _emit(f"backfill processing: {recording}")
            inferred_start, inferred_source = infer_datetime_from_recording_path(recording)
            matched_event: dict[str, object] | None = None
            manual_title: str | None = None
            if match_calendar:
                matched_event = resolve_event_near_timestamp(
                    at=inferred_start,
                    window_minutes=max(window_minutes, 0),
                )
                if matched_event:
                    matched_calendar += 1
                else:
                    unmatched_calendar += 1
                    unmatched_recordings.append(str(recording))
            if review_calendar:
                candidates = resolve_event_candidates_near_timestamp(
                    at=inferred_start,
                    window_minutes=max(window_minutes, 0),
                    max_candidates=max(review_max_candidates, 1),
                )
                matched_event, manual_title, skipped = _prompt_calendar_decision(
                    recording=recording,
                    inferred_start=inferred_start,
                    auto_match=matched_event,
                    candidates=candidates,
                )
                if skipped:
                    skipped_manual += 1
                    if progress:
                        _emit(
                            f"backfill progress: {index}/{total} "
                            f"(processed={processed_jobs} failed={failed_jobs} skipped={skipped_existing + skipped_manual})"
                        )
                    continue

            if dry_run:
                simulated_event = (
                    matched_event
                    if matched_event
                    else {
                        "title": (
                            manual_title
                            or recording.stem.replace("_", " ").replace("-", " ").strip()
                        )
                        or "Backfill Meeting",
                        "start": inferred_start.isoformat(),
                        "end": inferred_start.isoformat(),
                    }
                )
                note_info = preview_note_from_event(simulated_event)
            else:
                note_info = (
                    create_note_from_event(matched_event)
                    if matched_event
                    else create_backfill_note_for_recording(
                        recording_path=recording,
                        title=manual_title,
                    )
                )
            meeting_id = note_info["meeting_id"]
            transcript = _preferred_transcript_path(meeting_id=meeting_id, cfg=cfg)
            if transcript.exists():
                skipped_existing += 1
                if verbose:
                    _emit(f"backfill skip existing: {recording} (transcript exists for {meeting_id})")
                if progress:
                    _emit(
                        f"backfill progress: {index}/{total} "
                        f"(processed={processed_jobs} failed={failed_jobs} skipped={skipped_existing})"
                    )
                continue
            resolved_recording = recording
            if rename and matched_event:
                resolved_recording = _rename_recording_family(
                    recording_path=recording,
                    meeting_id=meeting_id,
                    dry_run_mode=dry_run,
                )

            payload = {
                "meeting_id": meeting_id,
                "note_path": note_info["note_path"],
                "wav_path": str(resolved_recording),
            }
            if dry_run:
                plans.append(
                    {
                        "recording": str(recording),
                        "inferred_start": inferred_start.isoformat(),
                        "inferred_source": inferred_source,
                        "matched_calendar": bool(matched_event),
                        "meeting_id": meeting_id,
                        "note_path": note_info["note_path"],
                        "wav_path": payload["wav_path"],
                        "match_distance_minutes": (
                            matched_event.get("match_distance_minutes") if matched_event else None
                        ),
                    }
                )
            else:
                if process_now:
                    _default_queue_handler(payload)
                    processed_jobs += 1
                else:
                    _queue_job_payload(payload)
                    queued_jobs += 1
            if progress:
                _emit(
                    f"backfill progress: {index}/{total} "
                    f"(processed={processed_jobs} failed={failed_jobs} skipped={skipped_existing})"
                )
        except Exception as exc:
            failed_jobs += 1
            errors.append({"recording": str(recording), "error": str(exc)})
            if verbose:
                _emit(f"backfill error: {recording} :: {exc}")
            if progress:
                _emit(
                    f"backfill progress: {index}/{total} "
                    f"(processed={processed_jobs} failed={failed_jobs} skipped={skipped_existing})"
                )

    exported_unmatched_manifest = ""
    if export_unmatched_manifest.strip():
        manifest_path = Path(export_unmatched_manifest).expanduser().resolve()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("\n".join(unmatched_recordings) + ("\n" if unmatched_recordings else ""))
        exported_unmatched_manifest = str(manifest_path)

    return {
        "discovered_files": len(files),
        "queued_jobs": queued_jobs,
        "processed_jobs": processed_jobs,
        "failed_jobs": failed_jobs,
        "skipped_existing": skipped_existing,
        "process_now": process_now,
        "match_calendar": match_calendar,
        "matched_calendar": matched_calendar,
        "unmatched_calendar": unmatched_calendar,
        "unmatched_recordings": len(unmatched_recordings),
        "exported_unmatched_manifest": exported_unmatched_manifest,
        "review_calendar": review_calendar,
        "review_max_candidates": max(review_max_candidates, 1),
        "skipped_manual": skipped_manual,
        "rename": rename,
        "dry_run": dry_run,
        "extensions": exts,
        "file_list": resolved_file_list,
        "plans": plans,
        "errors": errors,
    }


def _format_doctor_human(payload: dict[str, object]) -> str:
    status = "OK" if payload.get("ok") else "NOT OK"
    lines = [f"Doctor status: {status}"]
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        marker = "PASS" if check.get("ok") else "FAIL"
        name = check.get("name", "unknown")
        message = check.get("message", "")
        hint = check.get("hint", "")
        lines.append(f"- [{marker}] {name}: {message}")
        if hint:
            lines.append(f"  hint: {hint}")
    return "\n".join(lines)


def _audit_notes_duplicates() -> dict[str, object]:
    vault_path = Path(os.environ.get("VAULT_PATH", ".")).expanduser().resolve()
    meetings_folder = Path(os.environ.get("DEFAULT_MEETINGS_FOLDER", "meetings"))
    note_dir = (vault_path / meetings_folder).resolve()
    if not note_dir.exists():
        return {
            "discovered_notes": 0,
            "unique_meeting_ids": 0,
            "duplicate_meeting_ids": 0,
            "duplicates": [],
        }

    pattern = re.compile(r"(m-[0-9a-f]{10})")
    by_meeting_id: dict[str, list[str]] = {}
    for note_path in sorted(note_dir.glob("*.md")):
        match = pattern.search(note_path.name)
        if not match:
            continue
        meeting_id = match.group(1)
        by_meeting_id.setdefault(meeting_id, []).append(str(note_path))

    duplicates = [
        {"meeting_id": meeting_id, "note_paths": paths}
        for meeting_id, paths in sorted(by_meeting_id.items())
        if len(paths) > 1
    ]
    return {
        "discovered_notes": len(list(note_dir.glob("*.md"))),
        "unique_meeting_ids": len(by_meeting_id),
        "duplicate_meeting_ids": len(duplicates),
        "duplicates": duplicates,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    store = _state_store()
    recorder = AudioHijackRecorder()

    if args.command == "status":
        payload = status_payload(store, now=_now_utc())
        _print_payload(payload, args.json)
        return 0
    if args.command == "start":
        try:
            if args.title:
                if args.note_path:
                    note_info = {
                        "meeting_id": args.meeting_id or _now_utc().strftime("adhoc-%Y%m%d%H%M%S"),
                        "note_path": args.note_path,
                    }
                else:
                    note_info = create_adhoc_note(
                        title=args.title or "Untitled Meeting",
                        platform=args.platform,
                        meeting_id=args.meeting_id,
                        start=_now_utc(),
                    )
                payload = start_recording_flow(
                    store=store,
                    recorder=recorder,
                    event={"title": args.title or "Untitled Meeting", "platform": args.platform},
                    meeting_id=note_info["meeting_id"],
                    note_path=note_info["note_path"],
                    now=_now_utc(),
                )
            else:
                payload = start_wrapper(
                    store=store,
                    recorder=recorder,
                    event_resolver=lambda: resolve_now_or_next_event(
                        now=_now_utc(), window_minutes=args.window_minutes
                    ),
                    note_creator=create_note_from_event,
                    now=_now_utc(),
                )
        except Exception as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 1
        _print_payload(payload, args.json)
        return 0
    if args.command == "stop":
        payload = stop_recording_flow(
            store=store,
            recorder=recorder,
            process_trigger=_queue_process_trigger(),
        )
        _print_payload(payload, args.json)
        return 0
    if args.command == "patch-note":
        try:
            parsed_summary = parse_summary_json(Path(args.summary_json).read_text())
        except SummaryParseError as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 2
        payload = patch_note_file(
            note_path=Path(args.note_path),
            updates=summary_to_patch_regions(parsed_summary),
            dry_run=args.dry_run,
        )
        _print_payload(payload, args.json)
        return 0
    if args.command == "event":
        try:
            payload = resolve_now_or_next_event(now=_now_utc(), window_minutes=args.now_or_next)
        except CalendarResolutionError as exc:
            _print_payload(exc.to_payload(), args.json)
            return 2
        _print_payload(payload, args.json)
        return 0
    if args.command == "doctor":
        payload = run_doctor()
        if args.json:
            _print_payload(payload, True)
        else:
            print(_format_doctor_human(payload))
        return 0
    if args.command == "process-queue":
        try:
            payload = process_queue_jobs(
                queue_file=_process_queue_file(),
                handler=_default_queue_handler,
                max_jobs=max(args.max_jobs, 1),
            )
        except QueueLockError as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 2
        _print_payload(payload, args.json)
        return 0
    if args.command == "backfill":
        try:
            extensions = [value.strip() for value in args.extensions.split(",") if value.strip()]
            payload = _backfill_recordings(
                extensions=extensions or ["wav"],
                max_files=max(args.max_files, 0),
                file_list=args.file_list,
                process_now=args.process_now,
                match_calendar=args.match_calendar,
                export_unmatched_manifest=args.export_unmatched_manifest,
                review_calendar=args.review_calendar,
                review_max_candidates=args.review_max_candidates,
                window_minutes=args.window_minutes,
                rename=args.rename,
                dry_run=args.dry_run,
                progress=args.progress,
                verbose=args.verbose,
            )
        except Exception as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 2
        _print_payload(payload, args.json)
        return 0
    if args.command == "ingest-watch":
        try:
            extensions = [value.strip() for value in args.extensions.split(",") if value.strip()]
            payload = _run_ingest_watch(
                once=args.once,
                poll_seconds=args.poll_seconds,
                max_polls=args.max_polls,
                min_age_seconds=max(args.min_age_seconds, 0),
                extensions=extensions or ["wav", "m4a"],
                match_calendar=args.match_calendar,
                window_minutes=args.window_minutes,
                process_now=args.process_now,
            )
        except Exception as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 2
        _print_payload(payload, args.json)
        return 0
    if args.command == "audit-notes":
        try:
            payload = _audit_notes_duplicates()
        except Exception as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 2
        _print_payload(payload, args.json)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
