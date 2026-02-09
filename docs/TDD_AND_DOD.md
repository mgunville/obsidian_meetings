# TDD and Definition of Done

## TDD Rules
- For each story: add failing test -> implement minimum code -> refactor.
- Unit tests are mandatory for logic-heavy modules.
- Integration checks are required for KM/Audio Hijack touchpoints.

## YAGNI Rules
- No optional integrations until their stories are in-progress.
- Avoid speculative abstractions.
- Keep CLI and data contracts minimal and explicit.

## Story Done Criteria
- Acceptance criteria pass.
- Tests added and green locally.
- No unrelated code churn.
- Logging and error messages are actionable.

## Epic Done Criteria
- All child stories done.
- Contract boundaries are documented.
- End-to-end demo path validated.
