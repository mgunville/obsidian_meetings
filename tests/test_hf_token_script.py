from __future__ import annotations

import os
from pathlib import Path
import subprocess


def test_hf_token_loader_uses_file_when_env_contains_op_reference(tmp_path: Path) -> None:
    token_file = tmp_path / "hf_token"
    token_file.write_text("hf-test-token\n", encoding="utf-8")
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "hf_token.sh"

    env = os.environ.copy()
    env["HUGGINGFACE_TOKEN"] = "op://team/example/token"
    env["MEETINGCTL_HF_TOKEN_FILE"] = str(token_file)

    result = subprocess.run(
        [
            "bash",
            "-lc",
            f'source "{script_path}"; meetingctl_load_hf_token_from_file; printf "%s" "${{HUGGINGFACE_TOKEN:-}}"',
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout == "hf-test-token"
