#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _frontmatter_lines(text: str) -> list[str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, min(len(lines), 500)):
        if lines[i].strip() == "---":
            return lines[1:i]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Obsidian frontmatter tags usage.")
    parser.add_argument("vault", type=Path, help="Vault root path")
    parser.add_argument("--max-examples", type=int, default=40)
    args = parser.parse_args()

    stats: dict[str, int] = {
        "files_scanned": 0,
        "with_frontmatter": 0,
        "yaml_parse_errors_estimate": 0,
        "tags_missing": 0,
        "tags_scalar": 0,
        "tags_list": 0,
        "tags_inline_list": 0,
        "tags_block_list": 0,
    }

    scalar_examples: list[dict[str, str]] = []
    parse_error_examples: list[str] = []

    for path in args.vault.rglob("*.md"):
        stats["files_scanned"] += 1
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        frontmatter = _frontmatter_lines(text)
        if frontmatter is None:
            continue
        if frontmatter == []:
            stats["yaml_parse_errors_estimate"] += 1
            if len(parse_error_examples) < args.max_examples:
                parse_error_examples.append(str(path))
            continue

        stats["with_frontmatter"] += 1

        tags_idx = None
        tags_line = None
        for idx, line in enumerate(frontmatter):
            if re.match(r"^tags\s*:", line):
                tags_idx = idx
                tags_line = line
                break

        if tags_idx is None or tags_line is None:
            stats["tags_missing"] += 1
            continue

        value = tags_line.split(":", 1)[1].strip()

        if value.startswith("[") and value.endswith("]"):
            stats["tags_list"] += 1
            stats["tags_inline_list"] += 1
            continue

        if value == "":
            has_list_item = False
            j = tags_idx + 1
            while j < len(frontmatter):
                line = frontmatter[j]
                if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
                    break
                if re.match(r"^\s*-\s+\S", line):
                    has_list_item = True
                    break
                j += 1

            if has_list_item:
                stats["tags_list"] += 1
                stats["tags_block_list"] += 1
            else:
                stats["tags_scalar"] += 1
                if len(scalar_examples) < args.max_examples:
                    scalar_examples.append({"path": str(path), "tags_line": tags_line})
            continue

        stats["tags_scalar"] += 1
        if len(scalar_examples) < args.max_examples:
            scalar_examples.append({"path": str(path), "tags_line": tags_line})

    print(
        json.dumps(
            {
                "stats": stats,
                "scalar_examples": scalar_examples,
                "parse_error_examples": parse_error_examples,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
