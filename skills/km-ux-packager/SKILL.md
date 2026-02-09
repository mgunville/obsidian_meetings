---
name: km-ux-packager
description: Package and validate Keyboard Maestro v0.1 UX macros that consume meetingctl JSON contracts. Use when building Start/Stop/Status/Ad-hoc KM flows and related docs.
---

# KM UX Packager

In scope macros:
- Start Meeting
- Stop Meeting
- Recording Status
- Ad-hoc Recording
- Optional auto-detect (disabled by default)

1. Consume `meetingctl` JSON output; avoid parsing fragile text.
2. Show immediate notifications for start/stop/error.
3. Surface explicit `System+Mic` fallback warning.
4. Keep optional auto-detect disabled in exported defaults.
5. Validate macro behavior against a fresh setup checklist.
