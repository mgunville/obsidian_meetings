# Vault Metadata And Transcript Normalization Runbook

Last updated: 2026-02-26
Status: Planned (documented, not yet executed end-to-end)

## Objective

Standardize note metadata and reduce note noise by:

1. Removing full inline transcript bodies from meeting notes.
2. Keeping transcript/audio access through artifact links in `## References`.
3. Normalizing frontmatter category fields across the vault.

## Confirmed Decisions

### Transcript policy

- Meeting notes should not keep full `## Transcript` text blocks.
- Notes should reference transcript/audio artifacts from `## References`.
- If references already exist, remove transcript section.
- If references are missing, create references before removing transcript section.

### Frontmatter policy

- Use `type` for root category only:
  - `daily`
  - `work`
  - `personal`
  - `reference`
  - `system`
- Use `note_type` for semantic subtype (for example `meeting`, `template`).
- Avoid overloading `type: meeting`.

### Firm policy

- `firm` is allowed only for work notes.
- Remove `firm` from:
  - `_Daily/`
  - `Personal/`
  - `Reference/`
  - `System/`
- Keep/infer `firm` only under `_Work/`.

### Explicit current exclusion

- Do not classify notes under `meetings/` or `Meetings/` yet.
- Those are intentionally deferred until files are renamed/moved into final folders.

## Execution Plan

## Phase 0: Preflight Snapshot

Run from vault repo root (`~/Notes/notes-vault`):

```bash
git status --short --branch
rg -n '^## Transcript$' meetings Meetings -g '*.md' 2>/dev/null | wc -l
rg -n '^## References$' meetings Meetings -g '*.md' 2>/dev/null | wc -l
rg -n '^firm:' _Daily Personal Reference System -g '*.md' 2>/dev/null | wc -l
```

## Phase 1: Code Behavior Change (before mass note edits)

Reason: current processor still writes full transcript into managed transcript region.

Planned code updates:

- `templates/meeting.md`
  - Remove `## Transcript` block from template.
  - Keep `## References` managed block.
- `src/meetingctl/cli.py`
  - Stop writing `transcript` managed region in `_default_queue_handler`.
  - Write only `references` region entries for transcript/audio artifact links.
- Optional compatibility:
  - Keep transcript marker support in patcher for legacy notes during migration window.

Validation after code change:

```bash
PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli process-queue --max-jobs 1 --json
```

Confirm new/updated notes do not get inline transcript text blocks.

## Phase 2: Meeting Note Cleanup (links-only transcript)

Scope:

- Apply to meeting notes that are in active destination folders after user move/rename.
- For now, `meetings/` and `Meetings/` are excluded from category classification, but transcript cleanup can still be applied when ready.

Per-note transform:

1. Ensure `## References` exists.
2. Ensure references include artifact links for existing files under:
   - `Meetings/_artifacts/<meeting_id>/<meeting_id>.txt`
   - `Meetings/_artifacts/<meeting_id>/<meeting_id>.srt`
   - `Meetings/_artifacts/<meeting_id>/<meeting_id>.json`
   - audio path
3. Remove full `## Transcript` section (header + managed markers + content).

Validation:

```bash
rg -n '^## Transcript$' <target-folders> -g '*.md'
rg -n 'transcript_txt:|transcript_srt:|transcript_json:|^- audio:' <target-folders> -g '*.md'
```

## Phase 3: Frontmatter Category Normalization

Scope:

- Include:
  - `_Daily/`
  - `_Work/`
  - `Personal/`
  - `Reference/`
  - `System/`
- Exclude:
  - `meetings/`
  - `Meetings/`
  - `.trash/`

Rules:

1. Set `type` by root folder:
   - `_Daily` -> `daily`
   - `_Work` -> `work`
   - `Personal` -> `personal`
   - `Reference` -> `reference`
   - `System` -> `system`
2. `note_type`:
   - Preserve existing if present.
   - If legacy `type: meeting` is encountered in scoped folders, move to `note_type: meeting`.
   - For `System/Templates/**`, default `note_type: template` if absent.
3. `firm`:
   - Remove from non-work roots.
   - Keep/infer under `_Work/` only.

Validation:

```bash
rg -n '^type:' _Daily _Work Personal Reference System -g '*.md' | wc -l
rg -n '^note_type:' _Daily _Work Personal Reference System -g '*.md' | wc -l
rg -n '^firm:' _Daily Personal Reference System -g '*.md'
```

Expected: no `firm` hits outside `_Work/`.

## Phase 4: Final Review And Commit

Recommended commit strategy:

1. Code behavior changes (template + processor) commit.
2. Transcript cleanup migration commit.
3. Frontmatter normalization commit.

Post-change checks:

```bash
git status --short
PYTHONPATH=src ./.venv/bin/python -m meetingctl.cli audit-notes --json
```

## Rollback

If a phase result is not acceptable:

- Reset only that phase by reverting the specific commit.
- Do not use destructive workspace resets unless explicitly approved.

