# Setup and Dependencies

## 1) Repository Setup
- Clone repo.
- Create `.env` from `.env.example`.
  - default:
    - `cp .env.example .env`

## 2) Python Environment
- Required: Python 3.11+
- Create venv:
  - `python3.11 -m venv .venv`
  - `source .venv/bin/activate`
- Install:
  - `pip install -e .[dev]`

## 3) External Apps and Tools
Assumed installed:
- Keyboard Maestro
- Audio Hijack

Required:
- `ffmpeg` via Homebrew

Planned optional runtime dependencies:
- whisper.cpp or faster-whisper
- LLM provider SDK (only for summarization stories)
- Todoist API token (only for optional tasks stories)

## 4) macOS Permissions
Grant access for:
- Calendar
- Automation (KM controlling Audio Hijack)
- Microphone/system audio capture

Trigger Calendar permission request for the current runtime:
- `source .venv/bin/activate`
- `python scripts/eventkit_fetch.py --request-access`

## 5) Calendar Integration Runtime
- Preferred path: EventKit helper script `scripts/eventkit_fetch.py`.
  - Auto-used when present, or force with `MEETINGCTL_EVENTKIT_HELPER=/abs/path/to/eventkit_fetch.py`.
- Fallback path: JXA through `osascript`, optionally with `MEETINGCTL_JXA_SCRIPT=/abs/path/to/calendar_events.jxa`.
- For incremental workflow checks without Audio Hijack side effects:
  - `MEETINGCTL_RECORDING_DRY_RUN=1`

## 6) Verification
- `pytest`
- `meetingctl doctor` (once implemented)
- `bash scripts/smoke-test.sh`
