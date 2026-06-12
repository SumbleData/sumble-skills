"""Shared helpers for the unified Sumble v6 people endpoints.

Single source of truth for: API-key resolution, the HTTP POST helper, the
person-attribute selection (and its per-person credit cost), the canonical
job-level -> rank map, the people advanced-query builder, and how a response
person row flattens into `data.csv` columns (`build_person_row`).
`fetch_people.py`, `merge_data.py`, `build_config.py` and `fit_weights.py` all
import from here so the fetched payload, the merged columns and the config's
column references can never drift apart.

Endpoints used (documented in api/app/routers/paid_api/people_unified.py and
api/app/routers/paid_api/organizations.py):
  POST /v6/people          unified people endpoint (match mode + filter mode)
  POST /v6/organizations   org match (calibration companies -> org_ids)
  POST /v6/technologies/lookup, /v6/jobs/title-lookup   (lookup.py)

Pricing (from the endpoint schema): every returned person costs 1 base credit
plus 1 credit per paid attribute (`name` is free). Identifying a person by
email costs EMAIL_RESOLUTION_CREDITS extra when it resolves (and is limited to
25-person batches).
"""

from __future__ import annotations

import datetime as _dt
import getpass
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.sumble.com/v6"
PEOPLE_URL = f"{API_BASE}/people"
ORGS_URL = f"{API_BASE}/organizations"

# Where a saved key is read from / written to. First existing wins on read;
# the interactive prompt writes the durable ~/.config path.
_KEY_CONFIG = Path.home() / ".config" / "sumble" / "api_key"


def _key_file_candidates() -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("SUMBLE_API_KEY_FILE")
    if explicit:
        paths.append(Path(explicit))
    paths.append(_KEY_CONFIG)
    tmp = os.environ.get("TMPDIR")
    if tmp:
        paths.append(Path(tmp) / "sumble_api_key")
    paths.append(Path(".sumble_api_key"))
    return paths


def _read_env_file(path: str) -> str | None:
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("SUMBLE_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


def save_api_key(key: str) -> Path:
    """Write the key to ~/.config/sumble/api_key with 0600 perms."""
    _KEY_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _KEY_CONFIG.write_text(key.strip() + "\n")
    _KEY_CONFIG.chmod(0o600)
    return _KEY_CONFIG


def saved_key() -> str | None:
    """Return a key persisted to a key file (NOT env) — i.e. one that survives
    across sessions. Used to decide whether a fresh save is still needed."""
    for p in _key_file_candidates():
        if p.exists():
            k = p.read_text().strip()
            if k:
                return k
    return None


def resolve_api_key(env_file: str | None = None, allow_prompt: bool = False) -> str | None:
    """Find the Sumble API key: env var -> --env-file -> saved key file -> prompt.

    `allow_prompt` only triggers an interactive getpass when stdin is a TTY (so
    it never hangs an unattended/agent run); the entered key is saved for reuse.
    """
    key = os.environ.get("SUMBLE_API_KEY")
    if key:
        return key.strip()
    if env_file and Path(env_file).exists():
        k = _read_env_file(env_file)
        if k:
            return k
    file_key = saved_key()
    if file_key:
        return file_key
    if allow_prompt and sys.stdin.isatty():
        sys.stderr.write(
            "\nGet your Sumble API key at https://sumble.com/account "
            "(Account → API key).\n"
        )
        entered = getpass.getpass("Paste it here (hidden; saved for next time): ").strip()
        if entered:
            dest = save_api_key(entered)
            sys.stderr.write(f"[key] saved to {dest}\n")
            return entered
    return None


def post(
    api_key: str, url: str, body: dict, *, retries: int = 4, fatal: bool = True
) -> dict | None:
    """POST JSON with retry/backoff on transient failures."""
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            if not fatal:
                print(f"[post] HTTP {e.code} (non-fatal): {detail}")
                return None
            sys.exit(f"[post] HTTP {e.code} on {url}: {detail}")
        except (
            urllib.error.URLError,
            TimeoutError,
            http.client.IncompleteRead,
            http.client.HTTPException,
            ConnectionError,
            OSError,
        ) as e:
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            if not fatal:
                return None
            sys.exit(f"[post] network error on {url}: {e}")
    if fatal:
        raise SystemExit("[post] exhausted retries")
    return None


# --- Person attribute selection + pricing --------------------------------------

# Full attribute set for calibration pulls. `name` is free; every other listed
# attribute costs 1 credit per returned person on top of the 1-credit base.
# `technologies` is the person's LinkedIn skills normalized to Sumble's
# technology catalog — the source of the matched-skills factor.
PERSON_ATTRIBUTES = [
    "name",
    "linkedin_url",
    "job_title",
    "job_function",
    "job_level",
    "location",
    "country",
    "current_employer",
    "technologies",
]

# Lean set for large production runs: only what the score + joins need
# (jf/level/technologies to score, linkedin_url to join, current_employer for
# the account factor). Saves 3 credits per person vs the full set.
PERSON_ATTRIBUTES_LEAN = [
    "name",
    "linkedin_url",
    "job_function",
    "job_level",
    "current_employer",
    "technologies",
]

_FREE_ATTRIBUTES = {"name"}

# Identifying a person by email (no person_id / linkedin_url) runs reverse
# enrichment: 20 extra credits per resolved person, max 25 such rows per call.
EMAIL_RESOLUTION_CREDITS = 20
EMAIL_BATCH = 25
MATCH_BATCH = 1000  # match-mode max people per request (linkedin_url/person_id)
FILTER_PAGE = 200  # filter-mode max limit per page
FILTER_MAX_OFFSET = 10_000  # filter-mode limit+offset cap (per org we paginate)


def per_person_credits(attributes: list[str]) -> int:
    """1 base credit + 1 per paid attribute (deduped; `name` free)."""
    return 1 + sum(1 for a in set(attributes) if a not in _FREE_ATTRIBUTES)


# --- Canonical job-level rank map ----------------------------------------------

# Mirror of the `job_levels` reference table (id, name, level_rank). The v6
# people endpoints return `job_level` as the display NAME without its rank, so
# the rank used by the seniority factor is resolved through this map. The
# taxonomy is small and stable; "Individual Contributor" covers people with no
# detected level.
JOB_LEVEL_RANKS: dict[str, int] = {
    "Individual Contributor": 0,
    "Senior": 1,
    "Lead": 2,
    "Principal": 3,
    "Manager": 4,
    "Senior Manager": 5,
    "Associate Director": 6,
    "Head": 7,
    "General Manager": 8,
    "Director": 9,
    "Senior Director": 10,
    "Board Member": 11,
    "Executive Director": 11,
    "AVP": 13,
    "VP": 14,
    "SVP": 15,
    "CXO": 18,
}
MAX_JOB_LEVEL_RANK = max(JOB_LEVEL_RANKS.values())


def job_level_rank(level_name: str | None) -> int:
    """Rank for a job-level display name; unknown/missing -> 0 (IC)."""
    if not level_name:
        return 0
    return JOB_LEVEL_RANKS.get(str(level_name).strip(), 0)


# --- Advanced-query DSL helpers -------------------------------------------------


def _q(value: str) -> str:
    """Single-quote a DSL literal, escaping any embedded single quotes."""
    return "'" + value.replace("'", "''") + "'"


def _in_list(values: list[str]) -> str:
    return "(" + ", ".join(_q(v) for v in values) + ")"


def people_query(jf_names: list[str], min_level_name: str | None) -> str:
    """People filter query: ICP job functions + optional seniority floor.

    `job_function EQ '<Name>'` matches the whole descendant subtree server-side
    (a person tagged with a leaf function is indexed under every ancestor), so
    seed function names are enough — no recursive expansion needed.
    `job_level_min EQ '<Name>'` resolves to every level with level_rank >= the
    named level's rank.
    """
    parts: list[str] = []
    if jf_names:
        parts.append(f"job_function IN {_in_list(jf_names)}")
    if min_level_name and job_level_rank(min_level_name) > 0:
        parts.append(f"job_level_min EQ {_q(min_level_name)}")
    if not parts:
        sys.exit("[query] refusing to build an empty people query (no JFs, no floor)")
    return " AND ".join(parts)


# --- LinkedIn URL canonicalisation ----------------------------------------------

_LI_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)


