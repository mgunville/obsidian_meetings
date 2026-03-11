from __future__ import annotations

import json
from pathlib import Path

from scripts import prune_orphan_artifacts


def test_prune_orphan_artifacts_reports_orphan_dirs_without_deleting(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes_dir = vault / "Meetings"
    notes_dir.mkdir(parents=True, exist_ok=True)
    artifacts_root = notes_dir / "_artifacts"
    keep_dir = artifacts_root / "m-aaaaaaaaaa"
    drop_dir = artifacts_root / "m-bbbbbbbbbb"
    keep_dir.mkdir(parents=True, exist_ok=True)
    drop_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "2026-03-11 0900 - Keep - m-aaaaaaaaaa.md").write_text("# keep", encoding="utf-8")

    args = prune_orphan_artifacts.build_parser().parse_args(
        ["--vault-path", str(vault), "--json"]
    )
    payload = prune_orphan_artifacts.run(args)

    assert payload["discovered_orphan_dirs"] == 1
    assert payload["deleted_dirs"] == 0
    assert str(drop_dir.resolve()) in payload["orphans"]
    assert drop_dir.exists()


def test_prune_orphan_artifacts_deletes_orphan_dirs_and_honors_frontmatter(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    client_dir = vault / "_Work" / "AHEAD" / "Clients" / "Contoso"
    client_dir.mkdir(parents=True, exist_ok=True)
    artifacts_root = vault / "Meetings" / "_artifacts"
    keep_dir = artifacts_root / "m-cccccccccc"
    drop_dir = artifacts_root / "m-dddddddddd"
    keep_dir.mkdir(parents=True, exist_ok=True)
    drop_dir.mkdir(parents=True, exist_ok=True)
    (keep_dir / "m-cccccccccc.txt").write_text("keep", encoding="utf-8")
    (drop_dir / "m-dddddddddd.txt").write_text("drop", encoding="utf-8")
    (client_dir / "Moved Meeting.md").write_text(
        "\n".join(
            [
                "---",
                'meeting_id: "m-cccccccccc"',
                "---",
                "# moved",
            ]
        ),
        encoding="utf-8",
    )

    args = prune_orphan_artifacts.build_parser().parse_args(
        ["--vault-path", str(vault), "--apply", "--json"]
    )
    payload = prune_orphan_artifacts.run(args)

    assert payload["discovered_orphan_dirs"] == 1
    assert payload["deleted_dirs"] == 1
    assert keep_dir.exists()
    assert not drop_dir.exists()
    report = json.loads(Path(payload["report_path"]).read_text(encoding="utf-8"))
    assert report["deleted_dirs"] == 1
