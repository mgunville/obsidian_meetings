---
name: story-executor
description: Execute one backlog story at a time with strict scope control, explicit acceptance checks, and dependency-aware handoffs. Use when implementing any story from docs/EPICS_AND_STORIES.md.
---

# Story Executor

1. Read the target story in `docs/EPICS_AND_STORIES.md` and dependencies in `docs/EXECUTION_PLAN.md`.
2. Confirm scope boundaries and list excluded work.
3. Implement only the minimum code needed to pass story acceptance criteria.
4. Record changed files and contracts touched.
5. Publish a handoff note with test evidence and any blockers.

Required output:
- Story ID
- Files changed
- Acceptance checks passed
- Handoff contract changes (if any)
