"""Stage 2 (final) — parse the fetched responses into `data.csv`.

Reads (all under --raw):
  spec.json              ICP (personas with slug+name, skills, 1P signal spec)
  org_matches.json       calibration company -> org_id/domain map
  responses/people_*.json + fetch_index.json   (from fetch_people.py)
  contacts.csv           optional — used to recover is_gold flags + which
                         input rows resolved (paths a/b)
  gold.csv               optional — path-c gold list (every row gold)
  skills.csv             optional — person_id,skill_count,matched_skills
                         (written by the agent from the organizations-duckdb
                         MCP query; the v6 API has no per-person skills)
  account_scores.csv     optional — domain,account_score[,account_rank]
                         (e.g. exported from a sumble-account-scoring run)
  signals.csv            optional — person_id or linkedin_url + one raw column
                         per 1P signal declared in spec.first_party_signals

Writes:
  <output_root>/data.csv                    one row per unique person_id
  <output_root>/data.calibration-info.json  per-company people counts + stats
  _raw/_merge_report.json                   match rates / sanity numbers

Deterministic: same spec + same responses -> byte-identical data.csv. Policy
constants live here, not in agent prompts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import sumble_v6


def _truthy(v: object) -> bool:
    return str(v or "0").strip().lower() in ("1", "true", "yes")


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(v: object, default: float = 0.0) -> float:
    if v in (None, ""):
        return default
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def p99_norm(raws: list[float]) -> list[float]:
    """p99 log-saturation normalisation — identical to the app/scorer formula:
    x = ln(1+max(raw,0)); p99 over x where raw>0;
    norm = clamp((1 - exp(-x/p99)) / (1 - exp(-1)), 0, 1)."""
    xs = [math.log1p(max(r, 0.0)) for r in raws]
    pos = sorted(x for r, x in zip(raws, xs) if r > 0)
    p99 = max(pos[min(len(pos) - 1, int(0.99 * len(pos)))], 1e-9) if pos else 1e-9
    scale = 1.0 - math.exp(-1.0)
    return [
        max(0.0, min((1.0 - math.exp(-min(x / p99, 700.0))) / scale, 1.0)) for x in xs
    ]


def load_people(raw: Path, jf_slug_by_name: dict[str, str]) -> tuple[dict, dict]:
    """Parse every response file into {person_id: row}, merging duplicates.

    Returns (rows_by_id, meta) where meta carries per-source person_id sets:
    {"contacts": set, "gold": set, "contact_inputs": {input_key: person_id}}.
    A person seen both in an org pull and a contact resolution keeps the org
    row's columns (identical anyway) and gains the contact flags in finalise.
    """
    index = json.loads((raw / "fetch_index.json").read_text())
    rows_by_id: dict[int, dict] = {}
    contact_ids: set[int] = set()
    gold_ids: set[int] = set()
    contact_inputs: dict[str, int] = {}
    counts = {"org_people": 0, "contacts": 0, "gold": 0, "unmatched_inputs": 0}

    for entry in index:
        resp = json.loads((raw / "responses" / entry["file"]).read_text())
        kind = entry["kind"]
        for person in resp.get("people") or []:
            row = sumble_v6.build_person_row(person, jf_slug_by_name)
            inp = person.get("input") or {}
            if row is None:
                if kind in ("contacts", "gold"):
                    counts["unmatched_inputs"] += 1
                continue
            pid = row["person_id"]
            rows_by_id.setdefault(pid, row)
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "contacts":
                contact_ids.add(pid)
            elif kind == "gold":
                gold_ids.add(pid)
            if kind in ("contacts", "gold"):
                slug = sumble_v6.li_slug(inp.get("linkedin_url"))
                if slug:
                    contact_inputs[f"li:{slug}"] = pid
                if inp.get("email"):
                    contact_inputs[f"em:{str(inp['email']).strip().lower()}"] = pid
    meta = {
        "contact_ids": contact_ids,
        "gold_ids": gold_ids,
        "contact_inputs": contact_inputs,
        "counts": counts,
    }
    return rows_by_id, meta


def gold_ids_from_contacts(contacts: list[dict], contact_inputs: dict[str, int]) -> set[int]:
    """Recover is_gold flags for resolved contact rows (paths a/b)."""
    out: set[int] = set()
    for r in contacts:
        if not _truthy(r.get("is_gold")):
            continue
        slug = sumble_v6.li_slug(r.get("linkedin_url"))
        pid = None
        if slug:
            pid = contact_inputs.get(f"li:{slug}")
        if pid is None and (r.get("email") or "").strip():
            pid = contact_inputs.get(f"em:{r['email'].strip().lower()}")
        if pid is not None:
            out.add(pid)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge fetched responses into data.csv.")
    ap.add_argument("--raw", required=True, help="absolute path to the _raw directory")
    args = ap.parse_args()
    raw = Path(args.raw).resolve()
    out_root = raw.parent

    spec = json.loads((raw / "spec.json").read_text())
    path = (spec.get("path") or "c").strip().lower()
    personas = spec.get("personas") or []
    jf_slug_by_name = {p["name"]: p["slug"] for p in personas if p.get("name")}
    org_matches = json.loads((raw / "org_matches.json").read_text())
    domain_by_org = {
        m["org_id"]: (m.get("url") or m.get("input_domain") or "") for m in org_matches
    }
    name_by_org = {m["org_id"]: m.get("name") or "" for m in org_matches}

    rows_by_id, meta = load_people(raw, jf_slug_by_name)
    if not rows_by_id:
        sys.exit("[merge] no matched people in the responses — nothing to write.")

    contacts_path = raw / "contacts.csv"
    contacts = _read_csv(contacts_path) if contacts_path.exists() else []
    gold_ids: set[int] = set(meta["gold_ids"])
    gold_ids |= gold_ids_from_contacts(contacts, meta["contact_inputs"])

    # --- Flags + org domain (account-picker join key) --------------------------
    for pid, row in rows_by_id.items():
        row["is_crm_contact"] = 1 if pid in meta["contact_ids"] else 0
        row["is_icp_gold"] = 1 if pid in gold_ids else 0
        oid = row.get("org_id")
        row["domain"] = domain_by_org.get(oid, "")
        if not row.get("org_name"):
            row["org_name"] = name_by_org.get(oid, "")

    # --- Skills (organizations-duckdb MCP -> skills.csv; no API equivalent) ----
    skills_path = raw / "skills.csv"
    have_skills = skills_path.exists()
    skills_by_id: dict[int, dict] = {}
    if have_skills:
        for r in _read_csv(skills_path):
            try:
                skills_by_id[int(_f(r.get("person_id")))] = r
            except (TypeError, ValueError):
                continue
    for pid, row in rows_by_id.items():
        s = skills_by_id.get(pid, {})
        row["skill_count"] = int(_f(s.get("skill_count")))
        row["matched_skills"] = s.get("matched_skills") or ""
    if spec.get("skills") and not have_skills:
        print(
            "[merge] WARNING: spec has ICP skills but _raw/skills.csv is missing — "
            "skill_count is 0 for everyone. Run the organizations-duckdb skills "
            "query and re-run merge."
        )

    # --- Account score (optional; joined on the org match domain) --------------
    acct_path = raw / "account_scores.csv"
    if acct_path.exists():
        by_domain: dict[str, dict] = {}
        for r in _read_csv(acct_path):
            d = (r.get("domain") or r.get("url") or "").strip().lower()
            if d:
                by_domain[d] = r
        hits = 0
        for row in rows_by_id.values():
            r = by_domain.get((row.get("domain") or "").strip().lower())
            row["account_score"] = _f(r.get("account_score") or r.get("score")) if r else ""
            row["account_rank"] = int(_f(r.get("account_rank") or r.get("rank"))) if r else ""
            hits += 1 if r else 0
        print(f"[merge] account scores joined for {hits}/{len(rows_by_id)} people.")

    # --- 1P signals (optional; person_id or linkedin_url join) -----------------
    one_p = spec.get("first_party_signals") or []
    sig_path = raw / "signals.csv"
    if one_p and sig_path.exists():
        sig_rows = _read_csv(sig_path)
        by_pid: dict[int, dict] = {}
        by_slug: dict[str, dict] = {}
        for r in sig_rows:
            if (r.get("person_id") or "").strip():
                by_pid[int(_f(r.get("person_id")))] = r
            slug = sumble_v6.li_slug(r.get("linkedin_url"))
            if slug:
                by_slug[slug] = r
        ordered = sorted(rows_by_id.values(), key=lambda r: r["person_id"])
        for sig in one_p:
            key = sig["key"]
            raw_col = sig.get("raw_column") or f"{key}_raw"
            src_col = sig.get("source_column") or key
            raws: list[float] = []
            for row in ordered:
                src = by_pid.get(row["person_id"]) or by_slug.get(
                    sumble_v6.li_slug(row.get("linkedin_url")) or ""
                )
                raws.append(_f(src.get(src_col)) if src else 0.0)
            norms = p99_norm(raws)
            norm_col = sig.get("norm_column") or f"{key}_norm"
            nonzero = sum(1 for v in raws if v > 0)
            for row, rv, nv in zip(ordered, raws, norms):
                row[raw_col] = rv
                row[norm_col] = round(nv, 6)
            print(f"[merge] 1P signal {key}: {nonzero}/{len(ordered)} non-zero rows.")
    elif one_p:
        print(
            "[merge] WARNING: spec declares 1P signals but _raw/signals.csv is "
            "missing — all 1P columns are 0."
        )
        for sig in one_p:
            raw_col = sig.get("raw_column") or f"{sig['key']}_raw"
            norm_col = sig.get("norm_column") or f"{sig['key']}_norm"
            for row in rows_by_id.values():
                row[raw_col] = 0.0
                row[norm_col] = 0.0

    # --- Write data.csv ---------------------------------------------------------
    rows = sorted(rows_by_id.values(), key=lambda r: r["person_id"])
    fieldnames = list(rows[0].keys())
    data_path = out_root / "data.csv"
    with data_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # --- Calibration info + report ----------------------------------------------
    per_company = []
    for m in org_matches:
        n = sum(1 for r in rows if r.get("org_id") == m["org_id"])
        per_company.append(
            {
                "name": m["name"],
                "domain": m.get("url") or m.get("input_domain") or "",
                "org_id": m["org_id"],
                "people": n,
            }
        )
        if n == 0:
            print(f"[merge] WARNING: 0 people at {m['name']} — check the ICP query "
                  "or the org match.")
    info = {
        "calibration_companies": per_company,
        "total_people": len(rows),
        "path": path,
        "has_account_score": acct_path.exists(),
        "crm_contacts": sum(r["is_crm_contact"] for r in rows),
        "gold_people": sum(r["is_icp_gold"] for r in rows),
    }
    (out_root / "data.calibration-info.json").write_text(json.dumps(info, indent=2))
    (raw / "_merge_report.json").write_text(
        json.dumps({**info, "source_counts": meta["counts"]}, indent=2)
    )
    print(
        f"[merge] data.csv: {len(rows)} people, "
        f"{info['crm_contacts']} CRM contacts, {info['gold_people']} gold."
    )


if __name__ == "__main__":
    main()
