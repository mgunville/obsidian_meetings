# Meeting Capture & Notes Pipeline (MCNP)
Version: 0.2
Status: Product Spec + Architecture
Primary platform: macOS (Apple Silicon)
Storage: local-first (Obsidian vault, Markdown, WAV/MP3)
Orchestrator UX: Keyboard Maestro (KM)
Recording engine: Audio Hijack (Rogue Amoeba)
Transcription: Local Whisper (whisper.cpp or faster-whisper)
Summarization: LLM API (transcript-only outbound; no-training API usage)
Tasks (optional): Todoist (API, opt-in)

---

## 1. Problem Statement

Create a local-first workflow that:
- Starts a meeting recording (system/app audio + mic) with minimal friction.
- Transcribes audio locally.
- Generates meeting minutes, decisions, and action items via LLM using transcript text only.
- Updates the corresponding Obsidian meeting note (single-file workflow).
- Converts WAV to MP3 for archival.
- Works across multiple Macs by cloning a repo + minimal configuration.
- Avoids lock-in and preserves data portability.

---

## 2. Goals / Non-Goals

### 2.1 Goals
1. **One-keystroke UX on macOS**
   - Start meeting capture (create note + start recording).
   - Stop meeting capture (stop recording + transcribe + summarize + update note + convert audio).
2. **Correct association of audio/transcript/minutes with the right meeting note**
   - Use a generated `meeting_id` as the durable join key.
3. **Local-first storage**
   - Meeting note: Markdown in Obsidian vault.
   - Audio: stored under vault `recordings/` and excluded from Git.
4. **Privacy-sensitive**
   - Audio never leaves device.
   - Transcript may be sent to LLM APIs with no-training policy (configurable).
5. **Cloneable & reproducible**
   - Full solution in a single repo folder.
   - Per-machine configuration via `.env` + a small YAML config.
6. **TDD-first implementation**
   - Unit tests for parsing, note patching, ID generation, URL extraction, and pipeline stages.

### 2.2 Non-Goals (initial release)
- Perfect speaker diarization (may be a later enhancement).
- In-meeting real-time transcription.
- iOS recording automation (can be added later as an inbox uploader).
- Advanced audio retention windows (v0.1 keeps policy simple).

---

## 3. User Personas & UX

### 3.1 Primary user
- Uses Obsidian daily.
- Wants minimal clicks/decisions.
- Works mostly on macOS, sometimes mobile.
- Uses Teams primarily, with occasional Zoom/Google Meet.

### 3.2 UX (Keyboard Maestro)
- Hotkey: **Start Meeting**
  - Find current/next meeting (within N minutes).
  - Create/open Obsidian meeting note from a template.
  - Start Audio Hijack session based on platform (Teams/Zoom/Browser).
  - If platform cannot be inferred, show explicit fallback message and use `System+Mic`.
- Hotkey: **Stop Meeting**
  - Stop Audio Hijack.
  - Run processing pipeline and update note.
  - Notify when complete (or on error).

Optional:
- Macro palette to pick session override (Teams/Zoom/Browser/System).

---

## 4. Functional Requirements

### 4.1 Meeting discovery
- Determine the active meeting:
  - If an event is currently ongoing: select it.
  - Else select the next event starting within configurable window (default 5 minutes).
- Extract:
  - title, start/end, location, notes, calendar name
  - join link (Teams/Zoom/Meet/Webex) if present in notes/location/url
- On calendar query failure:
  - Return clear, actionable error.
  - Report backend used (EventKit or JXA).
  - Suggest `meetingctl doctor` and permission checks.

Rationale: Meeting links may move; pipeline should still work without one.

### 4.2 Note creation
- Create a meeting note file in the correct Obsidian folder (based on user rules).
- Populate from a markdown template with placeholders.
- Insert frontmatter keys including:
  - `type: meeting`
  - `meeting_id`
  - `start`, `end`, `title`
  - `platform` (inferred if possible)
  - `recording_wav`, `recording_mp3`
  - `transcript_status` (`pending|done|error`)
  - `summary_status` (`pending|done|error`)
- Must support existing vault structure:
  - `~/Notes/notes-vault/work/<firm>/Clients/...`
- Client association strategy:
  - Rule-based mapping from event title keywords to client folder, OR
  - Prompt-driven selection on Start Meeting, OR
  - Default folder if unknown.

