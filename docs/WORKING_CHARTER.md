# Working Charter

This charter defines execution standards for all contributors (human or model) in this project.

## 1) Operating Principles
- Optimize for delivery speed without sacrificing correctness.
- Prefer simple, testable implementations (YAGNI).
- Keep contracts stable and explicit.
- Prioritize deterministic behavior over cleverness.

## 2) Continuous State Updates
- Keep working state updated continuously during execution:
  - `memory`: durable decisions, assumptions, and constraints.
  - `journal`: progress notes, what changed, and why.
  - `tasklist`: current and next actions, dependencies, blockers.
- Update these artifacts incrementally, not only at milestone boundaries.

## 3) Efficiency Expectations
- Reuse existing skills, scripts, fixtures, and templates before creating new assets.
- Choose the shortest reliable path:
  - focused story scope
  - minimal diffs
  - direct validation loops
- Reduce rework by freezing interfaces before downstream integration.

## 4) Quality Guardrails
- TDD first: write/adjust failing tests, then implement, then refactor.
- Preserve safety invariants:
  - no unmanaged note mutations outside sentinels
  - idempotent reruns where required
  - actionable error output for operational failures
- Validate machine-readable contracts with fixtures and regression tests.

## 5) Coordination and Handoffs
- Announce skill usage and story scope before implementation.
- Publish contract fixtures when outputs change.
- Surface blockers early with concrete mitigation options.

## 6) Definition of Effective Delivery
- Faster cycle time over successive iterations.
- Stable or improved test coverage and pass rates.
- Fewer integration regressions and handoff misunderstandings.
