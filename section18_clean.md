# Section 18: UI/UX Integration Layer

## 18.1 Overview

While meetingctl provides the core automation engine, the user interface layer determines whether the system is used daily or abandoned. This section defines the primary interaction surfaces: Keyboard Maestro for context-aware automation and Alfred 5 (or Raycast) for manual control and search.
**Design Principles:**

- Zero-friction start: Start recording in <2 seconds from any application
- Ambient awareness: Always know recording status without context-switching
- Graceful fallback: Manual override when automation fails
- Fast recovery: Quick access to recent meetings and transcripts
- Multi-modal: Support hotkeys, keywords, and gestures

**Tool Selection:**

- Keyboard Maestro: Background automation, context triggers, menu bar presence
- Alfred 5 Powerpack (primary) or Raycast (free alternative): Command palette, search, workflows
- Optional: Bartender 4 (menu bar management), BetterTouchTool (gesture controls)


## 18.2 Keyboard Maestro Integration

### 18.2.1 Core Macros

All macros call meetingctl CLI commands. KM provides orchestration and UI feedback only.
#### Macro 1: Start Meeting

**Trigger Options:**

- Global hotkey: ⌥ + R (recommended)
- Palette trigger: Type "meeting" in KM palette
- Context trigger: Zoom/Teams window opens + calendar event active (see 18.2.2)

**Actions:**

```sql
# 1. Execute meetingctl start
set result to do shell script "source ~/.zshrc; meetingctl start --window-minutes 5 2>&1"

# 2. Parse result
if result contains "ERROR" then
display notification result with title "❌ Recording Failed" sound name "Basso"
else if result contains "FALLBACK:System+Mic" then
display notification "⚠️ Using fallback audio (System+Mic). Platform unknown." with title "Recording Started"
else
set meetingTitle to do shell script "echo " & quoted form of result & " | jq -r '.title'"
display notification "Recording: " & meetingTitle with title "🔴 Meeting Started" sound name "Blow"
end if
```

**Expected Behavior:**

- Shows notification with meeting title
- If platform detection fails, shows explicit warning
- On error, displays actionable message
- Returns immediately (non-blocking)

Deliverable: Start Meeting.kmmacros

#### Macro 2: Stop Meeting

**Trigger Options:**


Global hotkey: ⌥ + S (recommended)
Palette trigger: Type "stop" in KM palette
Menu bar click (see 18.2.3)

**Actions:**

```vbnet
# 1. Confirm recording is active
set activeCheck to do shell script "meetingctl status --json 2>&1"

if activeCheck contains "\"recording\":false" then
display notification "No active recording found" with title "⚠️ Nothing to Stop"
return
end if

# 2. Stop recording
do shell script "meetingctl stop 2>&1"

# 3. Show processing notification
display notification "Processing transcript and minutes. This may take a few minutes." with title "⏹ Recording Stopped" sound name "Pop"
```

**Expected Behavior:**

- Validates active recording before stopping
- Shows immediate confirmation
- Sets expectation for processing time
- Does not block for processing completion (runs async)

Deliverable: Stop Meeting.kmmacros

#### Macro 3: Recording Status

Trigger: Global hotkey ⌥ + I or menu bar click
**Actions:**

```vbnet
set status to do shell script "meetingctl status --json"
set isRecording to do shell script "echo " & quoted form of status & " | jq -r '.recording'"

if isRecording is "true" then
set meetingTitle to do shell script "echo " & quoted form of status & " | jq -r '.title'"
set duration to do shell script "echo " & quoted form of status & " | jq -r '.duration_human'"
set platform to do shell script "echo " & quoted form of status & " | jq -r '.platform'"

display dialog "🔴 Recording: " & meetingTitle & return & return & "Duration: " & duration & return & "Platform: " & platform buttons {"Stop Recording", "Continue"} default button "Continue"

if button returned of result is "Stop Recording" then
do shell script "meetingctl stop"
end if
else
display notification "No active recording" with title "Status"
end if
```

**Expected Behavior:**

- Shows current recording title, duration, platform
- Offers quick-stop button
- Shows "idle" state when not recording

Deliverable: Recording Status.kmmacros

#### Macro 4: Ad-hoc Recording

Trigger: Global hotkey ⌥⇧ + R or palette "record adhoc"
Use Case: Recording needed but no calendar event exists (hallway conversation, impromptu call)
**Actions:**

