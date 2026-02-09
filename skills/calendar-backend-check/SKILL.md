---
name: calendar-backend-check
description: Validate EventKit-first calendar resolution, JXA fallback behavior, and actionable error handling. Use when implementing or testing calendar discovery flows.
---

# Calendar Backend Check

1. Prefer EventKit backend when available.
2. Use JXA fallback only when EventKit is unavailable.
3. Include backend name and next action in all errors.
4. Ensure `meetingctl doctor` guidance appears on failures.
5. Add tests for:
- ongoing vs upcoming selection
- fallback switching
- backend-specific failure messages
