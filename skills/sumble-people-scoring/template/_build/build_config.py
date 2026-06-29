"""Stage 3 — render spec.json (+ calibration info) into the app's config.json.

Deterministic: same spec + same data.calibration-info.json -> byte-identical
config.json. The policy constants live HERE, not in agent prompts:

  * Weights, Sumble-only:     jf 38 / seniority 46 / skills 16
    (mirrors Sumble's internal people score without the Account factor).
  * Weights, with N 1P signals: the Sumble factors keep their 38/46/16 ratio
    scaled to 75; the remaining 25 splits evenly across the 1P signals.
  * No ICP skills: the skills weight drops and the rest renormalise.
  * JF ranges: ICP personas tier `key` -> (0.55, 0.95); tier `other`/unset ->
    (0.50, 0.85); non-ICP functions fall back to default_jf_range (0.45, 0.80).
  * skill_cap 5.

`fit_weights.py` runs after this and may nudge the `current` weights toward
the gold set (the `default` values stay as the priors).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

# --- Policy constants -----------------------------------------------------------
SUMBLE_WEIGHTS = {"jf": 38.0, "seniority": 46.0, "skills": 16.0}
ONE_P_TOTAL_PCT = 25.0  # with 1P signals, Sumble factors scale to 100 - this
KEY_JF_RANGE = (0.55, 0.95)
OTHER_JF_RANGE = (0.50, 0.85)
DEFAULT_JF_RANGE = (0.45, 0.80)
SKILL_CAP = 5

WEIGHT_LABELS = {
    "jf": "Job Function (%)",
    "seniority": "Seniority (%)",
    "skills": "Skills (%)",
}

TABLE_COLUMNS = [
    "name",
    "current_title",
    "job_function_name",
    "job_level",
    "matched_skills",
    "skill_count",
    "location",
]


def build_weights(has_skills: bool, one_p_keys: list[str]) -> dict:
    base = dict(SUMBLE_WEIGHTS)
    if not has_skills:
        base.pop("skills")
        total = sum(base.values())
        base = {k: 100.0 * v / total for k, v in base.items()}
    sumble_total = 100.0 - (ONE_P_TOTAL_PCT if one_p_keys else 0.0)
    scale = sumble_total / 100.0
    weights: dict[str, dict] = {}
    for key, pct in base.items():
        w = round(pct * scale, 1)
        weights[key] = {
            "default": w,
            "current": w,
            "min": 0,
            "max": 100,
            "label": WEIGHT_LABELS[key],
        }
    if one_p_keys:
        each = round(ONE_P_TOTAL_PCT / len(one_p_keys), 1)
        for key in one_p_keys:
            weights[f"1p_{key}"] = {
                "default": each,
                "current": each,
                "min": 0,
                "max": 100,
                "label": f"{key.replace('_', ' ').title()} (%)",
            }
    return weights


def build_jf_ranges(personas: list[dict], data_path: Path) -> dict:
    out: dict[str, dict] = {}
    for p in personas:
        slug = p.get("slug") or ""
        if not slug:
            continue
        lo, hi = KEY_JF_RANGE if p.get("tier") == "key" else OTHER_JF_RANGE
        out[slug] = {"min": lo, "max": hi, "label": p.get("name") or slug}
    # People come back with LEAF function names (the query expands the ICP
    # seeds to their subtrees server-side), so also emit a tunable range entry
    # for every function actually observed in data.csv — otherwise the per-JF
    # sliders would only ever cover the seeds while most rows fall through to
    # default_jf_range.
    if data_path.exists():
        observed: dict[str, str] = {}
        with data_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                slug = (row.get("job_function_slug") or "").strip()
                if slug and slug not in observed:
                    observed[slug] = (row.get("job_function_name") or slug).strip()
        lo, hi = DEFAULT_JF_RANGE
        for slug, name in sorted(observed.items()):
            out.setdefault(slug, {"min": lo, "max": hi, "label": name})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Render spec.json into config.json.")
    ap.add_argument("--raw", required=True, help="absolute path to the _raw directory")
    args = ap.parse_args()
    raw = Path(args.raw).resolve()
    out_root = raw.parent

    spec = json.loads((raw / "spec.json").read_text())
    info_path = out_root / "data.calibration-info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}

    company = spec.get("company") or {}
    personas = spec.get("personas") or []
    skills = spec.get("skills") or []
    one_p = spec.get("first_party_signals") or []
    one_p_keys = [s["key"] for s in one_p]
    floor = spec.get("seniority_floor") or {}

    config = {
        "customer_name": company.get("name") or "",
        "score_label": f"{company.get('name') or 'Sumble'} people fit score",
        "csv": "data.csv",
        "id_column": "person_id",
        "name_column": "name",
        "linkedin_url_column": "linkedin_url",
        "sumble_url_column": "sumble_url",
        "account_picker": {"domain_column": "domain", "org_name_column": "org_name"},
        "table_columns": TABLE_COLUMNS,
        "weights": build_weights(bool(skills), one_p_keys),
        "job_function_ranges": build_jf_ranges(personas, out_root / "data.csv"),
        "default_jf_range": {"min": DEFAULT_JF_RANGE[0], "max": DEFAULT_JF_RANGE[1]},
        "skill_cap": SKILL_CAP,
        "seniority": {
            "rank_column": "job_level_rank",
            "max_rank_column": "max_job_level_rank",
        },
        "one_p_signals": [
            {
                "key": s["key"],
                "weight_key": f"1p_{s['key']}",
                "label": s.get("label") or s["key"],
                "raw_column": s.get("raw_column") or f"{s['key']}_raw",
                "norm_column": s.get("norm_column") or f"{s['key']}_norm",
                "unit": s.get("unit") or "",
            }
            for s in one_p
        ],
        "flags": {"crm_contact_column": "is_crm_contact", "gold_column": "is_icp_gold"},
        # Self-contained ICP definition: the ACTUAL slugs (not just counts) so a
        # coding agent can re-implement the score in a production pipeline without
        # re-deriving the ICP. skill_score counts a person's technologies that fall
        # in `icp.skills`; the ICP population is `icp.job_functions` at/above
        # `icp.seniority_floor.rank`.
        "icp": {
            "job_functions": [
                {"slug": p["slug"], "name": p.get("name") or p.get("label") or p["slug"]}
                for p in personas
                if p.get("slug")
            ],
            "skills": [
                {"slug": s["slug"], "name": s.get("name") or s.get("label") or s["slug"]}
                for s in skills
                if s.get("slug")
            ],
            "seniority_floor": {
                "label": floor.get("name") or "All levels",
                "rank": floor.get("rank") or 0,
            },
        },
        "filters_applied": {
            "seniority_floor_label": floor.get("name") or "All levels",
            "seniority_floor_rank": floor.get("rank") or 0,
            "icp_job_function_count": len(personas),
            "icp_skill_count": len(skills),
            "calibration_companies": len(info.get("calibration_companies") or []),
            "total_people": info.get("total_people") or 0,
            "gold_people": info.get("gold_people") or 0,
        },
    }
    if info.get("has_account_score"):
        config["account_picker"]["account_rank_column"] = "account_rank"
        config["account_picker"]["account_score_column"] = "account_score"

    out_path = out_root / "config.json"
    out_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"[config] wrote {out_path} "
          f"({len(personas)} JFs, {len(skills)} skills, {len(one_p)} 1P signals).")


if __name__ == "__main__":
    main()