```vbnet
display dialog "Enter meeting title:" default answer "" buttons {"Cancel", "Start Recording"} default button "Start Recording"
set meetingTitle to text returned of result

do shell script "meetingctl start --adhoc --title " & quoted form of meetingTitle

display notification "Recording: " & meetingTitle with title "🔴 Ad-hoc Recording Started"
```

**Expected Behavior:**

- Prompts for title (required)
- Creates note with minimal metadata (no calendar association)
- Uses System+Mic fallback by default

Deliverable: Ad-hoc Recording.kmmacros

### 18.2.2 Context-Aware Auto-Start (Optional)

Use Case: Auto-detect meeting start and prompt user to record.
**Trigger Logic:**

scssIF (Calendar event is active OR starts within 2 minutes)
AND (Zoom.app OR Microsoft Teams.app window becomes active)
AND (No recording currently active)
THEN show auto-start prompt

**Implementation:**

Macro: Auto-Detect Meeting Start
**Triggers:**


Application "zoom.us" activates
Application "Microsoft Teams" activates

**Conditions:**


**Execute AppleScript to check calendar:**

kotlinset hasEvent to do shell script "meetingctl event --now-or-next 2 --quiet; echo $?"
return (hasEvent is "0")


**Actions:**

```vbnet
# Check if already recording
set isRecording to do shell script "meetingctl status --json | jq -r '.recording'"
if isRecording is "true" then
return
end if

# Get event details
set eventJSON to do shell script "meetingctl event --now-or-next 2 --json"
set eventTitle to do shell script "echo " & quoted form of eventJSON & " | jq -r '.title'"

# Show prompt with 10-second timeout
display notification "Start recording for: " & eventTitle & "?" with title "🎙 Meeting Detected" sound name "Tink"

with timeout of 10 seconds
try
display dialog "Start recording?" & return & eventTitle buttons {"Skip", "Record"} default button "Record" giving up after 10

if button returned of result is "Record" or gave up of result is true then
do shell script "meetingctl start --window-minutes 2"
display notification "Recording started" with title "🔴 Auto-Recording"
end if
end try
end timeout
```

**User Experience:**


User joins Zoom/Teams call
Notification appears: "Meeting detected, start recording?"
User has 10 seconds to click "Skip"
If no action, recording auto-starts
If "Skip" clicked, no recording

**Configuration:**


Auto-start timeout: configurable in macro (default 10 seconds)
Can be disabled entirely for users who prefer manual control

Deliverable: Auto-Detect Meeting.kmmacros (marked as optional in deployment)

### 18.2.3 Menu Bar Status Indicator

Use Case: Persistent visual indicator of recording state.
**Implementation:**

Macro: Menu Bar Recording Indicator
Trigger: Recording status changes (detected by polling every 5 seconds)
**Actions:**

```vbnet
set status to do shell script "meetingctl status --json"
set isRecording to do shell script "echo " & quoted form of status & " | jq -r '.recording'"

if isRecording is "true" then
set duration to do shell script "echo " & quoted form of status & " | jq -r '.duration_human'"
# Update KM menu bar item to show: "🔴 " & duration
else
# Hide or show idle state
end if
```

**Menu Bar Behavior:**


Idle: No icon (or ⚪️ if always-visible preferred)
Recording: 🔴 23:14 (red dot + duration)
**Click action: Shows dropdown menu:**


Current meeting title
Duration
Platform
"Stop Recording" button
"Open Note" button
"Show Status" (calls Macro 3)


**Implementation Note:**

Keyboard Maestro 11+ supports native menu bar items. For earlier versions, use a separate helper app (e.g., SwiftBar or xbar script).
**SwiftBar Alternative:**

```bash
#!/bin/bash
# ~/Library/Application Support/SwiftBar/meeting-status.5s.sh
# Runs every 5 seconds

STATUS=$(meetingctl status --json 2>/dev/null)
IS_RECORDING=$$(echo "$$STATUS" | jq -r '.recording')

if [[ "$IS_RECORDING" == "true" ]]; then
DURATION=$$(echo "$$STATUS" | jq -r '.duration_human')
TITLE=$$(echo "$$STATUS" | jq -r '.title')

echo "🔴 $DURATION"
echo "---"
echo "$TITLE"
echo "Stop Recording | bash='meetingctl stop' terminal=false"
else
echo "⚪️"
fi
```

