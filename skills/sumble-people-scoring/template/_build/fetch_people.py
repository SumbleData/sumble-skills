"""Stage 2 — fetch all calibration people from the unified v6 endpoints.

Replaces the old RunSqlQuery people pull + the linkedin_url equality-join SQL
+ the v5 reverse-enrichment fallback. Two endpoints, no SQL:

  POST /v6/organizations  match the ~5 calibration companies -> org_ids
  POST /v6/people         filter mode: people at those org_ids matching the
                          ICP query (paths b/c)
                          match mode: resolve 1P contacts by linkedin_url /
                          person_id / email (paths a/b, gold lists)

Inputs (all under --raw):
  spec.json        ICP + calibration companies + path (see _build/README.md)
  contacts.csv     optional 1P contact rows (paths a/b):
                   contact_id,name,linkedin_url,email,is_gold
  gold.csv         optional gold list for path c (same columns, no is_gold —
                   every row is gold)

Writes:
  _raw/org_matches.json        [{input_name, input_domain, org_id, name, slug,
                                 url, sumble_url}]
  _raw/responses/people_*.json raw endpoint responses (one per page/batch)
  _raw/fetch_index.json        [{file, kind, org_id?}] manifest for merge

Credits: every returned person costs `1 + paid-attributes` (8 with the full
attribute set, 5 with --lean). Email-only contact rows cost
EMAIL_RESOLUTION_CREDITS (20) extra each when they resolve and are SKIPPED
unless --resolve-emails is passed. Run --estimate-only first: it probes the
people counts with a free-ish 1-credit-per-org query and prints the credit
estimate without enriching anything.

Usage:
  python fetch_people.py --raw <abs>/_raw --estimate-only
  python fetch_people.py --raw <abs>/_raw
  python fetch_people.py --raw <abs>/_raw --resolve-emails
  python fetch_people.py --raw <abs>/_raw --lean        # big production pulls
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import sumble_v6


def load_api_key(env_file: str | None) -> str:
    key = sumble_v6.resolve_api_key(env_file, allow_prompt=sys.stdin.isatty())
    if not key:
        sys.exit(
            "No Sumble API key found. Run `python set_api_key.py` (prompts for the "
            "key and saves it), or `export SUMBLE_API_KEY=...`, or pass "
            "--env-file path/to/.env, then re-run."
        )
    return key


def _clear_responses(raw: Path) -> Path:
    resp_dir = raw / "responses"
    resp_dir.mkdir(parents=True, exist_ok=True)
    for old in resp_dir.glob("people_*.json"):
        old.unlink()
    return resp_dir


def match_companies(raw: Path, spec: dict, api_key: str) -> list[dict]:
    """Resolve spec.calibration_companies -> Sumble org_ids via
    /v6/organizations match mode (1 credit per matched org)."""
    companies = spec.get("calibration_companies") or []
    if not companies:
        sys.exit("[fetch] spec.calibration_companies is empty — nothing to match.")
    orgs = [
        {"name": c.get("name") or "", "url": c.get("domain") or c.get("url") or ""}
        for c in companies
    ]
    body = {
        "organizations": orgs,
        "select": {"attributes": ["id", "name", "slug", "url"], "entities": []},
    }
    resp = sumble_v6.post(api_key, sumble_v6.ORGS_URL, body)
    assert resp is not None
    matches: list[dict] = []
    for comp, ro in zip(companies, resp.get("organizations") or []):
        attrs = ro.get("attributes") or {}
        if attrs.get("id"):
            matches.append(
                {
                    "input_name": comp.get("name") or "",
                    "input_domain": comp.get("domain") or comp.get("url") or "",
                    "org_id": int(attrs["id"]),
                    "name": attrs.get("name") or "",
                    "slug": attrs.get("slug") or "",
                    "url": attrs.get("url") or "",
                    "sumble_url": ro.get("sumble_url") or "",
                }
            )
        else:
            print(f"[fetch] UNMATCHED company: {comp.get('name')} ({comp.get('domain')})")
    (raw / "org_matches.json").write_text(json.dumps(matches, indent=2))
    print(f"[fetch] matched {len(matches)}/{len(companies)} calibration companies.")
    return matches


def count_people(api_key: str, org_id: int, query: str) -> int:
    """Free-ish people count at one org (limit 1, no paid attributes -> 1 credit)."""
    body = {
        "filter": {"organization_ids": [org_id], "query": {"query": query}},
        "select": {"attributes": []},
        "limit": 1,
    }
    resp = sumble_v6.post(api_key, sumble_v6.PEOPLE_URL, body, fatal=False)
    return int(resp.get("total") or 0) if resp else 0


def pull_org_people(
    api_key: str,
    org_id: int,
    query: str,
    attributes: list[str],
    resp_dir: Path,
    index: list[dict],
) -> int:
    """Filter-mode pull: every person at `org_id` matching `query` (paginated)."""
    fetched = 0
    page = 0
    while True:
        offset = page * sumble_v6.FILTER_PAGE
        if offset + sumble_v6.FILTER_PAGE > sumble_v6.FILTER_MAX_OFFSET:
            print(f"[fetch] org {org_id}: hit the {sumble_v6.FILTER_MAX_OFFSET} "
                  "offset cap — tighten the seniority floor if you need them all.")
            break
        body = {
            "filter": {"organization_ids": [org_id], "query": {"query": query}},
            "select": {"attributes": attributes},
            "limit": sumble_v6.FILTER_PAGE,
            "offset": offset,
        }
        resp = sumble_v6.post(api_key, sumble_v6.PEOPLE_URL, body)
        assert resp is not None
        people = resp.get("people") or []
        if not people:
            break
        fname = f"people_org{org_id}_p{page:03d}.json"
        (resp_dir / fname).write_text(json.dumps(resp))
        index.append({"file": fname, "kind": "org_people", "org_id": org_id})
        fetched += len(people)
        page += 1
        if len(people) < sumble_v6.FILTER_PAGE:
            break
    print(f"[fetch] org {org_id}: {fetched} people.")
    return fetched


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def resolve_contacts(
    rows: list[dict],
    kind: str,
    api_key: str,
    attributes: list[str],
    resp_dir: Path,
    index: list[dict],
    resolve_emails: bool,
) -> None:
    """Match-mode resolution of 1P contact rows.

    Rows with a linkedin_url go in MATCH_BATCH-person batches; email-only rows
    are restricted by the endpoint to 25-person batches and cost
    EMAIL_RESOLUTION_CREDITS extra each, so they only run with --resolve-emails.
    Unmatched entries come back with their input echoed (free).
    """
    with_url = [r for r in rows if sumble_v6.li_slug(r.get("linkedin_url"))]
    email_only = [
        r for r in rows
        if not sumble_v6.li_slug(r.get("linkedin_url")) and (r.get("email") or "").strip()
    ]
    unresolvable = len(rows) - len(with_url) - len(email_only)
    if unresolvable:
        print(f"[fetch] {kind}: {unresolvable} rows have neither linkedin_url nor "
              "email — they cannot be resolved and are skipped.")

    batch_no = 0
    for bi in range(0, len(with_url), sumble_v6.MATCH_BATCH):
        chunk = with_url[bi : bi + sumble_v6.MATCH_BATCH]
        people = [
            {
                "linkedin_url": sumble_v6.canonical_linkedin_url(
                    sumble_v6.li_slug(r["linkedin_url"]) or ""
                )
            }
            for r in chunk
        ]
        body = {"people": people, "select": {"attributes": attributes}}
        resp = sumble_v6.post(api_key, sumble_v6.PEOPLE_URL, body)
        assert resp is not None
        fname = f"people_{kind}_url_b{batch_no:03d}.json"
        (resp_dir / fname).write_text(json.dumps(resp))
        index.append({"file": fname, "kind": kind})
        print(
            f"[fetch] {kind} url batch {batch_no}: {len(chunk)} sent, "
            f"matched={resp.get('matched_count')} credits={resp.get('credits_used')}"
        )
        batch_no += 1

    if email_only and not resolve_emails:
        cost = len(email_only) * sumble_v6.EMAIL_RESOLUTION_CREDITS
        print(
            f"[fetch] {kind}: {len(email_only)} email-only rows SKIPPED. Re-run with "
            f"--resolve-emails to resolve them (worst case ~{cost} extra credits)."
        )
        return
    for bi in range(0, len(email_only), sumble_v6.EMAIL_BATCH):
        chunk = email_only[bi : bi + sumble_v6.EMAIL_BATCH]
        people = [{"email": (r.get("email") or "").strip()} for r in chunk]
        body = {"people": people, "select": {"attributes": attributes}}
        resp = sumble_v6.post(api_key, sumble_v6.PEOPLE_URL, body)
        assert resp is not None
        fname = f"people_{kind}_email_b{batch_no:03d}.json"
        (resp_dir / fname).write_text(json.dumps(resp))
        index.append({"file": fname, "kind": kind})
        print(
            f"[fetch] {kind} email batch {batch_no}: {len(chunk)} sent, "
            f"matched={resp.get('matched_count')} credits={resp.get('credits_used')}"
        )
        batch_no += 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch calibration people via /v6/people.")
    ap.add_argument("--raw", required=True, help="absolute path to the _raw directory")
    ap.add_argument(
        "--estimate-only",
        action="store_true",
        help="probe people counts (1 credit/org) and print the credit estimate, "
        "then stop — nothing is enriched",
    )
    ap.add_argument(
        "--resolve-emails",
        action="store_true",
        help="resolve email-only contact rows via reverse enrichment "
        f"({sumble_v6.EMAIL_RESOLUTION_CREDITS} extra credits per resolved person)",
    )
    ap.add_argument(
        "--lean",
        action="store_true",
        help="lean attribute set (5 credits/person instead of 8) — for large "
        "production pulls; drops job_title/location/country",
    )
    ap.add_argument("--env-file", default=None, help="read SUMBLE_API_KEY from this file")
    args = ap.parse_args()

    raw = Path(args.raw).resolve()
    spec = json.loads((raw / "spec.json").read_text())
    api_key = load_api_key(args.env_file)
    attributes = (
        sumble_v6.PERSON_ATTRIBUTES_LEAN if args.lean else sumble_v6.PERSON_ATTRIBUTES
    )
    per_person = sumble_v6.per_person_credits(attributes)
    path = (spec.get("path") or "c").strip().lower()

    jf_names = [p["name"] for p in spec.get("personas") or []]
    floor = (spec.get("seniority_floor") or {}).get("name")
    query = sumble_v6.people_query(jf_names, floor) if path in ("b", "c") else ""

    matches = match_companies(raw, spec, api_key)
    org_ids = [m["org_id"] for m in matches]

    contacts_path = raw / "contacts.csv"
    contacts = _read_csv(contacts_path) if contacts_path.exists() else []
    gold_path = raw / "gold.csv"
    gold_rows = _read_csv(gold_path) if gold_path.exists() else []

    if path in ("a", "b") and not contacts:
        sys.exit(f"[fetch] path {path} needs _raw/contacts.csv (1P contact rows).")

    # --- Credit estimate (always printed; --estimate-only stops here) ----------
    est_people = 0
    if path in ("b", "c"):
        for oid in org_ids:
            n = count_people(api_key, oid, query)
            est_people += n
            print(f"[estimate] org {oid}: ~{n} people match the ICP query")
    n_contact_url = sum(1 for r in contacts if sumble_v6.li_slug(r.get("linkedin_url")))
    n_contact_email = sum(
        1
        for r in contacts
        if not sumble_v6.li_slug(r.get("linkedin_url")) and (r.get("email") or "").strip()
    )
    n_gold = len(gold_rows)
    est_credits = (est_people + n_contact_url + n_gold) * per_person
    email_extra = n_contact_email * (per_person + sumble_v6.EMAIL_RESOLUTION_CREDITS)
    print(
        f"[estimate] ~{est_people} Sumble-side people + {n_contact_url} contact rows "
        f"+ {n_gold} gold rows at {per_person} credits/person "
        f"≈ {est_credits} credits"
        + (
            f" (+ up to {email_extra} for {n_contact_email} email-only rows "
            "with --resolve-emails)"
            if n_contact_email
            else ""
        )
    )
    if args.estimate_only:
        print("[fetch] --estimate-only: stopping before enrichment. No people credits spent.")
        return

    # --- Fetch ------------------------------------------------------------------
    resp_dir = _clear_responses(raw)
    index: list[dict] = []

    if path in ("b", "c"):
        for oid in org_ids:
            pull_org_people(api_key, oid, query, attributes, resp_dir, index)
    if contacts:
        resolve_contacts(
            contacts, "contacts", api_key, attributes, resp_dir, index, args.resolve_emails
        )
    if gold_rows:
        resolve_contacts(
            gold_rows, "gold", api_key, attributes, resp_dir, index, args.resolve_emails
        )

    if not index:
        sys.exit("[fetch] nothing fetched — check spec.path and the input CSVs.")
    (raw / "fetch_index.json").write_text(json.dumps(index, indent=2))
    print(f"[fetch] wrote fetch_index.json ({len(index)} response files).")


if __name__ == "__main__":
    main()
