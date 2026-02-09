# Epics and Stories

This backlog is sliced for independent parallel work with clear dependencies.

## Epic E1: Project Bootstrap and Core Contracts
Goal: establish executable skeleton and test harness.

### Story E1-S1: Repo bootstrap
- Deliverables: `pyproject.toml`, package skeleton, test runner config, lint config.
- Acceptance:
  - `pip install -e .[dev]` works.
  - `pytest` runs.
- Owner profile: platform engineer.

### Story E1-S2: CLI shell and command registry
- Deliverables: `meetingctl` base CLI with subcommands placeholders.
- Acceptance:
  - `meetingctl --help` and subcommand help work.
- Depends on: E1-S1.

### Story E1-S3: Config loader + env path normalization
- Deliverables: env loading, `~` expansion, required key checks.
- Acceptance:
  - missing keys return actionable errors.
  - normalized paths are absolute.
- Depends on: E1-S1.

## Epic E2: Calendar Event Resolution
Goal: reliable now-or-next event JSON for meeting start.

### Story E2-S1: Event selection logic (pure)
- Deliverables: deterministic selector for ongoing vs upcoming.
- Acceptance:
  - unit tests for edge windows and ties.
- Depends on: E1-S1.

### Story E2-S2: EventKit adapter (preferred backend)
- Deliverables: EventKit query wrapper contract.
- Acceptance:
  - returns normalized event schema.
  - errors include guidance.
- Depends on: E1-S2, E1-S3.

### Story E2-S3: JXA fallback adapter
- Deliverables: fallback backend with backend-specific error reporting.
- Acceptance:
  - activates when EventKit unavailable.
  - error output suggests `meetingctl doctor`.
- Depends on: E2-S2.

### Story E2-S4: `meetingctl event --now-or-next --json`
- Deliverables: wired command endpoint.
- Acceptance:
  - machine-readable JSON schema stable in tests.
- Depends on: E2-S1, E2-S2.

## Epic E3: Note Creation and Safe Patching
Goal: deterministic note creation and idempotent managed updates.

### Story E3-S1: `meeting_id` and filename rules
- Deliverables: ID generator + title sanitization.
- Acceptance:
  - deterministic tests and collision strategy.
- Depends on: E1-S1.

### Story E3-S2: Template renderer for meeting note
- Deliverables: render `templates/meeting.md` with frontmatter.
- Acceptance:
  - required keys present.
- Depends on: E3-S1, E1-S3.

### Story E3-S3: Safe-region patch engine
- Deliverables: sentinel-based patching + no outside mutation guarantee.
- Acceptance:
  - idempotent patch tests.
  - unmanaged text unchanged tests.
- Depends on: E3-S2.

### Story E3-S4: `patch-note --dry-run`
- Deliverables: preview mode output.
- Acceptance:
  - no write side effects.
- Depends on: E3-S3.

## Epic E4: Recording Control and Runtime State
Goal: predictable start/stop behavior with resilient state.

### Story E4-S1: runtime state store
- Deliverables: atomic state writes + stale state detection.
- Acceptance:
  - lock and stale-state tests.
- Depends on: E1-S3.

### Story E4-S2: Audio Hijack control adapter
- Deliverables: start/stop session controls by platform.
- Acceptance:
  - mock integration tests.
- Depends on: E4-S1.

### Story E4-S3: `meetingctl start` wrapper
- Deliverables: event resolve + note create + recording start.
- Acceptance:
  - returns JSON with fallback surfaced.
- Depends on: E2-S4, E3-S2, E4-S2.

### Story E4-S4: `meetingctl stop` wrapper
- Deliverables: stop + async-safe process trigger.
- Acceptance:
  - no active recording gives safe warning.
- Depends on: E4-S2.

### Story E4-S5: `meetingctl status --json`
- Deliverables: status contract for KM.
- Acceptance:
  - fields: recording, meeting_id, title, platform, duration_human, note_path.
- Depends on: E4-S1.

## Epic E5: Transcription, Summary, and Audio Conversion
Goal: post-stop processing pipeline.

### Story E5-S1: transcription runner abstraction
- Deliverables: local whisper invocation wrapper.
- Acceptance:
  - missing wav handled cleanly.
- Depends on: E4-S4.

### Story E5-S2: summary client + parser
- Deliverables: transcript-only summarization request and parser.
- Acceptance:
  - malformed JSON fails safely.
- Depends on: E5-S1.

### Story E5-S3: process orchestrator
- Deliverables: transcribe -> summarize -> patch.
- Acceptance:
  - idempotent rerun behavior.
- Depends on: E3-S3, E5-S1, E5-S2.

### Story E5-S4: WAV->MP3 and retention
- Deliverables: conversion + v0.1 immediate WAV deletion.
- Acceptance:
  - mp3 linked in note, wav removed after success.
- Depends on: E5-S3.

### Story E5-S5: queue consumer real pipeline wiring
- Deliverables: `meetingctl process-queue` executes the real process chain (transcribe -> summarize -> patch -> convert), not log-only placeholders.
- Acceptance:
  - queued stop payloads are transformed into `ProcessContext` and passed to `run_processing`.
  - successful jobs produce transcript/mp3/note mutations for the target meeting.
  - failures keep payloads queued with actionable failure reason.
  - integration tests cover one success and one failure path.
- Depends on: E5-S1, E5-S2, E5-S3, E5-S4.

## Epic E6: UX Layer (v0.1 subset)
Goal: reliable daily use through KM.

### Story E6-S1: KM Start macro
- Deliverables: macro calling `meetingctl start --json` with notifications.
- Acceptance:
  - fallback warning surfaced.
- Depends on: E4-S3.

### Story E6-S2: KM Stop macro
- Deliverables: macro calling `meetingctl stop` and processing notice.
- Acceptance:
  - immediate confirmation path.
- Depends on: E4-S4, E5-S5.

### Story E6-S3: KM Status macro
- Deliverables: status popup via `meetingctl status --json`.
- Acceptance:
  - idle and active states correct.
- Depends on: E4-S5.

### Story E6-S4: KM Ad-hoc macro
- Deliverables: prompt title + start ad-hoc recording.
- Acceptance:
  - note created without calendar dependency.
- Depends on: E4-S3.

### Story E6-S5: optional auto-detect macro (disabled by default)
- Deliverables: prompt on Zoom/Teams activation.
- Acceptance:
  - disabled by default in package.
- Depends on: E6-S1, E6-S2.

## Epic E7: Doctor, Hardening, and Release Prep
Goal: make installation and diagnostics repeatable.

### Story E7-S1: `meetingctl doctor`
- Deliverables: checks for paths, binaries, permissions hints.
- Acceptance:
  - JSON and human-readable outputs.
- Depends on: E1-S3, E2-S2, E4-S2.

### Story E7-S2: setup script and install doc
- Deliverables: `scripts/setup.sh`, developer setup docs.
- Acceptance:
  - fresh machine setup succeeds with documented steps.
- Depends on: E1-S1.

### Story E7-S3: integration smoke tests
- Deliverables: script/checklist for start-stop-process loop.
- Acceptance:
  - includes error-path checks.
- Depends on: E5-S5, E6-S2, E7-S1.