**Deliverable:**


Menu Bar Indicator.kmmacros (KM 11+)
OR meeting-status.5s.sh (SwiftBar script for earlier versions)


### 18.2.4 Meeting Mode Environment

Use Case: One-click preparation for meeting (open apps, enable DND, close distractions).
Macro: Enter Meeting Mode
Trigger: Global hotkey ⌥ + M or palette "meeting mode"
**Actions:**

perl# 1. Enable Do Not Disturb
```applescript
do shell script "shortcuts run 'Set Focus' --input 'Do Not Disturb'"

# 2. Close distracting apps
tell application "Slack" to quit
tell application "Mail" to quit

# 3. Open meeting apps
tell application "Obsidian" to activate

# 4. Show notification
display notification "DND enabled, distractions closed" with title "🎯 Meeting Mode"

Macro: Exit Meeting Mode
```

Trigger: Global hotkey ⌥⇧ + M or auto-trigger when recording stops
**Actions:**


Disable Do Not Disturb
Reopen Slack/Mail
Reset window positions

Deliverable: Meeting Mode.kmmacros

### 18.2.5 Deployment Package

File: km/Meeting-Automation-Macros.kmmacros
**Contents:**


Start Meeting
Stop Meeting
Recording Status
Ad-hoc Recording
Auto-Detect Meeting (optional, disabled by default)
Menu Bar Indicator (or SwiftBar script reference)
Meeting Mode (optional)

**Installation:**


Double-click .kmmacros file
KM imports all macros into new macro group "Meeting Automation"
User customizes hotkeys if conflicts exist
User enables "Auto-Detect Meeting" if desired

**Documentation Requirements:**


README section: "Keyboard Maestro Setup"
Screenshots of macro list and hotkey settings
Troubleshooting: "Macros not triggering" → check permissions


## 18.3 Alfred Integration

### 18.3.1 Overview

Alfred provides command palette interface for manual control and search for historical meetings.
Alfred Powerpack required ($34 one-time). Free alternative: Raycast (see 18.3.8).
### 18.3.2 Smart Recording Toggle

Keyword: rec
**Behavior:**


If recording active → stops recording
If recording idle → starts recording (detects from calendar)

**Alfred Workflow Script:**

```bash
#!/bin/bash
source ~/.zshrc

STATUS=$(meetingctl status --json)
IS_RECORDING=$$(echo "$$STATUS" | jq -r '.recording')

if [[ "$IS_RECORDING" == "true" ]]; then
meetingctl stop
echo "⏹ Recording stopped. Processing..."
else
RESULT=$(meetingctl start --window-minutes 5 2>&1)

if [[ "$RESULT" == *"ERROR"* ]]; then
echo "❌ $RESULT"
exit 1
else
TITLE=$$(echo "$$RESULT" | jq -r '.title')
echo "🔴 Recording: $TITLE"
fi
fi
```

**Alfred Output:**


Shows result as large text notification
Optional: trigger macOS notification via osascript

Deliverable: Alfred workflow node in Meeting Recorder.alfredworkflow

### 18.3.3 Meeting Dashboard

Keyword: meetings
**Behavior:**


Lists today's calendar events
Shows status: ✅ recorded, 📝 note exists, ⏺ recording now, ⚪️ not recorded
**Select event → submenu:**


Start Recording
Open Note
View Transcript
Regenerate Summary


**Alfred Script Filter:**

phpRun Code#!/bin/bash
source ~/.zshrc

EVENTS=$(meetingctl event --today --json)

echo "$EVENTS" | jq -c '.[]' | while read -r event; do
TITLE=$$(echo "$$event" | jq -r '.title')
START=$$(echo "$$event" | jq -r '.start_human')
MEETING_ID=$$(echo "$$event" | jq -r '.meeting_id // empty')

```applescript
if [[ -n "$MEETING_ID" ]]; then
NOTE_STATUS=$$(meetingctl note exists --meeting-id "$$MEETING_ID" && echo "✅" || echo "⚪️")
else
NOTE_STATUS="⚪️"
fi

cat <<EOF
{
"title": "$$NOTE_STATUS $$TITLE",
"subtitle": "$START",
"arg": "$MEETING_ID",
"autocomplete": "$TITLE",
"variables": {
"meeting_id": "$MEETING_ID",
"title": "$TITLE"
}
}
EOF
done | jq -s '{"items": .}'
```

