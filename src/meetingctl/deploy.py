from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any


PORTABLE_HAZEL_SCRIPT = """REPO_ROOT="${MEETINGCTL_REPO:-$HOME/Dev/obsidian_meetings}"

bash "$REPO_ROOT/scripts/secure_exec.sh" \\
  bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1" >> "$HOME/.local/state/meetingctl/hazel.log" 2>&1
"""

DEPLOY_COPY_PATHS = (
    ".env.example",
    "README.md",
    "SECURITY_BOOTSTRAP.md",
    "docker-compose.diarization.yml",
    "install.sh",
    "pyproject.toml",
    "requirements.txt",
    "config",
    "docker",
    "docs",
    "scripts",
    "src",
    "templates",
    "tests",
)

HAZEL_RULE_NAMES = (
    "MeetingCtl - Ingest Notes Audio",
    "MeetingCtl - Ingest Voice Memos",
)


def _find_bplist_offset(data: bytes) -> int:
    offset = data.find(b"bplist00")
    if offset < 0:
        raise ValueError("Hazel rules payload does not contain a binary plist.")
    return offset


def _load_hazel_plist(data: bytes) -> tuple[bytes, object]:
    offset = _find_bplist_offset(data)
    return data[:offset], plistlib.loads(data[offset:])


def _dump_hazel_plist(prefix: bytes, payload: object) -> bytes:
    return prefix + plistlib.dumps(payload, fmt=plistlib.FMT_BINARY, sort_keys=False)


def _walk_values(value: object):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _replace_hazel_values(value: object, *, rule_name: str, script_text: bytes) -> object:
    if isinstance(value, dict):
        return {
            key: _replace_hazel_values(item, rule_name=rule_name, script_text=script_text)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _replace_hazel_values(item, rule_name=rule_name, script_text=script_text)
            for item in value
        ]
    if isinstance(value, bytes):
        if b"hazel_ingest_file.sh" in value:
            return script_text
        return value
    if isinstance(value, str):
        if value.startswith("MeetingCtl - Ingest "):
            return rule_name
        return value
    return value


def hazel_rule_looks_compatible(data: bytes) -> bool:
    _, payload = _load_hazel_plist(data)
    for value in _walk_values(payload):
        if isinstance(value, bytes) and b"hazel_ingest_file.sh" in value:
            return True
        if isinstance(value, str) and value.startswith("MeetingCtl - Ingest "):
            return True
    return False


def discover_hazel_template(search_roots: list[Path] | None = None) -> Path | None:
    if search_roots is None:
        home = Path.home()
        search_roots = [
            home / "Library" / "Application Support" / "Hazel",
            home / "Library" / "CloudStorage",
        ]
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        try:
            candidates.extend(sorted(root.rglob("*.hazelrules")))
        except OSError:
            continue
    for candidate in candidates:
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        try:
            if hazel_rule_looks_compatible(data):
                return candidate
        except Exception:
            continue
    return None


def render_hazel_rule(template_data: bytes, *, rule_name: str) -> bytes:
    prefix, payload = _load_hazel_plist(template_data)
    rendered = _replace_hazel_values(
        payload,
        rule_name=rule_name,
        script_text=PORTABLE_HAZEL_SCRIPT.encode("utf-8"),
    )
    return _dump_hazel_plist(prefix, rendered)


def _copy_path(src: Path, dest: Path) -> None:
    def _ignore(path: str, names: list[str]) -> set[str]:
        ignored = {
            name
            for name in names
            if name in {".DS_Store", "__pycache__", ".pytest_cache", ".git", ".venv", "dist"}
            or name.endswith(".pyc")
        }
        src_path = Path(path)
        if src_path.name == "models" and src_path.parent.name == "config":
            if "whisperx" in names:
                ignored.add("whisperx")
        return ignored

    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=_ignore)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink(missing_ok=True)


def _validate_bundle_dir(bundle_dir: Path) -> Path:
    resolved = bundle_dir.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Bundle directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Bundle path is not a directory: {resolved}")
    if not (resolved / "install.sh").exists():
        raise FileNotFoundError(f"Bundle directory is missing install.sh: {resolved}")
    return resolved


def extract_bundle_archive(archive_path: Path, destination_root: Path) -> Path:
    resolved_archive = archive_path.expanduser().resolve()
    if not resolved_archive.exists():
        raise FileNotFoundError(f"Bundle archive does not exist: {resolved_archive}")
    destination_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(resolved_archive, "r:gz") as tar:
        members = tar.getmembers()
        roots = {Path(member.name).parts[0] for member in members if member.name and Path(member.name).parts}
        if len(roots) != 1:
            raise ValueError(f"Bundle archive must contain exactly one top-level directory: {resolved_archive}")
        tar.extractall(destination_root)
    bundle_dir = destination_root / next(iter(roots))
    return _validate_bundle_dir(bundle_dir)


