# Skills Rollout

These project skills are authored in `skills/`.

## Included Skills
- story-executor
- tdd-loop
- contract-freezer
- safe-note-patching
- calendar-backend-check
- km-ux-packager
- integration-auditor
- release-readiness

## Install to Codex Home

From repo root:

```bash
mkdir -p ~/.codex/skills
rsync -a skills/ ~/.codex/skills/
```

## Validate Presence

```bash
find ~/.codex/skills -maxdepth 2 -name SKILL.md | sort
```

## Notes
- `skill-creator` bootstrap script could not be used in this environment due missing `PyYAML` dependency.
- Skills were drafted directly as valid `SKILL.md` files.
