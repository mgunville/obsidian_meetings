---
name: integration-auditor
description: Run independent risk-based integration checks beyond story-level TDD, focusing on regressions, idempotency, setup friction, and contract drift. Use before milestone or release decisions.
---

# Integration Auditor

1. Build a risk matrix: happy path, failure path, rerun path, setup path.
2. Execute smoke checks across start -> stop -> process flow.
3. Validate JSON contract consistency and fixture freshness.
4. Add missing high-risk regression tests.
5. Report findings ordered by severity with go/no-go recommendation.
