# UI Quick Start Guide

Version: 0.1
Platform: macOS with Keyboard Maestro

## Overview

The Meeting Automation system provides one-keystroke UX for:
- Starting meeting recordings
- Stopping recordings and triggering processing
- Checking recording status
- Starting ad-hoc recordings without calendar events

## Installation

### Prerequisites

1. **Keyboard Maestro** (required)
   - Download from [keyboardmaestro.com](https://www.keyboardmaestro.com)
   - Version 9.0 or later recommended

2. **meetingctl CLI** (required)
   - Must be installed and configured
   - See `README.md` for installation steps

3. **Python virtual environment** (required)
   - Create at `~/.venv-meetingctl/`
   - Install meetingctl in this venv

### Setup Steps

1. **Install meetingctl**
   ```bash
   python3.11 -m venv ~/.venv-meetingctl
   source ~/.venv-meetingctl/bin/activate
   cd /path/to/obsidian_meetings
   pip install -e .
   ```

2. **Import Keyboard Maestro macros**
   - Double-click `config/km/Meeting-Automation-Macros.kmmacros`
   - This imports the "Meeting Automation" macro group
   - All macros are enabled by default except "Auto-detect"

3. **Verify installation**
   ```bash
   source ~/.venv-meetingctl/bin/activate
   meetingctl --help
   meetingctl status --json
   ```

4. **Configure hotkeys** (optional)
   - Open Keyboard Maestro Editor
   - Navigate to "Meeting Automation" group
   - Customize hotkey assignments (see HOTKEYS.md)

## Basic Usage

### Starting a Meeting Recording

**Default hotkey:** `⌃⌘S` (Control+Command+S)

1. Press the hotkey when you're ready to start recording
2. The system will:
   - Start Audio Hijack recording session
   - Show notification confirming start
   - Display warning if platform fallback was used
3. Recording runs in background until stopped

**What gets recorded:**
- System audio (meeting audio from Zoom/Teams/Meet/etc.)
- Microphone input
- Combined into single WAV file

### Stopping a Meeting Recording

**Default hotkey:** `⌃⌘⇧S` (Control+Command+Shift+S)

1. Press the hotkey when meeting ends
2. The system will:
   - Stop Audio Hijack recording
   - Queue post-processing (transcription, summary, conversion)
   - Show confirmation notification
3. Processing happens asynchronously in background

**Note:** If no recording is active, you'll see a warning notification.

### Checking Recording Status

**Default hotkey:** `⌃⌥S` (Control+Option+S)

1. Press the hotkey anytime
2. Notification shows:
   - **If recording:** Title, platform, duration
   - **If idle:** "No active recording"

### Ad-hoc Recording (No Calendar Event)

**Default hotkey:** `⌃⌘⌥S` (Control+Command+Option+S)

1. Press the hotkey
2. (Optional) set `AdHocTitle` variable in Keyboard Maestro beforehand
3. Recording starts with Browser+Mic session (`meet` platform)
4. No calendar event required

**Use case:** Impromptu meetings, phone calls, brainstorming sessions

## Notifications

### Success Notifications

- **Recording Started:** Green checkmark, shows title and platform
- **Recording Stopped:** Stop icon, confirms processing triggered
- **Status (Active):** Red circle, shows duration
- **Status (Idle):** White circle, "No active recording"

### Warning Notifications

- **Fallback Used:** Yellow warning icon
  - Platform detection failed
  - Using Browser+Mic session instead
  - Recording still works, but platform is generic
- **No Active Recording:** When stop is pressed without active recording

## Troubleshooting

### Macro doesn't run

1. **Check Keyboard Maestro is running**
   - Should have icon in menu bar
   - Macros only work when KM is running

2. **Verify hotkey isn't conflicting**
   - System Preferences > Keyboard > Shortcuts
   - Look for conflicts with system shortcuts

3. **Check permissions**
   - System Preferences > Security & Privacy > Privacy
   - Keyboard Maestro needs Accessibility permission

### "Command not found" error

1. **Check virtual environment path**
   - Macros expect `~/.venv-meetingctl/`
   - If different, edit shell script actions in KM Editor

2. **Verify meetingctl is installed**
   ```bash
   source ~/.venv-meetingctl/bin/activate
   which meetingctl
   meetingctl --help
   ```

### Recording doesn't start

1. **Check Audio Hijack**
   - Must be installed and running
   - Required sessions must exist (Teams+Mic, Zoom+Mic, etc.)
   - See Audio Hijack setup in README.md

2. **Run doctor command**
   ```bash
   source ~/.venv-meetingctl/bin/activate
   meetingctl doctor
   ```

### No notifications appear

1. **Check Do Not Disturb**
   - System Preferences > Notifications
   - Ensure DND is off or KM is allowed

2. **Check Keyboard Maestro notification settings**
   - System Preferences > Notifications > Keyboard Maestro Engine
   - Set to "Alerts" not "Banners"

## Advanced Features

### Auto-detect (Optional, Disabled by Default)

The auto-detect macro can prompt you to start recording when Zoom or Teams activates.

**To enable:**
1. Open Keyboard Maestro Editor
2. Navigate to "Meeting Automation" group
3. Find "Auto-detect Meeting (DISABLED)" macro
4. Check the "Enabled" checkbox

**Warning:** This can be disruptive if you open Zoom/Teams for non-meeting purposes.

### Customizing Virtual Environment Path

If you use a different venv path:

1. Open Keyboard Maestro Editor
2. Edit each macro's shell script action
3. Change `~/.venv-meetingctl/` to your path
4. Save changes

## Next Steps

- Customize hotkeys: See `HOTKEYS.md`
- Setup Audio Hijack sessions: See `README.md`
- Configure paths and LLM API: See `.env` configuration in README.md

## Support

For issues or questions:
- Check `README.md` for detailed setup instructions
- Run `meetingctl doctor` for diagnostic information
- Review error messages in notifications for specific guidance
