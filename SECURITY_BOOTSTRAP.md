# Security Bootstrap

This repo is configured with a pre-commit gitleaks hook and hardened secret ignores.

## One-Time Setup

1. Install pre-commit (if not already installed):

```bash
python3 -m pip install --user pre-commit
```

2. Install hooks in this repo:

```bash
cd /Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings
pre-commit install --install-hooks
```

3. Validate current tree:

```bash
cd /Users/mike/Documents/Dev/agentic_Projects/projects/obsidian_meetings
pre-commit run --all-files
```

## Notes

- Real secrets must not be committed.
- Use `.env.example` for placeholders only.
- `.gitignore` includes a managed credentials hardening block.
