---
name: tdd-loop
description: Enforce red-green-refactor implementation flow for each story with minimal code and high-signal tests. Use when coding or updating tests in this repo.
---

# TDD Loop

1. Write or update a failing test for the target behavior.
2. Implement the smallest code change to pass tests.
3. Refactor only if behavior stays unchanged and tests remain green.
4. Add one negative-path test for each non-trivial branch.
5. Report test commands and results.

Guardrails:
- Do not merge code without tests.
- Do not add speculative abstractions.