### 4.3 Recording
- Must record other participants + mic.
- Prefer app-specific capture:
  - Teams app + mic
  - Zoom app + mic
  - Browser audio + mic (Google Meet)
  - fallback: system audio + mic
- Save WAV initially for transcription quality.
- Produce deterministic file naming including `meeting_id`:
  - `YYYY-MM-DD HHmm - <Normalized Title> - <meeting_id>.wav`

### 4.4 Transcription (local)
- Local Whisper transcription (no audio upload).
- Produce transcript text (markdown; timestamps optional).
- Store transcript content inside meeting note under `## Transcript`.
- Model choice configurable (speed vs accuracy).

### 4.5 Minutes / action items (LLM transcript-only)
- Send transcript text (optionally redacted in v1) to LLM API.
- Receive:
  - Summary/minutes
  - Decisions
  - Action items (structured JSON + human markdown list)
- Insert into meeting note under:
  - `## Minutes`
  - `## Decisions`
  - `## Action items`

### 4.6 Task creation (optional)
- Todoist integration is opt-in for v0.1.
- If enabled, create tasks from action items.
- Include link back to meeting note (obsidian URI or relative path).
- Storing Todoist task IDs is optional and deferred unless needed for update flows.

### 4.7 Audio archival
- Convert WAV -> MP3 after successful transcription (optionally after summary).
- Update note with MP3 link.
- v0.1 policy: delete WAV immediately after successful MP3 creation.
- Future enhancement: configurable retention window (keep WAV for N days).

### 4.8 Logging & observability
- Write logs to `./logs/meetingctl.log` and optionally to macOS Console.
- Provide `meetingctl doctor` command to validate environment.

---

## 5. Non-Functional Requirements

- **Portability:** repo clone + `.env` + permission grants.
- **Reliability:** avoid fragile UI automation where possible.
- **Security:**
  - All secrets in `.env` (never committed).
  - `.gitignore` includes `.env`, recordings, logs, caches.
  - Do not store transcript in external services beyond API call unless configured.
- **Performance:** transcription should run efficiently on Apple Silicon.
- **Maintainability:** TDD, modular components, clear interfaces.
- **Compliance:** recording notification is user responsibility; policy must be documented.

---

## 6. Architecture Overview

### 6.1 High-level components

1. **Keyboard Maestro macros (UX/orchestration)**
   - Start Meeting
   - Stop Meeting
   - Ad-hoc Recording
   - Recovery/Process Last

2. **`meetingctl` CLI (repo-based core)**
   - `meetingctl start` -> convenience wrapper (`event` + `note create` + `record start`)
   - `meetingctl stop` -> convenience wrapper (`record stop` + `process --last`)
   - `meetingctl status --json` -> current recording state for UX surfaces
   - `meetingctl event` -> JSON event descriptor
   - `meetingctl note create` -> writes markdown note from template
   - `meetingctl record start/stop` -> controls Audio Hijack sessions
   - `meetingctl transcribe` -> local whisper transcription
   - `meetingctl summarize` -> calls LLM APIs, returns structured output
   - `meetingctl patch-note` -> idempotent note updates
   - `meetingctl patch-note --dry-run` -> preview patch without writing
   - `meetingctl convert-audio` -> wav->mp3
   - `meetingctl process` -> end-to-end pipeline for a meeting_id
   - `meetingctl doctor` -> env validation

3. **Audio Hijack sessions**
   - Preconfigured sessions:
     - `Teams+Mic`
     - `Zoom+Mic`
     - `Browser+Mic`
     - `System+Mic` (fallback)
   - Output path and filename controlled by scripts (or post-stop rename).

4. **External tools**
   - `ffmpeg` for conversion
   - `whisper.cpp` or `faster-whisper` for transcription

5. **Optional integrations**
   - Todoist REST API

### 6.2 Data flow (Start -> Stop)

**Start Meeting**
1. KM triggers `meetingctl start --window-minutes 5`
2. `meetingctl start` resolves event, creates note, starts recording, and writes state.

**Stop Meeting**
1. KM triggers `meetingctl stop`
2. `meetingctl stop` stops recording and runs processing from saved state.

---

## 7. Key Design Considerations

### 7.1 Meeting association strategy
- Use generated `meeting_id` as durable join key.
- Store `meeting_id` in:
  - note frontmatter
  - recording filename
  - processing metadata
- Never rely solely on title/time matching.

### 7.2 Avoiding Obsidian plugin coupling
- Do not depend on Templater for orchestration.
- Use template files in repo (Jinja2/Mustache-style).
- Optional compatibility with older templates is allowed, but rendering lives in `meetingctl`.

