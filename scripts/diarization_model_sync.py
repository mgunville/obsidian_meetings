from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, snapshot_download


def _env_truthy(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _resolve_token() -> str:
    for name in ("PYANNOTE_AUTH_TOKEN", "HF_TOKEN", "HUGGINGFACE_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value.startswith("<concealed by 1Password>"):
            continue
        if value:
            return value
    for name in (
        "MEETINGCTL_HF_TOKEN_FILE",
        "HUGGINGFACE_TOKEN_FILE",
        "HF_TOKEN_FILE",
        "PYANNOTE_AUTH_TOKEN_FILE",
    ):
        raw_path = os.environ.get(name, "").strip()
        if not raw_path:
            continue
        path = Path(raw_path).expanduser()
        if not path.is_file():
            continue
        try:
            token = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if token.startswith("<concealed by 1Password>"):
            continue
        if token:
            return token
    return ""


def _parse_repo_ids() -> list[str]:
    model_ids: list[str] = []

    whisperx_model = os.environ.get("WHISPERX_MODEL", "large-v2").strip()
    if whisperx_model and "/" not in whisperx_model and not whisperx_model.startswith("."):
        model_ids.append(f"Systran/faster-whisper-{whisperx_model}")
    elif whisperx_model and "/" in whisperx_model:
        model_ids.append(whisperx_model)

    diarization_models_raw = os.environ.get(
        "WHISPERX_DIARIZATION_MODELS",
        "pyannote/speaker-diarization-3.1,pyannote/speaker-diarization",
    )
    for item in diarization_models_raw.split(","):
        model_id = item.strip()
        if model_id and model_id not in model_ids:
            model_ids.append(model_id)
    return model_ids


def _local_ref_sha(model_id: str, *, hf_home: Path) -> str:
    rel_model_dir = Path(f"models--{model_id.replace('/', '--')}")
    for base in (hf_home, hf_home / "hub"):
        model_dir = base / rel_model_dir
        for ref_name in ("main",):
            ref_path = model_dir / "refs" / ref_name
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()
    return ""


def _local_snapshot_path(model_id: str, *, hf_home: Path, sha: str) -> Path | None:
    if not sha:
        return None
    rel_model_dir = Path(f"models--{model_id.replace('/', '--')}")
    for base in (hf_home, hf_home / "hub"):
        candidate = base / rel_model_dir / "snapshots" / sha
        if candidate.exists():
            return candidate
    return None


def _is_local_snapshot_complete(model_id: str, *, hf_home: Path, sha: str) -> bool:
    snapshot = _local_snapshot_path(model_id, hf_home=hf_home, sha=sha)
    if snapshot is None:
        return False
    return (snapshot / "config.yaml").exists()


def _configure_ssl() -> None:
    ca_bundle = (
        os.environ.get("MEETINGCTL_SSL_CA_BUNDLE", "").strip()
        or os.environ.get("MEETINGCTL_SSL_CERT_FILE", "").strip()
        or os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
    )
    if ca_bundle:
        ca_path = Path(ca_bundle).expanduser()
        if ca_path.exists():
            os.environ["REQUESTS_CA_BUNDLE"] = str(ca_path)
            os.environ["SSL_CERT_FILE"] = str(ca_path)

    if not (
        _env_truthy("MEETINGCTL_DIARIZATION_INSECURE_SSL")
        or _env_truthy("MEETINGCTL_INSECURE_SSL")
    ):
        return
    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        original_request = requests.sessions.Session.request

        def _insecure_request(self: Any, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
            kwargs["verify"] = False
            return original_request(self, method, url, *args, **kwargs)

        requests.sessions.Session.request = _insecure_request
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Check/refresh diarization model cache from Hugging Face")
    parser.add_argument("--refresh", action="store_true", help="Download latest snapshots when updates are found")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    hf_home = Path(os.environ.get("HF_HOME", "/shared/diarization/cache/hf")).expanduser().resolve()
    hf_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    _configure_ssl()
    token = _resolve_token()
    api = HfApi(token=token or None)
    repos = _parse_repo_ids()
    results: list[dict[str, Any]] = []

    for repo_id in repos:
        local_sha = _local_ref_sha(repo_id, hf_home=hf_home)
        local_complete = _is_local_snapshot_complete(repo_id, hf_home=hf_home, sha=local_sha)
        item: dict[str, Any] = {
            "repo_id": repo_id,
            "local_sha": local_sha,
            "local_complete": local_complete,
            "remote_sha": "",
            "needs_update": False,
            "refreshed": False,
            "error": "",
        }
        try:
            info = api.model_info(repo_id=repo_id, token=token or None)
            item["remote_sha"] = str(getattr(info, "sha", "") or "")
            local_sha = str(item["local_sha"])
            remote_sha = str(item["remote_sha"])
            local_complete = bool(item["local_complete"])
            item["needs_update"] = bool(remote_sha and remote_sha != local_sha)
            if args.refresh and (item["needs_update"] or not local_sha or not local_complete):
                snapshot_download(
                    repo_id=repo_id,
                    token=token or None,
                    local_files_only=False,
                    cache_dir=str(hf_home),
                    resume_download=True,
                )
                item["local_sha"] = _local_ref_sha(repo_id, hf_home=hf_home)
                item["local_complete"] = _is_local_snapshot_complete(
                    repo_id,
                    hf_home=hf_home,
                    sha=str(item["local_sha"]),
                )
                item["refreshed"] = True
                item["needs_update"] = bool(item["remote_sha"] and item["remote_sha"] != item["local_sha"])
        except Exception as exc:  # pragma: no cover - operational script
            item["error"] = str(exc)
        results.append(item)

    payload = {
        "hf_home": str(hf_home),
        "repos_checked": len(results),
        "refresh": bool(args.refresh),
        "results": results,
    }
    if args.json:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
