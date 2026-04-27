#!/usr/bin/env python3
"""Validate local markdown links for README and docs.

Checks that relative local links point to files that exist.
Skips external links (http/https/mailto), in-page anchors, and fenced code blocks.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_GLOBS = ("README.md", "docs/**/*.md")

# Matches markdown links/images: [text](target) or ![alt](target)
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for glob in MARKDOWN_GLOBS:
        files.extend(ROOT.glob(glob))
    return sorted({path for path in files if path.is_file()})


def _normalize_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return unquote(target)


def _should_skip(target: str) -> bool:
    if not target:
        return True
    lowered = target.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("#")
    )


def _resolve_target(file_path: Path, target: str) -> Path:
    path_part = target.split("#", 1)[0]
    return (file_path.parent / path_part).resolve()


def main() -> int:
    markdown_files = _iter_markdown_files()
    missing: list[tuple[Path, int, str]] = []

    for file_path in markdown_files:
        in_fenced_block = False
        with file_path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if line.strip().startswith("```"):
                    in_fenced_block = not in_fenced_block
                    continue
                if in_fenced_block:
                    continue

                for match in LINK_PATTERN.finditer(line):
                    raw_target = match.group(1)
                    target = _normalize_target(raw_target)
                    if _should_skip(target):
                        continue

                    resolved = _resolve_target(file_path, target)
                    if not resolved.exists():
                        missing.append((file_path.relative_to(ROOT), line_no, raw_target))

    if missing:
        print("Broken markdown links found:")
        for rel_file, line_no, target in missing:
            print(f"- {rel_file}:{line_no} -> {target}")
        return 1

    print(f"Markdown links verified ({len(markdown_files)} files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