def sync_bundle_to_target(bundle_dir: Path, target_dir: Path) -> dict[str, Any]:
    resolved_bundle = _validate_bundle_dir(bundle_dir)
    resolved_target = target_dir.expanduser().resolve()
    resolved_target.mkdir(parents=True, exist_ok=True)

    copied_entries: list[str] = []
    for entry in sorted(resolved_bundle.iterdir(), key=lambda item: item.name):
        if entry.name in {".DS_Store"}:
            continue
        destination = resolved_target / entry.name
        _remove_path(destination)
        _copy_path(entry, destination)
        copied_entries.append(entry.name)

    return {
        "bundle_dir": str(resolved_bundle),
        "target_dir": str(resolved_target),
        "copied_entries": copied_entries,
    }


def deploy_bundle(
    *,
    target_dir: Path,
    archive_path: Path | None = None,
    bundle_dir: Path | None = None,
    run_install: bool = True,
) -> dict[str, Any]:
    if bool(archive_path) == bool(bundle_dir):
        raise ValueError("Provide exactly one of archive_path or bundle_dir.")

    if archive_path is not None:
        with tempfile.TemporaryDirectory(prefix="meetingctl-deploy-") as temp_dir:
            extracted_bundle = extract_bundle_archive(archive_path, Path(temp_dir))
            result = sync_bundle_to_target(extracted_bundle, target_dir)
    else:
        result = sync_bundle_to_target(bundle_dir or Path("."), target_dir)

    if run_install:
        completed = subprocess.run(
            ["bash", "install.sh"],
            cwd=Path(result["target_dir"]),
            check=False,
            capture_output=True,
            text=True,
        )
        result["install"] = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        if completed.returncode != 0:
            raise RuntimeError(f"install.sh failed in {result['target_dir']}")
    return result


def _write_deploy_readme(bundle_dir: Path, hazel_template: Path | None) -> None:
    deploy_root = bundle_dir.name
    hazel_line = "Auto-generated from local Hazel template discovery."
    if hazel_template is not None:
        hazel_line = f"Generated from: {hazel_template}"
    text = "\n".join(
        [
            "# Deploy Bundle",
            "",
            "1. Extract this bundle anywhere on the destination Mac.",
            "2. Apply or update the target repo with:",
            "   `python3 scripts/deploy_bundle_apply.py --bundle-dir . --target-dir ~/Dev/obsidian_meetings`",
            "   This overwrites the shipped project paths in the target repo, preserves local state like `.venv` and `shared_data`, and reruns `install.sh`.",
            "3. If you install somewhere other than `~/Dev/obsidian_meetings`, set `MEETINGCTL_REPO` to the target repo path.",
            "4. Fill in `~/.config/meetingctl/env` (or `env.secure`) with at least `VAULT_PATH`, `RECORDINGS_PATH=~/Notes/audio`, and your summary/diarization secrets.",
            "5. If the env uses `op://...` refs, install/sign in to 1Password CLI so `op whoami` succeeds on the destination Mac.",
            "6. For diarization: no Hugging Face MCP server is needed, but the HF token must have accepted access to the gated pyannote repos before the first sidecar run.",
            "7. Validate Docker with `docker info`, then run `bash scripts/meetingctl_cli.sh doctor --json`.",
            "8. Import `config/km/Meeting-Automation-Macros.kmmacros` into Keyboard Maestro.",
            "9. Import the generated Hazel rules from `deploy/hazel/`.",
            "",
            f"Bundle root: `{deploy_root}`",
            hazel_line,
        ]
    )
    (bundle_dir / "deploy" / "DEPLOY.md").write_text(text + "\n", encoding="utf-8")


def _write_manifest(bundle_dir: Path, *, hazel_template: Path | None, archive_path: Path) -> None:
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "archive_path": str(archive_path),
        "bundle_root": str(bundle_dir),
        "hazel_template": str(hazel_template) if hazel_template else "",
        "hazel_rules": [f"deploy/hazel/{name}.hazelrules" for name in HAZEL_RULE_NAMES],
    }
    (bundle_dir / "deploy" / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def build_deploy_bundle(
    *,
    repo_root: Path,
    output_dir: Path,
    bundle_name: str,
    hazel_template: Path | None = None,
) -> dict[str, str]:
    repo_root = repo_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = (output_dir / bundle_name).resolve()
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    for relative in DEPLOY_COPY_PATHS:
        _copy_path(repo_root / relative, bundle_dir / relative)

    resolved_template = hazel_template.resolve() if hazel_template else discover_hazel_template()
    if resolved_template is None:
        raise FileNotFoundError(
            "No Hazel template rule was found. Export a MeetingCtl rule from Hazel or pass --hazel-template."
        )
    template_data = resolved_template.read_bytes()
    hazel_dir = bundle_dir / "deploy" / "hazel"
    hazel_dir.mkdir(parents=True, exist_ok=True)
    for rule_name in HAZEL_RULE_NAMES:
        (hazel_dir / f"{rule_name}.hazelrules").write_bytes(
            render_hazel_rule(template_data, rule_name=rule_name)
        )

    _write_deploy_readme(bundle_dir, resolved_template)
    archive_path = output_dir / f"{bundle_name}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    _write_manifest(bundle_dir, hazel_template=resolved_template, archive_path=archive_path)
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(bundle_dir, arcname=bundle_dir.name)
    return {
        "archive_path": str(archive_path),
        "bundle_dir": str(bundle_dir),
        "hazel_template": str(resolved_template),
    }


def default_bundle_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d")
    return f"meetingctl-deploy-{stamp}"
