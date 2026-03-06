# Shared Data Layout

This folder is the common project data mount used by Docker sidecars and local tooling.

- `shared_data/diarization/jobs/`
  - One subfolder per diarization run (`job_id`) with transcript artifacts and a manifest.
- `shared_data/diarization/cache/`
  - Model/cache state for sidecar runs (`HF_HOME`, transformers cache).
- `shared_data/diarization/manifests/`
  - Optional curated manifests you may want to keep under version control.

Operational note:
- Generated job outputs and caches are ignored by git to prevent repo bloat.
- Folder structure remains in repo so paths are stable across machines.