### 7.3 Calendar querying reliability
Preferred: EventKit helper (Swift binary) for structured access.

Policy:
- EventKit helper is recommended and preferred.
- JXA/AppleScript is fallback only when EventKit helper is unavailable.
- JXA path is best-effort and may vary across macOS versions.
- Any calendar query failure must include:
  - backend used (EventKit or JXA)
  - likely failure reason (permissions/helper missing/no match)
  - next step: run `meetingctl doctor`

### 7.4 Platform detection
- Extract URL from any of: `url`, `location`, `notes`.
- Infer platform by domain:
  - `teams.microsoft.com` -> teams
  - `zoom.us` -> zoom
  - `meet.google.com` -> meet (browser)
  - `webex.com` -> webex (browser/system)
- If unknown: fallback session defaults to `System+Mic` (configurable).

### 7.5 Note patching and safe regions
- Patching must be idempotent.
- Patcher updates frontmatter keys and managed sections only.
- Managed sections are defined by sentinel markers:
  - `<!-- MINUTES_START -->` / `<!-- MINUTES_END -->`
  - `<!-- DECISIONS_START -->` / `<!-- DECISIONS_END -->`
  - `<!-- ACTION_ITEMS_START -->` / `<!-- ACTION_ITEMS_END -->`
  - `<!-- TRANSCRIPT_START -->` / `<!-- TRANSCRIPT_END -->`
- `patch-note` must never mutate content outside these sentinels.
- `patch-note --dry-run` must output proposed changes without writing file.

### 7.6 Permissions
- Calendar access for EventKit/JXA.
- Automation access for controlling Audio Hijack.
- Microphone/system audio permissions for Audio Hijack + macOS.
- `doctor` flow must guide user through missing permissions.

### 7.7 Runtime state reliability
- `meetingctl start` writes state to `~/.local/state/meetingctl/current.json`.
- State writes are atomic (temp file + rename).
- Locking prevents concurrent `start` commands from clobbering state.
- Stale-state detection must provide recover/clear guidance.

---

## 8. Repository Layout (cloneable solution)

```
meeting-capture-pipeline/
  README.md
  PRODUCT_SPEC.md
  .gitignore
  .env.example
  pyproject.toml (or package.json)
  src/
    meetingctl/
      __init__.py
      cli.py
      config.py
      calendar/
        eventkit_client.swift
        eventkit_wrapper.py
        jxa_client.js
      note/
        template.md
        renderer.py
        patcher.py
        frontmatter.py
      record/
        audio_hijack.scpt
        hijack_control.py
      transcribe/
        whisper_runner.py
        formats.py
      summarize/
        llm_client.py
        prompts/
          minutes_prompt.md
        schema.py
      tasks/
        todoist.py
      audio/
        convert.py
      util/
        logging.py
        paths.py
        text.py
  scripts/
    install_deps.sh
    setup.sh
  km/
    KeyboardMaestroMacros.kmmacros
  tests/
    test_event_selection.py
    test_url_extraction.py
    test_note_template_render.py
    test_note_patch_idempotent.py
    test_filename_sanitization.py
    test_transcribe_stub.py
    test_summarize_stub.py
  templates/
    meeting.md
  logs/ (gitignored)
  recordings/ (gitignored; may live inside vault)
```

Language recommendation:
- Python for `meetingctl` (fast iteration, testing).
- Swift helper for EventKit (recommended).

---

## 9. Configuration & Secrets

### 9.1 `.env` (required, not committed)
Store:
- `VAULT_PATH=~/Notes/notes-vault`
- `FIRM_NAME=AHEAD` (optional)
- `DEFAULT_MEETINGS_FOLDER=work/AHEAD/Events/Meetings`
- `RECORDINGS_PATH=~/Notes/notes-vault/recordings/Work`
- `WHISPER_ENGINE=whispercpp|fasterwhisper`
- `WHISPER_MODEL=base|small|medium`
- `FFMPEG_PATH=/opt/homebrew/bin/ffmpeg` (if needed)
- `LLM_PROVIDER=openai|anthropic|google`
- `OPENAI_API_KEY=...` / `ANTHROPIC_API_KEY=...`
- `TODOIST_ENABLED=false` (default)
- `TODOIST_API_TOKEN=...` (optional)
- `AUDIO_HIJACK_SESSION_TEAMS=Teams+Mic`
- `AUDIO_HIJACK_SESSION_ZOOM=Zoom+Mic`
- `AUDIO_HIJACK_SESSION_BROWSER=Browser+Mic`
- `AUDIO_HIJACK_SESSION_FALLBACK=System+Mic`

