---
name: contract-freezer
description: Freeze and protect machine-readable CLI/JSON contracts and fixtures to prevent downstream drift. Use when changing event/start/stop/status/doctor outputs.
---

# Contract Freezer

Target contracts:
- `meetingctl event --json`
- `meetingctl start --json`
- `meetingctl status --json`
- `meetingctl doctor --json`

1. Update schema/field list intentionally.
2. Update fixtures in `tests/fixtures/` in the same change.
3. Add regression tests asserting field presence/types.
4. Document breaking changes in PR notes and handoff.
5. Reject unplanned contract drift.
