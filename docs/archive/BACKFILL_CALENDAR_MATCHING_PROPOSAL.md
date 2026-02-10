# Backfill Calendar Matching Proposal

## Objective
- Automatically associate historical recordings with calendar events and normalize artifact naming.

## Timestamp Inference Order
1. Parse filename pattern: `yyyymmdd_hhmm` (for example, `20260208_1015-retro.wav`).
2. Fallback to filesystem timestamp (`st_ctime` where reliable; otherwise `st_mtime`).

## Matching Flow
1. Infer candidate timestamp in local timezone.
2. Query now-or-nearby events using a configurable window (default `+/-30m`).
3. Select best candidate:
   - ongoing event at timestamp, else
   - nearest start time within window.
4. If exactly one high-confidence candidate exists:
   - generate note from event metadata
   - rename recording/transcript/mp3 to canonical meeting ID form.
5. If no clear match:
   - keep original filenames
   - generate an ad-hoc note
   - emit report entry for manual triage.

## Suggested CLI Additions
- Implemented:
  - `meetingctl backfill --match-calendar`
  - `meetingctl backfill --window-minutes 30`
  - `meetingctl backfill --rename`
  - `meetingctl backfill --dry-run`

## Safety Constraints
- Rename only within `RECORDINGS_PATH`.
- Never overwrite existing files.
- Persist a JSONL migration log (`old_path`, `new_path`, match confidence, event id/title).
- Dry-run must output the exact planned changes.