Path handling rule:
- Expand `~` and env vars at runtime, then normalize to absolute paths.
- `meetingctl doctor` validates expanded paths.

### 9.2 `.env.example`
- Include all keys with blanks and comments.

### 9.3 `.gitignore`
Must include:
- `.env`
- `logs/`
- `**/*.wav`, `**/*.mp3`
- caches/models
- local config overrides

---

## 10. Build Plan (TDD-first)

### Phase 0: Spike & decisions (1-2 days)
- Confirm Audio Hijack AppleScript controls.
- Decide transcription engine:
  - `whisper.cpp` easiest deployment
  - `faster-whisper` may be faster but adds Python deps

Deliverables:
- AppleScript proof: start/stop known session
- WAV output to known folder

### Phase 1: CLI skeleton + config + logging
- Implement `meetingctl` CLI and `start`/`stop` wrappers.
- Load `.env` and validate required keys.
- Implement `meetingctl doctor`.

Tests:
- config loading
- missing env keys -> helpful errors
- path expansion behavior

### Phase 2: Calendar event query -> JSON
- Implement EventKit helper path + JXA fallback.
- `meetingctl event --now-or-next 5 --json`

Tests:
- selection logic: ongoing beats upcoming
- time window selection
- stable JSON schema
- failure messaging includes backend + doctor guidance

### Phase 3: URL extraction + platform inference
- Extract relevant join URL from location/notes/url.
- Infer platform.

Tests:
- Teams/Zoom/Meet/Webex URLs
- multiple URLs present
- none present -> fallback

### Phase 4: Note creation via template rendering
- Render `templates/meeting.md` from event JSON + `meeting_id`.
- Write note to vault path per routing rule.

Tests:
- filename sanitization
- template frontmatter keys
- deterministic `meeting_id` insertion

### Phase 5: Recording start/stop
- `meetingctl record start --meeting-id ... --platform ...`
- `meetingctl record stop`
- ensure expected file exists

Tests:
- mock AppleScript wrapper calls
- one-machine manual integration test

### Phase 6: Transcription pipeline
- `meetingctl transcribe --wav path --out transcript.md`
- insert transcript into note managed section

Tests:
- transcript insertion idempotent
- missing wav handled gracefully

### Phase 7: Summarization + safe patching
- Parse summarization output:
  - minutes markdown
  - decisions list
  - action items list
  - optional JSON block for task creation
- Patch note using safe-region sentinels only.
- Add `patch-note --dry-run`.

Tests:
- patch idempotency
- malformed JSON fail-safe behavior
- dry-run deterministic output
- unmanaged note text unchanged

### Phase 8: WAV -> MP3 conversion
- `meetingctl convert-audio`
- update note with MP3 link
- v0.1 immediate WAV deletion after successful MP3

Tests:
- conversion command generation
- immediate-delete policy

### Phase 9: Optional Todoist integration
- create tasks from action item JSON when enabled
- include meeting note link in task body

Tests:
- API request formation
- rate-limit/backoff stubs

### Phase 10: Keyboard Maestro integration
- provide exported macros
- macros call `meetingctl start` and `meetingctl stop`
- document permission prompts

Deliverables:
- `km/KeyboardMaestroMacros.kmmacros`
- setup + quick-start docs in README

### Phase 11: UX integration layer (v0.1 scope)
- add core KM macros:
  - Start Meeting
  - Stop Meeting
  - Recording Status
  - Ad-hoc Recording
- use `meetingctl status --json` as single status contract for KM.
- add notification strategy for start/stop/error with actionable messages.
- optional (disabled by default): auto-detect prompt on Zoom/Teams activation.

Deliverables:
- `km/Meeting-Automation-Macros.kmmacros`
- `docs/HOTKEYS.md`
- `docs/UI-QUICKSTART.md`

---

## 11. Test Plan

### 11.1 Unit tests (automated, CI-ready)
- event selection logic
- URL extraction and platform inference
- filename/path sanitization
- template rendering
- safe-region note patching (idempotency + preservation)
- summarization parsing + schema validation
- audio conversion command generation

