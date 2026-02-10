import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
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
from meetingctl.transcription import WhisperTranscriptionRunner


def registered_commands() -> list[str]:
    return ["start", "stop", "status", "event", "doctor", "patch-note", "process-queue", "backfill"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meetingctl")
    sub = parser.add_subparsers(dest="command")

    start_parser = sub.add_parser("start")
    start_parser.add_argument("--meeting-id")
    start_parser.add_argument("--title")
    start_parser.add_argument("--platform", default="meet")
    start_parser.add_argument("--note-path")
    start_parser.add_argument("--window-minutes", type=int, default=5)
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
    backfill_parser.add_argument("--extensions", default="wav")
    backfill_parser.add_argument("--max-files", type=int, default=0)
    backfill_parser.add_argument("--process-now", action="store_true")
    backfill_parser.add_argument("--match-calendar", action="store_true")
    backfill_parser.add_argument("--window-minutes", type=int, default=30)
    backfill_parser.add_argument("--rename", action="store_true")
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.add_argument("--json", action="store_true")

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
    transcript_path = cfg.recordings_path / f"{meeting_id}.txt"
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


def _summary_from_transcript(transcript_path: Path) -> dict[str, object]:
    fixture = os.environ.get("MEETINGCTL_PROCESSING_SUMMARY_JSON")
    if fixture:
        return parse_summary_json(fixture)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return generate_summary(transcript_path.read_text(), api_key=api_key)


def _transcribe_for_processing(
    transcript_runner: WhisperTranscriptionRunner,
    wav_path: Path,
    transcript_path: Path,
) -> Path:
    if os.environ.get("MEETINGCTL_PROCESSING_TRANSCRIBE_DRY_RUN") == "1":
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text("dry-run transcript")
        return transcript_path
    return transcript_runner.transcribe(wav_path=wav_path, transcript_path=transcript_path)


def _convert_for_processing(wav_path: Path, mp3_path: Path) -> Path:
    if os.environ.get("MEETINGCTL_PROCESSING_CONVERT_DRY_RUN") == "1":
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_text("dry-run mp3")
        wav_path.unlink(missing_ok=True)
        return mp3_path
    return convert_wav_to_mp3(
        wav_path=wav_path,
        mp3_path=mp3_path,
    )


def _artifact_status_region(result: ProcessResult) -> str:
    transcript_path = result.transcript_path
    mp3_path = result.mp3_path
    return "\n".join(
        [
            f"- transcript_path: {transcript_path}",
            f"- mp3_path: {mp3_path}",
            "- status: complete",
        ]
    )


def _default_queue_handler(payload: dict[str, object]) -> None:
    context = _process_context_from_payload(payload)
    transcript_runner = WhisperTranscriptionRunner()
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
        updates={"transcript": _artifact_status_region(result)},
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


def _queue_job_payload(payload: dict[str, object]) -> None:
    _queue_process_trigger()(payload)


def _backfill_recordings(
    *,
    extensions: list[str],
    max_files: int,
    process_now: bool,
    match_calendar: bool,
    window_minutes: int,
    rename: bool,
    dry_run: bool,
) -> dict[str, object]:
    cfg = load_config()
    exts = [ext.lower().lstrip(".") for ext in extensions if ext.strip()]
    files: list[Path] = []
    for ext in exts:
        files.extend(cfg.recordings_path.glob(f"*.{ext}"))
    files = sorted({path.resolve() for path in files}, key=lambda path: path.stat().st_mtime)
    if max_files > 0:
        files = files[:max_files]

    queued_jobs = 0
    processed_jobs = 0
    failed_jobs = 0
    skipped_existing = 0
    matched_calendar = 0
    unmatched_calendar = 0
    errors: list[dict[str, str]] = []
    plans: list[dict[str, object]] = []

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

    for recording in files:
        stem = recording.stem
        transcript = cfg.recordings_path / f"{stem}.txt"
        mp3 = cfg.recordings_path / f"{stem}.mp3"
        if transcript.exists() and mp3.exists():
            skipped_existing += 1
            continue

        try:
            inferred_start, inferred_source = infer_datetime_from_recording_path(recording)
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

            if dry_run:
                simulated_event = (
                    matched_event
                    if matched_event
                    else {
                        "title": recording.stem.replace("_", " ").replace("-", " ").strip()
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
                    else create_backfill_note_for_recording(recording_path=recording)
                )
            meeting_id = note_info["meeting_id"]
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
        except Exception as exc:
            failed_jobs += 1
            errors.append({"recording": str(recording), "error": str(exc)})

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
        "rename": rename,
        "dry_run": dry_run,
        "extensions": exts,
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
                process_now=args.process_now,
                match_calendar=args.match_calendar,
                window_minutes=args.window_minutes,
                rename=args.rename,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            _print_payload({"error": str(exc)}, args.json)
            return 2
        _print_payload(payload, args.json)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
