from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import plistlib
import shutil
import tarfile


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


def _write_deploy_readme(bundle_dir: Path, hazel_template: Path | None) -> None:
    deploy_root = bundle_dir.name
    hazel_line = "Auto-generated from local Hazel template discovery."
    if hazel_template is not None:
        hazel_line = f"Generated from: {hazel_template}"
    text = "\n".join(
        [
            "# Deploy Bundle",
            "",
            "1. Extract this bundle on the destination Mac into `~/Dev/obsidian_meetings` or set `MEETINGCTL_REPO` to the extracted path.",
            "2. Run `bash install.sh` from the extracted repo root.",
            "3. Fill in `~/.config/meetingctl/env` and run `bash scripts/meetingctl_cli.sh doctor --json`.",
            "4. Import `config/km/Meeting-Automation-Macros.kmmacros` into Keyboard Maestro.",
            "5. Import the generated Hazel rules from `deploy/hazel/`.",
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
