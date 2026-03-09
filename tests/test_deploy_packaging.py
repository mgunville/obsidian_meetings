from __future__ import annotations

from pathlib import Path
import plistlib

from meetingctl.deploy import (
    PORTABLE_HAZEL_SCRIPT,
    build_deploy_bundle,
    default_bundle_name,
    discover_hazel_template,
    render_hazel_rule,
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
