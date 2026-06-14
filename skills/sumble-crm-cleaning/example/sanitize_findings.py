"""Build this example's findings.json from a real CRM-cleaning run.

Copies the findings but replaces rep names with fictitious owners and the
customer flags with deterministic illustrative ones (same policy as the
account-scoring example: real companies, fictitious CRM-relationship data).

Usage:
  python3 sanitize_findings.py /path/to/real/findings.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

FAKE_OWNERS = ["Alex Rivera", "Jordan Lee", "Sam Patel", "Casey Kim", "Riley Chen"]


def _bucket(value: str, n: int) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest(), 16) % n


def scrub_account(a: dict) -> None:
    if a.get("owner"):
        a["owner"] = FAKE_OWNERS[_bucket(a["owner"], len(FAKE_OWNERS))]
    a["is_customer"] = _bucket(a.get("crm_account_id") or "", 6) == 0
    # Opportunity counts hint at real pipeline — drop them from the public
    # demo (the footprint then shows only contacts + activities).
    if "opportunity_count" in a:
        a["opportunity_count"] = 0


def main() -> None:
    src = Path(sys.argv[1])
    findings = json.loads(src.read_text())
    for d in findings["duplicates"]:
        for a in d["accounts"]:
            scrub_account(a)
    for p in findings["parent_sub"]:
        for key in ("child", "suggested_parent", "current_parent"):
            if p.get(key):
                scrub_account(p[key])
    for g in findings["parent_not_in_crm"]:
        for a in g["children"]:
            scrub_account(a)
    for a in findings["unmatched"]:
        scrub_account(a)

    out = Path(__file__).resolve().parent / "findings.json"
    out.write_text(json.dumps(findings, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