def li_slug(url: str | None) -> str | None:
    """Lower-cased LinkedIn profile slug from any /in/ URL form, else None."""
    if not url or not isinstance(url, str):
        return None
    m = _LI_RE.search(url.strip().lower())
    return m.group(1) if m else None


def canonical_linkedin_url(slug: str) -> str:
    return f"https://www.linkedin.com/in/{slug}"


# --- Response row -> data.csv columns -------------------------------------------


def slugify(name: str | None) -> str:
    """Display name -> slug (matches Sumble's job-function slugs for the
    common cases, e.g. 'Revenue Operations' -> 'revenue-operations')."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9]+", "-", str(name).strip().lower())
    return s.strip("-")


def build_person_row(
    resp_row: dict,
    jf_slug_by_name: dict[str, str],
    icp_skill_slugs: set[str] | None = None,
) -> dict | None:
    """Flatten one matched person from a /v6/people response into the common
    data.csv columns. Returns None for an unmatched row (no person_id).

    `jf_slug_by_name` maps ICP job-function display names to their canonical
    slugs (from spec.json); other functions fall back to `slugify(name)`.
    `icp_skill_slugs` filters the person's `technologies` attribute (LinkedIn
    skills normalized to Sumble's catalog) down to the matched-skills factor
    columns. The caller adds flags (is_crm_contact / is_icp_gold), account
    columns and 1P signal columns.
    """
    person_id = resp_row.get("person_id")
    if not person_id:
        return None
    attrs = resp_row.get("attributes") or {}
    employer = attrs.get("current_employer") or {}
    jf_name = attrs.get("job_function") or ""
    level = attrs.get("job_level") or ""
    rank = job_level_rank(level)
    icp_skill_slugs = icp_skill_slugs or set()
    person_tech_slugs = [
        t.get("slug") for t in (attrs.get("technologies") or []) if t.get("slug")
    ]
    matched = sorted({s for s in person_tech_slugs if s in icp_skill_slugs})
    return {
        "person_id": int(person_id),
        "name": attrs.get("name") or "",
        "current_title": attrs.get("job_title") or "",
        "linkedin_url": attrs.get("linkedin_url") or "",
        "sumble_url": resp_row.get("sumble_url") or "",
        "location": attrs.get("location") or "",
        "country": attrs.get("country") or "",
        "org_id": employer.get("organization_id") or "",
        "org_name": employer.get("name") or "",
        "org_sumble_url": employer.get("sumble_url") or "",
        "job_function_name": jf_name,
        "job_function_slug": jf_slug_by_name.get(jf_name, slugify(jf_name)),
        "job_level": level or "Individual Contributor",
        "job_level_rank": rank,
        "max_job_level_rank": MAX_JOB_LEVEL_RANK,
        "matched_skills": ",".join(matched),
        "skill_count": len(matched),
    }


def today_iso() -> str:
    return _dt.date.today().isoformat()
