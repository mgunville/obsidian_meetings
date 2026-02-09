from __future__ import annotations

import pytest

from meetingctl.note.patcher import PatchingError, apply_managed_patch


NOTE_TEXT = """---
title: "Weekly Sync"
---

# Weekly Sync

Unmanaged intro paragraph.

## Minutes
<!-- MINUTES_START -->
> _Pending_
<!-- MINUTES_END -->

## Decisions
<!-- DECISIONS_START -->
> _Pending_
<!-- DECISIONS_END -->

## Action items
<!-- ACTION_ITEMS_START -->
> _Pending_
<!-- ACTION_ITEMS_END -->

## Transcript
<!-- TRANSCRIPT_START -->
> _Pending_
<!-- TRANSCRIPT_END -->

Unmanaged footer paragraph.
"""


def test_patcher_updates_only_managed_regions() -> None:
    patched, changed_regions = apply_managed_patch(
        NOTE_TEXT,
        {
            "minutes": "Discussed project milestones.",
            "decisions": "- Proceed with rollout",
        },
    )

    assert "Discussed project milestones." in patched
    assert "- Proceed with rollout" in patched
    intro_prefix = NOTE_TEXT.split("## Minutes")[0]
    footer_suffix = NOTE_TEXT.split("<!-- TRANSCRIPT_END -->", maxsplit=1)[1]
    assert patched.startswith(intro_prefix)
    assert patched.endswith(footer_suffix)
    assert changed_regions == ["minutes", "decisions"]


def test_patcher_is_idempotent() -> None:
    updates = {"minutes": "Same value"}
    first, _ = apply_managed_patch(NOTE_TEXT, updates)
    second, _ = apply_managed_patch(first, updates)
    assert first == second


def test_patcher_rejects_missing_sentinel() -> None:
    with pytest.raises(PatchingError):
        apply_managed_patch("no sentinels here", {"minutes": "x"})
