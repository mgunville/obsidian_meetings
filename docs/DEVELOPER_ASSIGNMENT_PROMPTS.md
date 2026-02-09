# Developer Assignment Prompts (v2: Model-Aware)

This version assigns work to available models:
- DeepSeek-R1
- Claude
- Codex
- Qwen2.5-Coder (Ollama)
- Gemini

Aligned docs:
- `obsidian_spec.md`
- `docs/EPICS_AND_STORIES.md`
- `docs/EXECUTION_PLAN.md`
- `docs/TDD_AND_DOD.md`
- `docs/WORKING_CHARTER.md`

Repo root:
- `/Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings`

---

## 1) Model Fit Guidance

### Codex (Primary implementation agent)
Best for:
- Multi-file implementation
- Fast iteration with tests
- CLI contracts and integration glue
Use for:
- E1, E4, E5 core implementation

### Claude (Spec and contract rigor)
Best for:
- Clear interface contracts
- Failure-mode coverage
- Developer-facing docs and acceptance criteria tightening
Use for:
- API/JSON contract docs, story acceptance hardening, doc quality control

### DeepSeek-R1 (Reasoning-heavy logic + edge cases)
Best for:
- Complex logic and branch analysis
- Parser/selector behavior
- Threat modeling and failure-path reasoning
Use for:
- E2 event selection/backends, E3 safe patching invariants, E7 doctor checks logic

### Qwen2.5-Coder via Ollama (Focused coding tasks)
Best for:
- Small-to-medium scoped code tasks
- Unit test generation
- Utility modules and adapters
Use for:
- Story-bounded components with explicit output contract (diff + tests)

### Gemini (Independent verification + adversarial testing)
Best for:
- Cross-model contract review
- Adversarial and edge-case test design
- Integration and rollout risk assessment
Use for:
- Independent test auditing, risk matrix generation, and regression expansion

Recommendation:
- Use all 5 models. Keep each on narrow, non-overlapping story bundles with explicit handoffs.

---

## 2) Shared Prompt (Send to Every Developer/Model)

You are implementing `meetingctl` in:
`/Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings`

Rules:
1. Follow TDD and YAGNI strictly.
2. Work only inside assigned stories.
3. Keep CLI contracts stable; if changes are required, document and notify dependent owners.
4. Keep commits scoped to one story at a time.
5. No optional v0.1-deferred UX scope (Alfred/Raycast/menu bar/BTT/Stream Deck).
6. Before implementing each story, explicitly state which project skill(s) you are using.
7. Follow `docs/WORKING_CHARTER.md` for continuous memory/journal/tasklist updates and efficiency expectations.

Required skills usage:
- Use `story-executor` for story scoping and handoff notes.
- Use `tdd-loop` for all implementation stories.
- Use `contract-freezer` whenever JSON/CLI output contracts or fixtures may change.

Required workflow:
- `python3.11 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -e '.[dev]'`
- `pytest`

Output for each story:
1. What changed
2. Files changed
3. Tests added/updated
4. How to run/verify
5. Remaining risks

---

## 3) Developer Prompts by Model

### A) Codex Prompt (Core Integrator)

You are the core integrator for `meetingctl`.

Assigned stories:
- E1-S1, E1-S2, E1-S3
- E4-S1, E4-S2, E4-S3, E4-S4, E4-S5
- E5-S1, E5-S3, E5-S4

Objectives:
- Deliver stable CLI shell and runtime state model.
- Implement start/stop/status command flow with machine-readable JSON.
- Implement process orchestration and WAV->MP3 policy.

Must preserve contracts:
- `meetingctl status --json` fields:
  - `recording`, `meeting_id`, `title`, `platform`, `duration_human`, `note_path`

Dependencies consumed:
- Event JSON contract from DeepSeek-R1 lane
- Safe patcher contract from Qwen lane

Deliverables:
- Production code in `src/meetingctl/`
- Tests in `tests/`
- Contract fixtures under docs or tests fixtures

Required skills:
- `story-executor`
- `tdd-loop`
- `contract-freezer`

---

### B) DeepSeek-R1 Prompt (Calendar + Reliability Logic)

You own reasoning-heavy backend and reliability logic.

Assigned stories:
- E2-S1, E2-S2, E2-S3, E2-S4
- E7-S1

Objectives:
- Implement deterministic now-or-next event selection.
- Deliver EventKit-first backend with JXA fallback behavior.
- Ensure failure outputs are backend-aware and actionable.
- Implement doctor checks and failure hints.

Constraints:
- Avoid speculative calendar abstractions.
- Keep schema stable and minimal for downstream use.

Deliverables:
- Event module + tests (selection edge cases mandatory)
- `meetingctl event --json` schema fixture
- `meetingctl doctor` checks with actionable messages

Handoff required:
- Provide JSON fixtures and error examples for Codex/Claude/Qwen lanes.