### 11.2 Integration tests (manual checklist)
Run on each new Mac after cloning:
1. `meetingctl doctor` passes.
2. Start Meeting:
   - note created
   - Audio Hijack starts correct source
   - fallback warning appears when platform unknown
3. Stop Meeting:
   - recording stops
   - transcript inserted
   - minutes/action items inserted
   - mp3 created and linked
   - wav deleted on success
4. Failure paths:
   - summarize failure sets `summary_status: error`
   - transcribe failure sets `transcript_status: error`
   - rerun `meetingctl process --meeting-id ...` is safe

### 11.3 Regression tests
- fixture transcripts keep summarizer parsing stable
- fixture notes keep patching idempotent

### 11.4 TDD enforcement
- new modules ship with tests first or alongside
- PR checklist:
  - tests added/updated
  - `pytest` green
  - linting/formatting applied
  - secrets not committed

---

## 12. Security & Privacy

- Audio stays local.
- Transcript-only outbound to LLM APIs.
- `.env` contains all credentials and is gitignored.
- Logs do not include full transcript by default.
- Redaction (PII scrub before LLM call) is a v1 feature:
  - phone numbers
  - email addresses
- README must include a privacy section with explicit data flow.

---

## 13. Deployment & Setup

### 13.1 Dependencies
- Audio Hijack installed and sessions created/named.
- `ffmpeg` installed (Homebrew).
- Whisper engine installed:
  - whisper.cpp binary or faster-whisper dependencies
- Python 3.11+ recommended.

### 13.2 Setup steps (per machine)
1. Clone repo.
2. Run `scripts/setup.sh` (preferred).
3. If needed, copy `.env.example` -> `.env` and fill values.
4. If needed, run `scripts/install_deps.sh`.
5. Grant permissions:
   - Calendar
   - Automation (KM -> Audio Hijack)
   - Microphone/system audio
6. Import KM macros.
7. Run `meetingctl doctor`.

### 13.3 Quick-start docs requirements
- README includes a "10-minute quick start".
- Include screenshots for:
  - KM Start/Stop macro setup
  - Audio Hijack session layouts
  - expected `meetingctl doctor` success output

---

## 14. Open Questions / Decisions Needed

1. Note routing rules: client mapping vs prompt vs hybrid.
2. Template format migration from existing Templater snippets.
3. Stop behavior: manual stop only vs optional auto-stop at event end.
4. Task system of record: Todoist vs Reminders.

---

## 15. Acceptance Criteria (Definition of Done)

- Start Meeting hotkey:
  - creates note in vault
  - starts recording with filename containing `meeting_id`
- Stop Meeting hotkey:
  - stops recording
  - produces transcript locally
  - calls LLM summarizer with transcript only
  - patches the same note with minutes/decisions/action items/transcript
  - converts WAV -> MP3 and links it
  - deletes WAV after successful MP3 (v0.1 behavior)
- Safe patching:
  - only sentinel-defined regions are modified
  - `patch-note --dry-run` previews changes without writing
- Failure handling:
  - failed transcription/summarization sets status fields to `error`
  - rerunning `meetingctl process --meeting-id ...` is idempotent
- UX behavior:
  - Start/Stop hotkeys provide immediate notification feedback
  - fallback to `System+Mic` is explicitly surfaced in notification text
  - `meetingctl status --json` accurately reflects idle vs recording state
- Cross-machine reproducibility:
  - second Mac works after `.env` update + permissions grants
  - no code changes required

---

## 16. Appendix: Note Template (example)

`templates/meeting.md`:

```markdown
---
type: meeting
meeting_id: "{{ meeting_id }}"
title: "{{ title }}"
start: "{{ start_iso }}"
end: "{{ end_iso }}"
calendar: "{{ calendar_name }}"
platform: "{{ platform }}"
join_url: "{{ join_url }}"
recording_wav: "{{ recording_wav_rel }}"
recording_mp3: ""
transcript_status: "pending"
summary_status: "pending"
---

# {{ title }}

## Context
- When: {{ start_human }} - {{ end_human }}
- Platform: {{ platform }}
- Join: {{ join_url }}

## Notes

## Minutes
<!-- MINUTES_START -->
> _Pending_
<!-- MINUTES_END -->

## Decisions
<!-- DECISIONS_START -->
> _Pending_
<!-- DECISIONS_END -->

## Action items
<!-- ACTION_ITEMS_START -->
> _Pending_
<!-- ACTION_ITEMS_END -->

## Transcript
<!-- TRANSCRIPT_START -->
> _Pending_
<!-- TRANSCRIPT_END -->
```

