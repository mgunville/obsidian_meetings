from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "story_commit_slicing_report.py"


def run_report(tmp_path: Path, status_text: str) -> dict:
    status_file = tmp_path / "status.txt"
    out_file = tmp_path / "report.json"
    status_file.write_text(status_text)
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--status-file",
            str(status_file),
            "--write-json",
            str(out_file),
        ],
        check=True,
    )
    return json.loads(out_file.read_text())


def test_report_ignores_generated_files(tmp_path: Path) -> None:
    report = run_report(
        tmp_path,
        "\n".join(
            [
                " M src/meetingctl/cli.py",
                "?? docs/EXECUTION_PLAN.md",
                "?? tests/__pycache__/test_cli_smoke.cpython-311-pytest-9.0.2.pyc",
                "?? src/meetingctl.egg-info/PKG-INFO",
                "?? docs/STORY_COMMIT_SLICING_REPORT.json",
            ]
        ),
    )

    assert report["total_changed_files"] == 5
    assert len(report["ignored_files"]) == 4
    assert report["story_assignments"]["E1-S2"] == ["src/meetingctl/cli.py"]
    assert report["unmapped_files"] == []


def test_report_parses_rename_target_path(tmp_path: Path) -> None:
    report = run_report(
        tmp_path,
        "R  tests/test_start_wrapper.py -> tests/test_start_stop_flow.py\n",
    )

    # Both files map to E4-S3 and should be mapped without conflicts.
    assert report["conflicts"] == {}
    assert "E4-S3" in report["story_assignments"]
