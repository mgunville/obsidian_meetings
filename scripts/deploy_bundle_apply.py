#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from meetingctl.deploy import deploy_bundle  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply a MeetingCtl deploy bundle onto a target repo.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", default="", help="Path to a meetingctl-deploy-YYYYMMDD.tar.gz archive.")
    source.add_argument("--bundle-dir", default="", help="Path to an extracted deploy bundle directory.")
    parser.add_argument(
        "--target-dir",
        default="~/Dev/obsidian_meetings",
        help="Destination repo path to overwrite with the bundle contents.",
    )
    parser.add_argument("--skip-install", action="store_true", help="Copy bundle contents but do not run install.sh.")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = deploy_bundle(
            target_dir=Path(args.target_dir),
            archive_path=Path(args.archive) if args.archive else None,
            bundle_dir=Path(args.bundle_dir) if args.bundle_dir else None,
            run_install=not args.skip_install,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    if args.json:
        print(json.dumps(payload))
    else:
        print(f"target_dir={payload['target_dir']}")
        print(f"copied_entries={','.join(payload['copied_entries'])}")
        install = payload.get("install")
        if isinstance(install, dict):
            print(f"install_ok={install.get('ok')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
