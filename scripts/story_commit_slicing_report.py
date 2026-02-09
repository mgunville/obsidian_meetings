#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path


STORY_FILE_RULES = {
    "E1-S1": ["pyproject.toml", "README.md"],
    "E1-S2": ["src/meetingctl/cli.py", "tests/test_cli_smoke.py", "tests/test_cli_registry.py", "tests/test_cli_json_commands.py"],
    "E1-S3": ["src/meetingctl/config.py", "tests/test_config.py"],
    "E2-S1": ["src/meetingctl/calendar/selector.py", "tests/test_event_selector.py"],
    "E2-S2": ["src/meetingctl/calendar/backends.py", "tests/test_calendar_resolution.py"],
    "E2-S3": ["src/meetingctl/calendar/service.py", "tests/test_calendar_resolution.py"],
    "E2-S4": ["tests/test_event_command_contract.py", "tests/fixtures/event_now_or_next.json", "tests/fixtures/event_error_jxa_unavailable.json", "tests/fixtures/event_error_no_match.json"],
    "E3-S1": ["src/meetingctl/note/identity.py", "tests/test_note_identity.py"],
    "E3-S2": ["src/meetingctl/note/template.py", "src/meetingctl/note/service.py", "templates/meeting.md", "tests/test_note_template.py", "tests/test_note_service.py"],
    "E3-S3": ["src/meetingctl/note/patcher.py", "tests/test_note_patcher.py"],
    "E3-S4": ["tests/test_patch_note_dry_run.py", "tests/fixtures/patch_note_dry_run.json", "tests/test_patch_note_cli.py"],
    "E4-S1": ["src/meetingctl/runtime_state.py", "tests/test_runtime_state.py"],
    "E4-S2": ["src/meetingctl/recording.py"],
    "E4-S3": ["src/meetingctl/commands.py", "tests/test_start_wrapper.py", "tests/test_start_stop_flow.py", "tests/fixtures/start_success.json"],
    "E4-S4": ["tests/test_start_stop_contract.py", "tests/fixtures/stop_idle.json", "tests/fixtures/stop_success.json"],
    "E4-S5": ["tests/test_status_contract.py", "tests/fixtures/status_idle.json", "tests/fixtures/status_active.json"],
    "E5-S1": ["src/meetingctl/transcription.py", "tests/test_transcription_runner.py"],
    "E5-S2": ["src/meetingctl/summary_parser.py", "src/meetingctl/summary_client.py", "tests/test_summary_parser.py", "tests/test_summary_client.py"],
    "E5-S3": ["src/meetingctl/process.py", "src/meetingctl/queue_worker.py", "tests/test_process_orchestrator.py", "tests/test_queue_worker.py", "tests/test_process_queue_cli.py"],
    "E5-S4": ["src/meetingctl/audio.py", "tests/test_audio_conversion.py"],
    "E6-S1": ["km/Meeting-Automation-Macros.kmmacros", "tests/test_km_macro_package.py"],
    "E6-S2": ["km/Meeting-Automation-Macros.kmmacros", "tests/test_km_macro_package.py"],
    "E6-S3": ["km/Meeting-Automation-Macros.kmmacros", "tests/test_km_macro_package.py"],
    "E6-S4": ["km/Meeting-Automation-Macros.kmmacros", "tests/test_km_macro_package.py"],
    "E6-S5": ["km/Meeting-Automation-Macros.kmmacros", "tests/test_km_macro_package.py"],
    "E7-S1": ["src/meetingctl/doctor.py", "tests/test_doctor_command.py", "tests/fixtures/doctor_ok.json", "tests/fixtures/doctor_missing_paths.json"],
}


def parse_changed_paths(status_text: str) -> list[str]:
    files: list[str] = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        payload = line[3:] if len(line) > 3 else line
        token = payload.split(" -> ")[-1].strip()
        path = Path(token)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and ".git" not in child.parts:
                    files.append(str(child))
        else:
            files.append(token)
    # dedupe while preserving stable order
    seen = set()
    ordered: list[str] = []
    for file in sorted(files):
        if file not in seen:
            ordered.append(file)
            seen.add(file)
    return ordered


def changed_files(status_file: str | None) -> list[str]:
    if status_file:
        return parse_changed_paths(Path(status_file).read_text())
    result = subprocess.run(
        ["git", "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_changed_paths(result.stdout)


def is_generated_or_derived(path: str) -> bool:
    non_story_prefixes = (
        "docs/",
        "scripts/",
        "skills/",
        "meetings/",
    )
    if path.startswith(non_story_prefixes):
        return True

    non_story_files = {
        ".gitignore",
        "obsidian_spec.md",
        "section18_clean.md",
        "setup-dev-environment.sh",
        "tests/test_story_commit_slicing_report.py",
        "src/meetingctl/__init__.py",
        "src/meetingctl/calendar/__init__.py",
        "src/meetingctl/note/__init__.py",
    }
    if path in non_story_files:
        return True

    generated_prefixes = (
        "src/meetingctl.egg-info/",
        "tests/__pycache__/",
        "src/meetingctl/__pycache__/",
        "src/meetingctl/calendar/__pycache__/",
        "src/meetingctl/note/__pycache__/",
    )
    if path.startswith(generated_prefixes):
        return True
    if path.endswith(".pyc"):
        return True
    return False


def build_report(files: list[str]) -> dict[str, object]:
    file_to_stories: dict[str, list[str]] = defaultdict(list)
    ignored_files: list[str] = []
    effective_files: list[str] = []
    for file in files:
        if is_generated_or_derived(file):
            ignored_files.append(file)
            continue
        effective_files.append(file)

    for story, prefixes in STORY_FILE_RULES.items():
        for file in effective_files:
            if any(file == prefix or file.startswith(prefix + "/") for prefix in prefixes):
                file_to_stories[file].append(story)

    report = {
        "total_changed_files": len(files),
        "ignored_files": ignored_files,
        "story_assignments": defaultdict(list),
        "unmapped_files": [],
        "conflicts": {},
    }

    for file in effective_files:
        stories = file_to_stories.get(file, [])
        if not stories:
            report["unmapped_files"].append(file)
            continue
        if len(stories) > 1:
            report["conflicts"][file] = stories
        for story in stories:
            report["story_assignments"][story].append(file)

    report["story_assignments"] = dict(report["story_assignments"])
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate story commit slicing report.")
    parser.add_argument(
        "--status-file",
        help="Path to a file containing `git status --short` output.",
    )
    parser.add_argument(
        "--write-json",
        default="docs/STORY_COMMIT_SLICING_REPORT.json",
        help="Output path for the JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = changed_files(args.status_file)
    report = build_report(files)
    out_path = Path(args.write_json)
    out_path.write_text(json.dumps(report, indent=2))

    print(f"Wrote {out_path}")
    print(f"Changed files: {report['total_changed_files']}")
    print(f"Ignored files: {len(report['ignored_files'])}")
    print(f"Unmapped files: {len(report['unmapped_files'])}")
    print(f"Conflicting files: {len(report['conflicts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
