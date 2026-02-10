# Gap Task List (2026-02-10)

Source: code/documentation review findings in this repository.

## P0: Prevent ad-hoc recordings from generating unprocessable queue jobs

- Problem:
  - `meetingctl start --title ...` can save empty `note_path` when `--note-path` is omitted.
  - `meetingctl stop` then enqueues payloads that fail in `process-queue` because `note_path` is required.
- Scope:
  - Update ad-hoc start flow to guarantee a valid note path.
  - Option A: require `--note-path` when `--title` is used.
  - Option B (preferred): auto-create an ad-hoc note when `--note-path` is missing.
  - Keep JSON contract stable or version any intentional contract change.
- Tests to add/update:
  - CLI test for ad-hoc `start` without `--note-path` followed by `stop` and successful queue processing prechecks.
  - Macro-level regression to ensure E6-S4 ad-hoc macro still works end-to-end.
- Acceptance criteria:
  - No queue payload is emitted with empty `note_path`.
  - `process-queue` does not fail for the standard ad-hoc macro path.

## P0: Resolve WAV fallback mismatch between code and docs

- Problem:
  - Docs/release audit claim fallback to newest `*.wav`.
  - Code currently requires `<meeting_id>.wav` (or explicit `wav_path`) and fails otherwise.
- Decision required:
  - Option A: implement fallback-to-newest-WAV behavior.
  - Option B: keep strict behavior and correct docs/audit language.
- Scope:
  - Align implementation, tests, and docs to one behavior.
- Tests to add/update:
  - If Option A: add success test when only non-`meeting_id` WAV exists.
  - If Option B: keep failure test and ensure docs explicitly describe strict naming.
- Acceptance criteria:
  - Zero contradictions between runtime behavior and repository documentation.

## P1: Make installer match stated Python support policy

- Problem:
  - Docs state Python `3.11+`, but `install.sh` hard-requires the `python3.11` binary name.
- Scope:
  - Use `python3` detection and explicit version check (`>=3.11`).
  - Preserve existing setup behavior (`venv`, `pip install -r requirements.txt`, `.env` bootstrap).
- Tests/validation:
  - Script sanity check on hosts with Python 3.12+ only.
  - Confirm output still provides the same next-step commands.
- Acceptance criteria:
  - Installer works on supported Python versions regardless of minor version binary naming.

## P1: Harden Anthropic response parsing in summary client

- Problem:
  - `summary_client` assumes `response.content[0].text` exists and is text.
- Scope:
  - Add defensive extraction logic for unexpected/empty content blocks.
  - Raise actionable error messages before parser invocation.
- Tests to add/update:
  - Empty content response.
  - Non-text first block.
  - Mixed blocks with text present.
- Acceptance criteria:
  - Failures are deterministic and actionable for malformed/unexpected API responses.

## Cross-cutting follow-ups

- Add a short “Known Behavior” section to setup docs for queue WAV resolution and ad-hoc note path behavior.
- Re-run and capture:
  - unit tests
  - `scripts/smoke-test.sh` (local mode)
  - `scripts/run-incremental-workflow.sh` (local mode)
- Update release audit after behavior/docs are aligned.

## Backlog Candidate: Calendar-Assisted Backfill Mapping for Legacy Recordings

Status:
- MVP implemented via `meetingctl backfill --match-calendar [--window-minutes N] [--dry-run] [--rename]`.
- Next increment should add stronger confidence scoring + explicit event identifiers in logs.

- Goal:
  - For prior recordings, infer meeting time from either:
    - filename token (`yyyymmdd_hhmm`), or
    - file creation/modified timestamp.
  - Use inferred time to query calendar events in a narrow window and map recording -> event.
  - Rename artifacts and generated notes to canonical `meeting_id` + title naming.
- Why:
  - Reduces manual association work when importing historical recordings.
- Proposed MVP:
  - Add `meetingctl backfill --match-calendar --window-minutes 30 --rename`.
  - Matching strategy:
    - parse filename timestamp first
    - fallback to filesystem timestamp
    - resolve nearest event via existing calendar service
    - require confidence threshold; otherwise leave unmapped and report.
- Risks:
  - ambiguous matches in dense calendars
  - timezone mismatches in legacy filenames
  - rename safety/idempotency concerns
