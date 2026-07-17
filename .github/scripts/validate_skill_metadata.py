#!/usr/bin/env python3
"""Validate SKILL.md frontmatter against the Agent Skills platform's hard limits.

The Claude / Agent Skills loader rejects a skill whose frontmatter is invalid:
  - name:        64 characters max; lowercase letters, numbers, and hyphens only
  - description: 1024 characters max

An over-long description silently breaks the skill (and ships a broken zip via
the build-skill-zips workflow), so we gate it in CI before it can merge.

Run locally from the repo root:
    python3 .github/scripts/validate_skill_metadata.py

Exits non-zero and lists every violation if any SKILL.md is out of bounds.
Emits GitHub Actions ::error annotations so failures surface inline on the PR.
"""

from __future__ import annotations

import glob
import re
import sys

try:
    import yaml  # PyYAML: correct scalar semantics for quoted / plain / block forms.
except ModuleNotFoundError:  # pragma: no cover - CI installs it; guard for bare envs.
    sys.stderr.write(
        "PyYAML is required: pip install pyyaml (CI does this automatically).\n"
    )
    raise SystemExit(2)

NAME_MAX = 64
DESC_MAX = 1024
NAME_PATTERN = re.compile(r"[a-z0-9-]+")  # lowercase letters, numbers, hyphens only
SKILL_GLOB = "skills/**/SKILL.md"


def parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter mapping delimited by the leading '---' fences."""
    if not text.startswith("---"):
        raise ValueError("missing YAML frontmatter (no leading '---')")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("unterminated YAML frontmatter (no closing '---')")
    data = yaml.safe_load(parts[1])
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data


def check_file(path: str) -> list[str]:
    """Return a list of human-readable violation messages for one SKILL.md."""
    try:
        with open(path, encoding="utf-8") as fh:
            fm = parse_frontmatter(fh.read())
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [f"cannot parse frontmatter: {exc}"]

    problems: list[str] = []

    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("missing or empty 'name'")
    else:
        if len(name) > NAME_MAX:
            problems.append(f"name is {len(name)} chars (max {NAME_MAX})")
        if not NAME_PATTERN.fullmatch(name):
            problems.append(
                f"name {name!r} must be lowercase letters, numbers, and hyphens only"
            )

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        problems.append("missing or empty 'description'")
    elif len(desc) > DESC_MAX:
        over = len(desc) - DESC_MAX
        problems.append(f"description is {len(desc)} chars (max {DESC_MAX}, {over} over)")

    return problems


def main() -> int:
    paths = sorted(glob.glob(SKILL_GLOB, recursive=True))
    if not paths:
        sys.stderr.write(f"No SKILL.md files matched {SKILL_GLOB!r}\n")
        return 1

    failed = False
    for path in paths:
        problems = check_file(path)
        if problems:
            failed = True
            for msg in problems:
                # GitHub Actions annotation (surfaces inline on the PR diff).
                print(f"::error file={path}::{msg}")
                print(f"FAIL {path}: {msg}", file=sys.stderr)
        else:
            print(f"ok   {path}")

    if failed:
        sys.stderr.write(
            f"\nSKILL.md metadata validation failed "
            f"(name<={NAME_MAX}, description<={DESC_MAX}).\n"
        )
        return 1

    print(f"\nAll {len(paths)} SKILL.md file(s) within limits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