**Alfred Actions (on item selection):**


Default action (Enter): Open note in Obsidian
⌘ + Enter: Start recording for this event
⌥ + Enter: Show transcript only
⌃ + Enter: Regenerate summary (re-run LLM with new prompt)

Deliverable: Workflow node in Meeting Recorder.alfredworkflow

### 18.3.4 Transcript Search

Keyword: transcript {query}
**Behavior:**


Full-text search across all meeting transcripts
Shows matching meetings with preview snippet
Select → opens note at transcript section

**Alfred Script Filter:**

```bash
#!/bin/bash
source ~/.zshrc

QUERY="\$1"
VAULT_PATH=$(meetingctl config get VAULT_PATH)

if command -v rg &>/dev/null; then
SEARCH_CMD="rg --json"
else
SEARCH_CMD="grep -r"
fi

RESULTS=$$(rg --json -i "$$QUERY" "$VAULT_PATH" | grep '\.md:' | head -20)

echo "$RESULTS" | jq -s '{items: [.[] | {
title: (.data.path.text | split("/") | last | sub("\\.md$"; "")),
subtitle: .data.lines.text,
arg: .data.path.text,
match: .data.submatches[0].match.text
}]}'
```

**Alfred Actions:**


Enter: Open note in Obsidian
⌘ + Enter: Open note and scroll to matched line
⌥ + Enter: Copy matched snippet to clipboard

Deliverable: Workflow node in Meeting Recorder.alfredworkflow

### 18.3.5 Quick Summary Regeneration

Keyword: summary {meeting title}
Use Case: User wants different summary style or re-summarize after editing transcript.
**Behavior:**


Search recent meetings
Select meeting → regenerate summary with fresh LLM call
Optionally: prompt for custom instructions (e.g., "focus on action items only")

**Alfred Script:**

```bash
#!/bin/bash
source ~/.zshrc

MEETING_ID="\$1"
CUSTOM_PROMPT="\$2"

if [[ -n "$CUSTOM_PROMPT" ]]; then
meetingctl summarize --meeting-id "$$MEETING_ID" --prompt "$$CUSTOM_PROMPT"
else
meetingctl summarize --meeting-id "$MEETING_ID"
fi

meetingctl patch-note --meeting-id "$MEETING_ID" --section minutes

echo "✅ Summary regenerated"
```

**Alfred Workflow:**


Keyword summary → shows list filter of recent meetings
Select meeting → shows text input for custom prompt (optional)
Execute regeneration script
Show confirmation notification

Deliverable: Workflow node in Meeting Recorder.alfredworkflow

### 18.3.6 Quick Actions

Keyword: meeting
Behavior: Shows action menu (no calendar query, just commands)
**Actions:**


Start Recording
Stop Recording
Recording Status
Open Today's Meetings Folder
View Logs
Run Doctor

Implementation: Simple list filter with static items, each triggering meetingctl command.
Deliverable: Workflow node in Meeting Recorder.alfredworkflow

### 18.3.7 Workflow Package Structure

File: alfred/Meeting Recorder.alfredworkflow
**Contents:**

scssMeeting Recorder.alfredworkflow/
├── info.plist (workflow metadata)
├── icon.png (🎙 icon)
├── prefs.plist (user-configurable variables)
├── scripts/
│ ├── smart-record.sh
│ ├── meeting-list.sh
│ ├── transcript-search.sh
│ ├── quick-summary.sh
│ └── quick-actions.sh
└── README.txt

Workflow Variables (user-configurable in Alfred UI):

- vault_path: Path to Obsidian vault (default: from .env)
- default_window_minutes: Calendar look-ahead window (default: 5)
notification_sound: macOS sound name (default: "Blow")

**Installation:**


Double-click .alfredworkflow file
Alfred imports workflow
User reviews variables and updates if needed
Test with rec keyword

**Documentation Requirements:**


README section: "Alfred Setup"
Screenshots of workflow and keyword triggers
Video/GIF of rec toggle in action


### 18.3.8 Raycast Alternative

For users without Alfred Powerpack.
Raycast provides similar functionality for free (paid tier for team features only).
**Implementation Differences:**


TypeScript instead of bash scripts (Raycast extensions are Node.js-based)
Built-in UI components (forms, lists, detail views)
Native command palette integration

