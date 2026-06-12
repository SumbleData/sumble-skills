"""Stage 2a — resolve ICP terms to canonical Sumble slugs/names via the v6
lookup endpoints, replacing the RunSqlQuery name lookups.

  POST /v6/technologies/lookup   skill names/slugs/aliases -> {slug, name}
  POST /v6/jobs/title-lookup     job-function names (or any job titles)
                                 -> {job_function {slug, name},
                                     job_level {name, level_rank}}

Usage (comma-separated; flags repeatable):
  python lookup.py --skills clay,common-room,zoominfo \
                   --titles "Sales,Revenue Operations,Marketing"

Prints JSON: {"skills": [...], "job_functions": [...]}, each item
{input, slug, name}. Unmatched inputs are omitted — surface them to the user.
Auth: SUMBLE_API_KEY (or --env-file path, or the saved key file).
"""

from __future__ import annotations

import argparse
import json
import sys

import sumble_v6


def _split(vals: list[str]) -> list[str]:
    out: list[str] = []
    for v in vals or []:
        out += [s.strip() for s in v.split(",") if s.strip()]
    return out


def lookup_skills(api_key: str, names: list[str]) -> list[dict]:
    if not names:
        return []
    resp = sumble_v6.post(
        api_key, f"{sumble_v6.API_BASE}/technologies/lookup", {"technologies": names}
    )
    assert resp is not None
    out = []
    for r in resp.get("results", []):
        t = r.get("technology")
        if t:
            out.append({"input": r.get("input"), "slug": t.get("slug"), "name": t.get("name")})
    return out


def lookup_job_functions(api_key: str, titles: list[str]) -> list[dict]:
    """Map a job-function name (or any title) -> canonical job_function. The
    /v6/people query's `job_function` term is the display NAME (subtree-
    expanded server-side), so keep both slug and name."""
    if not titles:
        return []
    resp = sumble_v6.post(
        api_key, f"{sumble_v6.API_BASE}/jobs/title-lookup", {"titles": titles}
    )
    assert resp is not None
    return [
        {"input": r.get("input"), "slug": jf.get("slug"), "name": jf.get("name")}
        for r in resp.get("results", [])
        if (jf := r.get("job_function"))
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="Resolve ICP terms via v6 lookups.")
    ap.add_argument("--skills", action="append", default=[])
    ap.add_argument(
        "--titles",
        action="append",
        default=[],
        help="job-function names (or titles) -> canonical job_function",
    )
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    key = sumble_v6.resolve_api_key(args.env_file, allow_prompt=sys.stdin.isatty())
    if not key:
        sys.exit("No Sumble API key. Run set_api_key.py or export SUMBLE_API_KEY.")
    out = {
        "skills": lookup_skills(key, _split(args.skills)),
        "job_functions": lookup_job_functions(key, _split(args.titles)),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