## 17. Appendix: Suggested KM Macro Interface

Start Meeting:
- Executes: `meetingctl start --window-minutes 5`

Stop Meeting:
- Executes: `meetingctl stop`

Ad-hoc:
- Executes: `meetingctl start --adhoc --title "..."`

Implementation detail:
- `meetingctl start` writes state to:
  - `~/.local/state/meetingctl/current.json`
- state includes:
  - `meeting_id`, `note_path`, `wav_path`, `session_name`, `started_at`
- `meetingctl stop` / `meetingctl process --last` read this state safely.

## 18. Implementation Checklist (Critical Path)

1. Project bootstrap
- Initialize `meetingctl` package and CLI skeleton.
- Add `.env` loading, path expansion, and config validation.
- Implement `meetingctl doctor` with actionable diagnostics.

2. Calendar + event selection
- Build EventKit helper path first.
- Add JXA fallback path with backend-aware errors.
- Implement active-meeting selection (`ongoing` then `upcoming window`).

3. Note creation and IDs
- Implement `meeting_id` generation and deterministic filenames.
- Render `templates/meeting.md` into target vault folder.
- Persist initial frontmatter/status fields.

4. Recording control
- Implement Audio Hijack control for session start/stop.
- Add platform inference and explicit `System+Mic` fallback messaging.
- Verify WAV output path and naming include `meeting_id`.

5. Transcription and safe patching
- Run local Whisper against WAV and parse output.
- Implement safe-region patcher with strict sentinel boundaries.
- Add `patch-note --dry-run` preview mode.

6. Summarization pipeline
- Send transcript-only payload to selected LLM provider.
- Parse minutes, decisions, action items, and optional task JSON.
- Patch note managed sections and status fields idempotently.

7. Audio conversion and retention
- Convert WAV to MP3 and patch note link.
- Apply v0.1 retention policy (delete WAV immediately on success).
- Ensure reruns are safe and do not duplicate links/content.

8. Optional tasks module
- Gate Todoist integration behind opt-in config.
- Create tasks with backlink to meeting note.
- Keep task ID persistence optional.

9. KM integration and docs
- Wire KM Start/Stop macros to `meetingctl start`/`meetingctl stop`.
- Add setup docs and quick-start screenshots.
- Document privacy/data-flow and recording responsibility.

10. Test and hardening pass
- Complete unit tests for selection, parsing, rendering, patching, conversion.
- Run manual integration checklist on at least one Mac.
- Validate failure paths and recovery/idempotent reruns.

11. UX layer completion
- Ship KM macro package with default hotkeys and conflict notes.
- Validate start/stop/status/adhoc UX flows end-to-end.
- Keep auto-detect macro optional and disabled by default.

## 19. UI/UX Integration Layer (v0.1 Decision)

This spec adopts a trimmed subset of the proposed UX expansion to keep v0.1 simple and reliable.

### 19.1 Adopted in v0.1
- Keyboard Maestro is the primary UX layer.
- Four core macros are in scope:
  - Start Meeting (`meetingctl start --window-minutes 5`)
  - Stop Meeting (`meetingctl stop`)
  - Recording Status (`meetingctl status --json`)
  - Ad-hoc Recording (`meetingctl start --adhoc --title "..."`)
- Notification principles:
  - immediate feedback on start/stop/error
  - explicit fallback warning when `System+Mic` is used
  - actionable failure hints ("Run `meetingctl doctor`", "View logs")
- Optional auto-detect flow:
  - trigger on Zoom/Teams activation
  - prompt user to record
  - disabled by default

### 19.2 Deferred to post-v0.1
- Alfred workflow package
- Raycast extension
- menu bar indicator/SwiftBar integration
- BetterTouchTool and Stream Deck presets
- advanced notification actions requiring extra dependencies

### 19.3 Required CLI support for UX
- `meetingctl status --json` output includes:
  - `recording` (boolean)
  - `meeting_id`
  - `title`
  - `platform`
  - `duration_human`
  - `note_path`
- start/stop commands must return machine-readable JSON when requested (`--json`) for KM parsing.

### 19.4 UX Documentation Deliverables
- `docs/UI-QUICKSTART.md`: install/import/test in under 10 minutes
- `docs/HOTKEYS.md`: default hotkeys and how to customize
- README section "UI Quick Start" linking to above docs

End of spec.
