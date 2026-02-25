#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _split_frontmatter(text: str) -> tuple[list[str] | None, int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, -1
    for i in range(1, min(len(lines), 500)):
        if lines[i].strip() == "---":
            return lines, i
    return [], -1


def _sanitize_token(token: str) -> str:
    cleaned = token.strip()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    return cleaned


def _is_bare_year(tag: str) -> bool:
    raw = tag.strip().strip('"').strip("'")
    return bool(re.fullmatch(r"\d{4}", raw))


def _extract_scalar_tokens(value: str) -> tuple[list[str], str | None]:
    raw = value.strip()
    if not raw:
        return [], "empty"
    if "<%" in raw or "%>" in raw:
        return [], "templater"
    if "[" in raw or "]" in raw:
        return [], "inline-list-like"
    if "," in raw:
        return [], "comma-delimited-ambiguous"

    tokens = [_sanitize_token(tok) for tok in raw.split()]
    tokens = [tok for tok in tokens if tok]
    if not tokens:
        return [], "empty"
    return tokens, None


def _render_block_list(tags: list[str]) -> list[str]:
    rendered = ["tags:"]
    for tag in tags:
        rendered.append(f"  - {tag}")
    return rendered


def _extract_block_list(frontmatter: list[str], tags_idx: int) -> tuple[list[str], int]:
    items: list[str] = []
    j = tags_idx + 1
    while j < len(frontmatter):
        line = frontmatter[j]
        if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
            break
        m = re.match(r"^\s*-\s+(.*)$", line)
        if m:
            items.append(m.group(1).strip())
        j += 1
    return items, j


def _extract_inline_list(value: str) -> list[str]:
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    return [part.strip() for part in inner.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize scalar frontmatter tags to YAML block lists.")
    parser.add_argument("vault", type=Path)
    parser.add_argument("--write", action="store_true", help="Apply edits. Default is dry-run.")
    parser.add_argument("--report", type=Path, help="Write JSON report.")
    parser.add_argument("--max-examples", type=int, default=100)
    parser.add_argument(
        "--exclude-substring",
        action="append",
        default=[],
        help="Skip files whose paths contain this substring. Repeatable.",
    )
    parser.add_argument(
        "--include-substring",
        action="append",
        default=[],
        help="Only process files whose paths contain one of these substrings. Repeatable.",
    )
    parser.add_argument(
        "--drop-year-tags",
        action="store_true",
        help="Remove bare 4-digit year tags (e.g., 2026).",
    )
    args = parser.parse_args()

    report: dict[str, object] = {
        "files_scanned": 0,
        "frontmatter_files": 0,
        "unchanged": 0,
        "converted": 0,
        "skipped_no_tags": 0,
        "skipped_already_list": 0,
        "skipped_ambiguous": 0,
        "ambiguous_reasons": {},
        "examples_converted": [],
        "examples_ambiguous": [],
        "write_mode": args.write,
    }

    for path in args.vault.rglob("*.md"):
        p = str(path)
        if args.include_substring and not any(sub in p for sub in args.include_substring):
            continue
        if any(sub in p for sub in args.exclude_substring):
            continue
        report["files_scanned"] = int(report["files_scanned"]) + 1

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        lines, fm_end = _split_frontmatter(text)
        if lines is None:
            continue
        if lines == []:
            report["unchanged"] = int(report["unchanged"]) + 1
            continue
        report["frontmatter_files"] = int(report["frontmatter_files"]) + 1

        fm = lines[1:fm_end]
        tags_idx = None
        tags_line = None
        for idx, line in enumerate(fm):
            if re.match(r"^tags\s*:", line):
                tags_idx = idx
                tags_line = line
                break

        if tags_idx is None or tags_line is None:
            report["skipped_no_tags"] = int(report["skipped_no_tags"]) + 1
            continue

        value = tags_line.split(":", 1)[1].strip()
        tags: list[str]
        reason: str | None = None
        end_idx = tags_idx + 1

        if value.startswith("[") and value.endswith("]"):
            tags = _extract_inline_list(value)
        elif value == "":
            tags, end_idx = _extract_block_list(fm, tags_idx)
            if not tags:
                reason = "empty"
        else:
            tags, reason = _extract_scalar_tokens(value)

        if reason is not None:
            report["skipped_ambiguous"] = int(report["skipped_ambiguous"]) + 1
            reasons = dict(report["ambiguous_reasons"])
            reasons[reason] = int(reasons.get(reason, 0)) + 1
            report["ambiguous_reasons"] = reasons
            if len(report["examples_ambiguous"]) < args.max_examples:
                report["examples_ambiguous"].append({"path": p, "tags_line": tags_line, "reason": reason})
            continue

        if args.drop_year_tags:
            tags = [tag for tag in tags if not _is_bare_year(tag)]

        replacement = _render_block_list(tags)
        new_fm = fm[:tags_idx] + replacement + fm[end_idx:]
        new_lines = ["---"] + new_fm + ["---"] + lines[fm_end + 1 :]
        new_text = "\n".join(new_lines)
        if text.endswith("\n"):
            new_text += "\n"

        if new_text == text:
            report["skipped_already_list"] = int(report["skipped_already_list"]) + 1
            continue

        if args.write:
            path.write_text(new_text, encoding="utf-8")

        report["converted"] = int(report["converted"]) + 1
        if len(report["examples_converted"]) < args.max_examples:
            report["examples_converted"].append(
                {
                    "path": p,
                    "from": tags_line,
                    "to": replacement,
                }
            )

    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
