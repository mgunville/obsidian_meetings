# Execution Plan

This plan layers sequencing and checkpoint control on top of `EPICS_AND_STORIES.md`.

## Planning Rules
- Build in dependency order; parallelize only when contracts are stable.
- Follow TDD and YAGNI per story.
- Do not start optional scope until all core v0.1 acceptance criteria are met.

## Sprint 0: Project Foundation
Duration: 1-2 days

### Stories
- E1-S1 Repo bootstrap
- E1-S2 CLI shell and command registry
- E1-S3 Config loader + env normalization

### Exit Criteria
- `meetingctl --help` works.
- Config validation errors are actionable.
- Base test harness is running in team environments.

### Handoffs
- Lane A publishes CLI command contracts and config object schema.

## Sprint 1: Calendar + Notes Core
Duration: 3-5 days

### Stories
- E2-S1 Event selection logic
- E2-S2 EventKit adapter
- E2-S3 JXA fallback adapter
- E2-S4 `meetingctl event --now-or-next --json`
- E3-S1 `meeting_id` + filename rules
- E3-S2 Template renderer

### Exit Criteria
- Calendar event resolution works through preferred backend with fallback.
- Note creation from resolved event works with deterministic naming.
- JSON event schema is locked for downstream lanes.

### Handoffs
- Lane B publishes canonical event JSON fixtures.
- Lane C publishes created note fixture contract (frontmatter + headings).

## Sprint 2: Recording Runtime Loop
Duration: 3-4 days

### Stories
- E4-S1 Runtime state store
- E4-S2 Audio Hijack control adapter
- E4-S3 `meetingctl start`
- E4-S4 `meetingctl stop`
- E4-S5 `meetingctl status --json`

### Exit Criteria
- Start/stop/status loop is stable.
- `status --json` contract is frozen for UX lane.
- Fallback behavior is visible in start output.

### Handoffs
- Lane D publishes status JSON fixture set:
  - idle
  - active recording
  - error/stale state

## Sprint 3: Processing Pipeline
Duration: 4-6 days

### Stories
- E3-S3 Safe-region patch engine
- E3-S4 `patch-note --dry-run`
- E5-S1 Transcription runner abstraction
- E5-S2 Summary client + parser
- E5-S3 Process orchestrator
- E5-S4 WAV->MP3 + retention
- E5-S5 Queue consumer real pipeline wiring

### Exit Criteria
- End-to-end process path works against fixtures and local smoke checks.
- Patching is idempotent and safe-region constrained.
- Immediate WAV deletion policy is enforced after MP3 success.
- `process-queue` executes real processing work (not log-only placeholder behavior).

### Handoffs
- Lane E publishes process result fixtures for UX messaging and regression use.

## Sprint 4: UX + Hardening + Release Readiness
Duration: 3-5 days

### Stories
- E6-S1 KM Start macro
- E6-S2 KM Stop macro
- E6-S3 KM Status macro
- E6-S4 KM Ad-hoc macro
- E6-S5 Optional auto-detect macro (disabled by default)
- E7-S1 `meetingctl doctor`
- E7-S2 setup script + install docs
- E7-S3 integration smoke tests

### Exit Criteria
- KM core macro package works on a fresh machine with documented setup.
- `meetingctl doctor` reports actionable diagnostics.
- Smoke tests and manual checklist are complete.

## Blocker Map
- E2-S4 blocked by E2-S1 + E2-S2.
- E4-S3 blocked by E2-S4 + E3-S2 + E4-S2.
- E5-S3 blocked by E3-S3 + E5-S1 + E5-S2.
- E5-S5 blocked by E5-S1 + E5-S2 + E5-S3 + E5-S4.
- E6-S1/E6-S2/E6-S3/E6-S4 blocked by E4 status/start/stop contracts.
- E7-S3 blocked by E5-S5 + E6-S2 + E7-S1.

## Tracking Model
- Track each story in one of: `todo`, `in_progress`, `blocked`, `review`, `done`.
- Limit WIP per lane to 2 stories max.
- Daily standup updates:
  - completed yesterday
  - in progress today
  - blockers + owner

## Minimal Reporting Template
- Sprint:
- Story:
- Owner:
- Status:
- Tests added:
- Risks:
- Blockers:
- Next action:

## Post-v0.1 Backlog
- [done] B1: EventKit helper hardening
  - package/install wiring for `scripts/eventkit_fetch.py`
  - doctor checks for helper presence/executability and EventKit runtime dependency
- [done] B2: JXA date normalization hardening
  - normalize Calendar.app date strings to strict ISO-8601 in adapter output
- [in_progress] B3: Real-machine integration smoke pass
  - validate Calendar permissions + Audio Hijack + KM macros on a clean macOS profile
- [done] B4: Process queue consumer worker
  - consume `process_queue.jsonl` and execute orchestration jobs safely
- [done] B7: Queue-to-pipeline production wiring
  - replace log-only queue handler with real `run_processing` execution path
  - add integration regression tests for queued success/failure outcomes
- [done] B5: Story-scoped commit slicing
  - Option A applied: baseline snapshot commit created, enabling clean story-scoped commits from this point forward
- [done] B6: Incremental workflow runner script
  - add `scripts/run-incremental-workflow.sh` to execute stepwise checks quickly
