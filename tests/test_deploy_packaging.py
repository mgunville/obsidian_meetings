from __future__ import annotations

from pathlib import Path
import plistlib
import subprocess

from meetingctl.deploy import (
    PORTABLE_HAZEL_SCRIPT,
    build_deploy_bundle,
    deploy_bundle,
    default_bundle_name,
    discover_hazel_template,
    render_hazel_rule,
    sync_bundle_to_target,
)


def _hazel_template_bytes(*, rule_name: str = "MeetingCtl - Ingest Notes Audio") -> bytes:
    payload = {
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": 1},
        "$objects": [
            "$null",
            {
                "description": rule_name,
                "script": (
                    b'REPO_ROOT="/tmp/original"\n'
                    b'bash "$REPO_ROOT/scripts/hazel_ingest_file.sh" "$1"\n'
                ),
            },
        ],
    }
    return b"HZLR" + (27).to_bytes(4, "big") + b"0123456789abcdef0123456789abcdef" + plistlib.dumps(
        payload,
        fmt=plistlib.FMT_BINARY,
        sort_keys=False,
    )


def test_render_hazel_rule_rewrites_name_and_script() -> None:
    rendered = render_hazel_rule(
        _hazel_template_bytes(),
        rule_name="MeetingCtl - Ingest Voice Memos",
    )

    prefix = rendered[: rendered.index(b"bplist00")]
    payload = plistlib.loads(rendered[len(prefix) :])
    assert prefix.startswith(b"HZLR")
    assert payload["$objects"][1]["description"] == "MeetingCtl - Ingest Voice Memos"
    assert payload["$objects"][1]["script"] == PORTABLE_HAZEL_SCRIPT.encode("utf-8")


def test_discover_hazel_template_finds_matching_rule(tmp_path: Path) -> None:
    other = tmp_path / "other.hazelrules"
    other.write_bytes(plistlib.dumps({"name": "Other Rule"}, fmt=plistlib.FMT_BINARY))
    template = tmp_path / "notes_audio.hazelrules"
    template.write_bytes(_hazel_template_bytes())

    discovered = discover_hazel_template([tmp_path])

    assert discovered == template


def test_build_deploy_bundle_writes_expected_artifacts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template = tmp_path / "template.hazelrules"
    template.write_bytes(_hazel_template_bytes())

    result = build_deploy_bundle(
        repo_root=repo_root,
        output_dir=tmp_path,
        bundle_name=default_bundle_name(),
        hazel_template=template,
    )

    bundle_dir = Path(result["bundle_dir"])
    archive_path = Path(result["archive_path"])
    assert bundle_dir.exists()
    assert archive_path.exists()
    assert (bundle_dir / "deploy" / "hazel" / "MeetingCtl - Ingest Notes Audio.hazelrules").exists()
    assert (bundle_dir / "deploy" / "hazel" / "MeetingCtl - Ingest Voice Memos.hazelrules").exists()
    assert (bundle_dir / "config" / "km" / "Meeting-Automation-Macros.kmmacros").exists()
    assert not (bundle_dir / "config" / "models" / "whisperx").exists()
    assert (bundle_dir / "docs" / "HAZEL_SETUP.md").exists()
    assert (bundle_dir / "deploy" / "manifest.json").exists()
    deploy_readme = (bundle_dir / "deploy" / "DEPLOY.md").read_text(encoding="utf-8")
    assert "MEETINGCTL_REPO" in deploy_readme
    assert "RECORDINGS_PATH=~/Notes/audio" in deploy_readme
    assert "no Hugging Face MCP server is needed" in deploy_readme
    assert "python3 scripts/deploy_bundle_apply.py --bundle-dir . --target-dir ~/Dev/obsidian_meetings" in deploy_readme


def test_sync_bundle_to_target_replaces_managed_paths_and_preserves_unmanaged(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (bundle_dir / "README.md").write_text("new readme\n", encoding="utf-8")
    docs_dir = bundle_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("fresh docs\n", encoding="utf-8")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("old readme\n", encoding="utf-8")
    stale_docs = target_dir / "docs"
    stale_docs.mkdir()
    (stale_docs / "obsolete.md").write_text("stale\n", encoding="utf-8")
    shared_data = target_dir / "shared_data"
    shared_data.mkdir()
    (shared_data / "keep.txt").write_text("preserve\n", encoding="utf-8")
    venv = target_dir / ".venv"
    venv.mkdir()
    (venv / "marker").write_text("preserve\n", encoding="utf-8")

    result = sync_bundle_to_target(bundle_dir, target_dir)

    assert result["target_dir"] == str(target_dir.resolve())
    assert (target_dir / "README.md").read_text(encoding="utf-8") == "new readme\n"
    assert (target_dir / "docs" / "guide.md").read_text(encoding="utf-8") == "fresh docs\n"
    assert not (target_dir / "docs" / "obsolete.md").exists()
    assert (target_dir / "shared_data" / "keep.txt").read_text(encoding="utf-8") == "preserve\n"
    assert (target_dir / ".venv" / "marker").read_text(encoding="utf-8") == "preserve\n"


def test_deploy_bundle_runs_install_after_sync(monkeypatch, tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (bundle_dir / "README.md").write_text("bundle\n", encoding="utf-8")
    target_dir = tmp_path / "target"

    calls: list[tuple[list[str], str]] = []

    def _runner(args, cwd=None, check=False, capture_output=True, text=True):
        calls.append((list(args), str(cwd)))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("meetingctl.deploy.subprocess.run", _runner)

    result = deploy_bundle(bundle_dir=bundle_dir, target_dir=target_dir)

    assert (target_dir / "README.md").read_text(encoding="utf-8") == "bundle\n"
    assert calls == [(["bash", "install.sh"], str(target_dir.resolve()))]
    assert result["install"]["ok"] is True