**Raycast Extension Structure:**

scssmeeting-recorder-raycast/
├── package.json
├── src/
│ ├── start-recording.tsx
│ ├── stop-recording.tsx
│ ├── meeting-list.tsx
│ ├── transcript-search.tsx
│ └── utils/
│ └── meetingctl.ts (wrapper for CLI calls)
└── assets/
└── icon.png

**Example Command (Start Recording):**

```javascript
Run Code// src/start-recording.tsx
import { showToast, Toast } from "@raycast/api";
import { execSync } from "child_process";

export default async function Command() {
try {
const result = execSync("meetingctl start --window-minutes 5").toString();
const data = JSON.parse(result);

await showToast({
style: Toast.Style.Success,
title: "Recording Started",
message: data.title,
});
} catch (error) {
await showToast({
style: Toast.Style.Failure,
title: "Recording Failed",
message: error.message,
});
}
}
```

**Deployment:**


Publish to Raycast Store (optional, for public use)
OR distribute as unpublished extension (.zip of source)
Users run npm install && npm run build && npm run dev to install locally

Deliverable: raycast-extension/ folder (alternative to Alfred workflow)
Decision Point: Build Alfred OR Raycast, not both initially (unless community contribution). Recommend Alfred first (larger user base, more mature workflow system).

## 18.4 Menu Bar Management (Optional)

### 18.4.1 Native KM Menu Bar Item

Keyboard Maestro 11+ supports native menu bar items.
**Setup:**


Create macro "Menu Bar Status"
Set trigger: "Status Menu" (displays in menu bar)
**Menu contents:**


Show status text (🔴 23:14 or ⚪️)
**Menu items:**


Recording: {Meeting Title}
Stop Recording (action: trigger "Stop Meeting" macro)
Open Note (action: open note in Obsidian)
Show Logs (action: open log file)


Implementation: See 18.2.3 for polling logic.

### 18.4.2 Bartender 4 Integration

Use Case: Hide menu bar icon when not recording.
**Setup:**


Install Bartender 4 ($16)
**Configure KM menu bar item to:**


