#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from meetingctl.deploy import build_deploy_bundle, default_bundle_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a clean-machine deployment bundle.")
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Directory where the bundle directory and tarball will be written.",
    )
    parser.add_argument(
        "--bundle-name",
        default="",
        help="Optional bundle directory/tarball base name. Defaults to meetingctl-deploy-YYYYMMDD.",
    )
    parser.add_argument(
        "--hazel-template",
        default="",
        help="Optional path to an exported MeetingCtl .hazelrules template.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    bundle_name = args.bundle_name.strip() or default_bundle_name()
    hazel_template = Path(args.hazel_template).expanduser() if args.hazel_template else None
    result = build_deploy_bundle(
        repo_root=repo_root,
        output_dir=(repo_root / args.output_dir).resolve(),
        bundle_name=bundle_name,
        hazel_template=hazel_template,
    )
    if args.json:
        print(json.dumps(result))
    else:
        print(f"bundle_dir={result['bundle_dir']}")
        print(f"archive_path={result['archive_path']}")
        print(f"hazel_template={result['hazel_template']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