Required skills:
- `calendar-backend-check`
- `contract-freezer`
- `tdd-loop`

---

### C) Qwen2.5-Coder Prompt (Notes + Patching Engine)

You own note mutation safety and template mechanics.

Assigned stories:
- E3-S1, E3-S2, E3-S3, E3-S4
- E5-S2 (summary parser only; no provider sprawl)

Objectives:
- Implement `meeting_id` + deterministic filename rules.
- Render meeting template with required frontmatter.
- Implement strict sentinel-only patching and dry-run mode.
- Implement summary parsing with fail-safe behavior.

Critical safety rule:
- Never mutate text outside sentinel boundaries.

Deliverables:
- `note/` and parser modules
- Idempotency and no-outside-mutation tests
- Dry-run output contract

Suggested execution style (Ollama):
- One story per prompt
- Require unified diff + tests in every response

Required skills:
- `safe-note-patching`
- `tdd-loop`
- `contract-freezer`

---

### D) Claude Prompt (UX + Documentation + Acceptance Gate)

You own UX packaging and quality gate documentation.

Assigned stories:
- E6-S1, E6-S2, E6-S3, E6-S4, E6-S5
- E7-S2, E7-S3

Objectives:
- Produce KM macro package and usage docs for v0.1 UX subset.
- Keep optional auto-detect disabled by default.
- Create setup and smoke-test flows that are executable by fresh developers.
- Validate that acceptance criteria in spec are testable and unambiguous.

Constraints:
- No non-v0.1 UX expansion.
- UX layer must consume stable CLI JSON contracts from Codex/DeepSeek lanes.

Deliverables:
- `km/Meeting-Automation-Macros.kmmacros`
- `docs/UI-QUICKSTART.md`
- `docs/HOTKEYS.md`
- integration smoke checks in scripts/tests

Required skills:
- `km-ux-packager`
- `story-executor`
- `release-readiness`

---

### E) Gemini Prompt (Independent QA and Release Confidence)

You own independent verification across all lanes. You are not the primary feature implementer.

Assigned scope:
- Independent testing and quality audit across E1-E7 outputs
- Contract consistency checks between:
  - `meetingctl event --json`
  - `meetingctl start --json`
  - `meetingctl status --json`
  - `meetingctl doctor --json`

Objectives:
- Validate integration behavior beyond story-level TDD.
- Design adversarial tests for failure and rerun paths.
- Detect contract drift and setup/onboarding gaps before rollout.

Constraints:
- Do not expand product scope.
- Only add tests/docs/minor bug fixes that directly improve reliability.
- Escalate major design deviations rather than silently changing contracts.

Deliverables:
- Risk-based test matrix
- Additional regression/integration tests
- Release-readiness report with Go/No-Go recommendation

Required skills:
- `integration-auditor`
- `release-readiness`
- `contract-freezer`

---

## 4) Additional Independent Testing Prompt (Beyond TDD)

Use this with any model (recommended owner: Gemini) after feature implementation.

### Independent Test Auditor Prompt

You are the independent test auditor for this repo:
`/Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings`

Goal:
- Validate system behavior beyond story-level TDD.
- Find integration regressions, contract drift, and operational gaps.

Tasks:
1. Review implemented stories against `obsidian_spec.md` acceptance criteria.
2. Build a risk-based test matrix:
   - happy path
   - failure path
   - rerun/idempotency path
   - setup/onboarding path
3. Add missing tests where risk is high:
   - CLI JSON contract tests
   - safe patch boundary regression tests
   - calendar backend fallback behavior tests
   - process rerun behavior tests
4. Execute smoke checks and summarize residual risks.

Output format:
1. Findings (ordered by severity) with file references.
2. Added tests and rationale.
3. Gaps not testable yet and why.
4. Go/No-Go recommendation for internal team rollout.

Non-goals:
- Do not expand feature scope.
- Do not refactor unrelated modules.

---

## 5) Handoff Contracts (Must Be Explicit)

Before downstream work starts, owners must publish:
- Event JSON fixture (`meetingctl event --json`)
- Start/stop/status JSON fixtures
- Doctor JSON fixture
- Patch dry-run output example

Store fixtures in:
- `tests/fixtures/` (preferred)

---

## 6) Suggested Execution Sequence with 5 Models

1. DeepSeek-R1: E2 + E7-S1 foundations
2. Qwen2.5-Coder: E3 + E5-S2
3. Codex: E1 + E4 + E5 orchestration
4. Claude: E6 + E7-S2/S3 packaging
5. Gemini: independent audit pass + adversarial testing + release recommendation

Parallelization notes:
- Codex can start E1 immediately.
- Qwen can start E3-S1/S2 after minimal template contract is frozen.
- E6 should start only after `status --json` and `start/stop` contracts are frozen.
- Gemini should begin drafting the risk matrix early, then run full audit after Steps 3-4 converge.
