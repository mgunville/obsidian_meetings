---
name: safe-note-patching
description: Implement and verify sentinel-only note mutation with idempotent behavior and dry-run previews. Use when editing note patching logic or template-managed regions.
---

# Safe Note Patching

Managed regions:
- `<!-- MINUTES_START -->` / `<!-- MINUTES_END -->`
- `<!-- DECISIONS_START -->` / `<!-- DECISIONS_END -->`
- `<!-- ACTION_ITEMS_START -->` / `<!-- ACTION_ITEMS_END -->`
- `<!-- TRANSCRIPT_START -->` / `<!-- TRANSCRIPT_END -->`

1. Mutate only content inside managed regions.
2. Preserve all unmanaged content byte-for-byte.
3. Keep patching idempotent across reruns.
4. Provide `--dry-run` without file writes.
5. Add tests for outside-region protection and idempotency.
