---
name: release-readiness
description: Gate milestone or internal rollout readiness using acceptance criteria, setup reproducibility, and diagnostics quality checks. Use when preparing a milestone handoff.
---

# Release Readiness

1. Validate all targeted story acceptance criteria are met.
2. Verify setup path on a clean environment using docs/scripts.
3. Verify `meetingctl doctor` diagnostics are actionable.
4. Confirm known limitations and deferred scope are documented.
5. Produce rollout checklist and residual risk summary.