Show always when recording
Hide when idle (or show in Bartender's hidden section)


Alternative: Hidden Bar (free) provides basic show/hide functionality.
Deliverable: Documentation only (user configures Bartender to taste)

## 18.5 Notification Strategy

### 18.5.1 Notification Types

EventPrioritySoundPersistenceRecording startedHigh"Blow"5 secRecording stoppedHigh"Pop"5 secProcessing completeMedium"Glass"10 secError (recording failed)Critical"Basso"Until dismissedError (transcription failed)High"Sosumi"10 secAuto-start promptHigh"Tink"10 sec (with buttons)Meeting detectedLowNone3 sec
### 18.5.2 Notification Content Guidelines

**Recording Started:**

```vbnet
Title: 🔴 Recording Started
Body: {Meeting Title}
Platform: {Teams|Zoom|Browser|System+Mic}
Actions: [Stop]
```

**Processing Complete:**

```yaml
Title: ✅ Meeting Processed
Body: {Meeting Title}
Transcript: {word_count} words
Action items: {count}
Actions: [Open Note] [Dismiss]
```

**Error (Actionable):**

```yaml
Title: ❌ Recording Failed
Body: {error_message}

Suggested fix: {action}
Actions: [Run Doctor] [View Logs] [Dismiss]
```

### 18.5.3 Implementation

**macOS Native Notifications:**

rustRun Codeosascript -e 'display notification "Recording started" with title "🔴 Meeting" sound name "Blow"'

**Enhanced Notifications (with actions):**

**Use terminal-notifier (Homebrew package):**

luaterminal-notifier \
-title "🔴 Recording Started" \
-message "Client Strategy Call" \
-sound "Blow" \
-actions "Stop,Open Note" \
-execute "meetingctl stop"

Deliverable: Notification helper function in meetingctl CLI:
- goRun Codemeetingctl notify --type started --title "Meeting Title"
- meetingctl notify --type error --message "Calendar access denied" --action "Run Doctor"


## 18.6 BetterTouchTool Integration (Optional)

Use Case: Gesture-based recording control (TouchBar, trackpad, Stream Deck).
### 18.6.1 TouchBar Buttons (MacBook Pro)

**Setup:**


Install BetterTouchTool ($22)
Add TouchBar button: "🔴 Record"
**Button action:**


If recording: show duration + "Stop" button
If idle: show "Start" button


Implementation: BTT calls same KM macros via AppleScript.

### 18.6.2 Trackpad Gestures

**Examples:**


Four-finger tap: Toggle recording (start/stop)
Three-finger double-tap: Show recording status

Configuration: BTT gesture → trigger KM macro

### 18.6.3 Stream Deck Integration

**Setup:**


Stream Deck "System" plugin
Create button: "Recording"
Button action: Execute shell script meetingctl start
Button appearance: Changes color when recording (poll meetingctl status)

Deliverable: Stream Deck profile export (.streamDeckProfile)

## 18.7 Do Not Disturb Automation

Goal: Auto-enable DND when recording starts, disable when stops.
### 18.7.1 Implementation (macOS Shortcuts)

Create Shortcut: "Enable Meeting DND"
```vbnet
Input: None
```

**Actions:**

- Set Focus: Do Not Disturb
- Wait 2 hours (max meeting duration)
- Set Focus: Off (auto-disable if user forgets)

**Call from KM "Start Meeting" macro:**

```javascript
Run Codedo shell script "shortcuts run 'Enable Meeting DND'"
```

**Call from KM "Stop Meeting" macro:**

```javascript
Run Codedo shell script "shortcuts run 'Disable DND'"
```

### 18.7.2 Enhanced Version (Muzzle Alternative)

Muzzle ($6) auto-detects screen sharing and enables DND.
**DIY Alternative: Detect screen sharing via:**

perlps aux | grep -i "screensharingd" | grep -v grep

Add to KM "Auto-Detect Meeting" macro to enable DND when screen sharing starts.
Deliverable: Optional KM macro "Auto-DND on Screen Share"

## 18.8 Quick Access to Logs and Diagnostics

### 18.8.1 Alfred Workflow: View Logs

Keyword: meetinglogs
**Behavior:**


Opens ~/meeting-automation/logs/meetingctl.log in Console.app or preferred editor
Shows tail of last 50 lines in Alfred preview
Option to clear old logs

**Script:**

```bash
#!/bin/bash
tail -50 ~/meeting-automation/logs/meetingctl.log
```

**Actions:**


Enter: Open full log in Console.app
⌘ + Enter: Open in default text editor
⌥ + Enter: Copy last error to clipboard


### 18.8.2 Alfred Workflow: Run Doctor

Keyword: meetingdoctor
**Behavior:**


Runs meetingctl doctor
Shows results in Alfred detail view
Highlights failures in red

**Script:**

```bash
#!/bin/bash
meetingctl doctor --json | jq -r '.checks[] | "\(.status) \(.name): \(.message)"'
```

**Output Example:**

```yaml
✅ Whisper installed: /opt/homebrew/bin/whisper
✅ Calendar access: Granted
❌ Audio Hijack: Not running
⚠️ API key: ANTHROPIC_API_KEY not set
```

**Actions:**


Enter: Copy diagnostics to clipboard
⌘ + Enter: Open troubleshooting docs (README section)


## 18.9 Cross-Device Sync Considerations

Problem: Keyboard Maestro and Alfred workflows are per-machine.
**Solution for Multi-Mac Deployment:**

### 18.9.1 KM Macro Sync (Native)

**Keyboard Maestro supports iCloud/Dropbox sync:**


Preferences → General → Sync Macros
Select sync folder: ~/Dropbox/Apps/Keyboard Maestro
Enable on all Macs

Caveat: Hotkeys may conflict if same keyboard on multiple Macs. User must adjust per machine.

### 18.9.2 Alfred Workflow Sync (Manual)

**Alfred does not auto-sync workflows. Workarounds:**

Option A: Shared Workflow File

Store Meeting Recorder.alfredworkflow in repo
On each Mac, re-import workflow
Workflow reads .env for paths (no hardcoding)

Option B: Symlink Workflow Folder
```javascript
Run Codeln -s ~/meeting-automation/alfred/Meeting\ Recorder.alfredworkflow ~/Library/Application\ Support/Alfred/Alfred.alfredpreferences/workflows/

```

Deliverable: Deployment docs include sync strategy

## 18.10 Testing UI/UX Layer

### 18.10.1 Manual Test Checklist

**Keyboard Maestro Macros:**


Start Meeting hotkey triggers recording
Stop Meeting hotkey stops recording
Status macro shows correct recording duration
Ad-hoc recording prompts for title
Auto-detect macro triggers on Zoom/Teams open (if enabled)
Menu bar indicator updates every 5 seconds
Meeting Mode enables DND and closes distractions

**Alfred Workflows:**


rec toggles recording on/off
meetings lists today's events with correct status icons
transcript {query} returns relevant results
summary regenerates summary for selected meeting
meeting shows quick actions menu
meetinglogs opens log file
meetingdoctor runs diagnostics

**Notifications:**


Recording start shows meeting title and platform
Recording stop shows confirmation
Processing complete notification has "Open Note" action
Errors show actionable messages

**Edge Cases:**


Start recording when already recording → shows error
Stop recording when nothing active → shows warning
Calendar permission denied → error message includes "Run Doctor"
No meeting in calendar window → shows "Ad-hoc" prompt


### 18.10.2 Automated Testing (Limited)

UI automation is brittle, but test key integration points:
- Test: KM Macro Execution
- rustRun Codeosascript -e 'tell application "Keyboard Maestro Engine" to do script "Start Meeting"'
- sleep 2
- meetingctl status --json | jq -e '.recording == true'

- Test: Alfred Workflow Script
```bash
- bash alfred/scripts/meeting-list.sh | jq -e '.items | length > 0'

```

Deliverable: Shell script test-ui-integration.sh for basic smoke tests

## 18.11 Documentation Requirements

### 18.11.1 Quick Start Guide

File: docs/UI-QUICKSTART.md
**Contents:**


Install Keyboard Maestro macros (double-click .kmmacros)
Import Alfred workflow (double-click .alfredworkflow)
Test recording (press ⌥ + R, say something, press ⌥ + S)
Check results (type meetings in Alfred, open note)

**Include:**


Screenshots of each step
GIF of recording workflow in action
Troubleshooting: "Macros not working" → check permissions


### 18.11.2 Hotkey Reference Card

File: docs/HOTKEYS.md
**Keyboard Maestro Hotkeys:**

HotkeyActionContext⌥ + RStart/Resume RecordingGlobal⌥ + SStop RecordingGlobal⌥ + IShow Recording StatusGlobal⌥⇧ + RAd-hoc RecordingGlobal⌥ + MEnter Meeting ModeGlobal⌥⇧ + MExit Meeting ModeGlobal
**Alfred Keywords:**

KeywordDescriptionrecToggle recordingmeetingsToday's meeting dashboardtranscript {query}Search all transcriptssummaryRegenerate meeting summarymeetingQuick actions menumeetinglogsView automation logsmeetingdoctorRun diagnostics
Print-friendly PDF version for desk reference.

### 18.11.3 Customization Guide

File: docs/CUSTOMIZATION.md
**Topics:**


Change hotkeys: How to modify KM macro triggers
Add custom prompts: Edit LLM prompt templates for summaries
Adjust auto-start timing: Configure calendar window and timeout
Disable auto-detect: Turn off context-aware triggers
Menu bar appearance: Show/hide, change icon, polling frequency
Notification sounds: macOS sound name reference


## 18.12 Accessibility Considerations

Keyboard-first design: All actions accessible via hotkeys (no mouse required)
Screen reader support: Notification text is descriptive (not just icons)
High contrast mode: Menu bar icons have text fallbacks
Voice control: Alfred keywords work with dictation
Deliverable: Accessibility section in main README

## 18.13 Deployment Checklist

File: DEPLOYMENT.md (append UI/UX section)
### 18.13.1 Per-Machine Setup

Phase 1: Core Installation

Run install.sh (installs dependencies)
Copy .env.example to .env and configure
Run meetingctl doctor (verify environment)

Phase 2: UI Layer

Import Keyboard Maestro macros (km/Meeting-Automation-Macros.kmmacros)
Grant Automation permissions (System Preferences → Privacy → Automation)
Customize hotkeys if conflicts exist
Import Alfred workflow (alfred/Meeting Recorder.alfredworkflow)
Configure Alfred workflow variables (vault path, etc.)

Phase 3: Audio Hijack

Install Audio Hijack (Rogue Amoeba)
Create required sessions: Teams+Mic, Zoom+Mic, Browser+Mic, System+Mic
Test each session manually
Configure output path: ~/Recordings/meetings/

Phase 4: Optional Enhancements

Install Bartender 4 (menu bar management)
Install BetterTouchTool (gesture controls)
Configure Do Not Disturb shortcuts
Enable KM macro sync (iCloud/Dropbox)

Phase 5: Testing

Test Start/Stop recording cycle
Verify note creation and patching
Check Alfred search and dashboard
Test error scenarios (no calendar access, etc.)


### 18.13.2 Multi-Mac Deployment

**After initial setup on Mac #1:**


**Sync repo to Mac #2:**

```bash
git clone <repo-url> ~/meeting-automation

```

**Copy .env and customize paths:**

```bash
cp .env.example .env
# Edit vault path, recording path for this machine

```

**Run installation:**

```bash
bash scripts/setup.sh

```

**Import UI components:**


KM macros (already in repo)
Alfred workflow (already in repo)
Audio Hijack sessions (manual setup)


Test with meetingctl doctor


**Estimated time:**


Mac #1 (initial): 2-3 hours
Mac #2-3 (clones): 30-45 minutes


## 18.14 Success Metrics

**UI/UX is successful when:**


Start-to-record time: <5 seconds from meeting start
Error recovery time: <2 minutes to diagnose and fix issues
Search speed: Find any past meeting transcript in <10 seconds
Cross-machine consistency: Same workflow on all Macs after initial setup
Daily adoption: User records ≥80% of eligible meetings without friction

**Measurement:**


Log meetingctl start calls and timestamp deltas
Track error rates in logs
User survey after 2 weeks


## 18.15 Future Enhancements (Out of Scope for v0.1)

**Potential UI/UX improvements for later versions:**


iOS Shortcuts integration: Upload mobile recordings to Mac for processing
Siri voice commands: "Hey Siri, start meeting recording"
Calendar app extension: Start recording button in Calendar.app event details
Obsidian plugin: Native start/stop buttons in meeting notes
Meeting summary preview: Rich preview in Alfred (formatted markdown)
Automated meeting prep: Pull agenda from calendar into note pre-meeting
Post-meeting follow-up: Auto-send email with action items (opt-in)
Dashboard widget: Today's meetings with recording status


## 18.16 Deliverables Summary

**Keyboard Maestro:**


km/Meeting-Automation-Macros.kmmacros (macro group export)
Optional: km/menu-bar-status.sh (SwiftBar script for KM <11)

**Alfred:**


alfred/Meeting Recorder.alfredworkflow (workflow package)
alfred/scripts/*.sh (workflow scripts)

**Raycast (alternative):**


raycast-extension/ (TypeScript extension source)

**BetterTouchTool (optional):**


btt/meeting-controls.bttpreset (gesture preset export)

**Stream Deck (optional):**


streamdeck/meeting-recording.streamDeckProfile

**Documentation:**


docs/UI-QUICKSTART.md (quick start guide)
docs/HOTKEYS.md (hotkey reference card)
docs/CUSTOMIZATION.md (customization guide)
Screenshots and GIFs in docs/screenshots/

**Tests:**


tests/test-ui-integration.sh (smoke tests for UI layer)


## 18.17 Open Questions

**For decision before implementation:**


Alfred vs. Raycast priority: Which to build first? (Recommend: Alfred due to larger user base)
Menu bar indicator: KM native vs. SwiftBar? (Recommend: SwiftBar for compatibility with KM <11)
Auto-start default: Should auto-detect macro be enabled by default? (Recommend: No, opt-in for power users)
Notification verbosity: Show every step or just start/stop/errors? (Recommend: Start/stop/errors only)
BetterTouchTool inclusion: Worth the $22 ask? (Recommend: Optional, document but don't require)
Gesture defaults: Standard hotkeys vs. encourage custom gestures? (Recommend: Hotkeys primary, gestures for users who already own BTT)


End of Section 18

Integration with Existing Spec
**Changes to other sections required:**


Section 10 (Build Plan): Add Phase 11: "UI/UX Integration Layer" after Phase 10
Section 15 (Acceptance Criteria): Add UI criteria: "Start recording via ⌥+R hotkey works in <2 seconds"
Section 13 (Deployment): Reference Section 18.13 for UI-specific setup steps
README: Add "Quick Start (UI)" section linking to docs/UI-QUICKSTART.md
