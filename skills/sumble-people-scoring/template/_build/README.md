# `_build/` — deterministic pipeline scripts (people-scoring)

Every Sumble column comes from the v6 REST endpoints — org match via
`POST /v6/organizations`, people via `POST /v6/people` (match mode for 1P
contact lists, filter mode for Sumble-side pulls). Same `spec.json` + same
endpoint responses → byte-identical output. Policy constants are baked into
the scripts, not chosen per run.

Skills are API-sourced too: the people endpoint's `technologies` attribute
(LinkedIn skills normalized to Sumble's catalog) is intersected with
`spec.skills` at merge time — no SQL anywhere.

## Files

- **`sumble_v6.py`** — shared helpers: API-key resolution, the POST helper,
  the person-attribute selection + per-person credit cost, the canonical
  job-level → `level_rank` map (the endpoint returns level *names* only), the
  people advanced-query builder (`job_function IN … AND job_level_min EQ …`),
  LinkedIn-slug canonicalisation, and `build_person_row` (response →
  `data.csv` columns). Imported by every other script so nothing drifts.
- **`lookup.py`** — Stage 2a name resolution via the v6 lookup endpoints
  (`/technologies/lookup` for skills, `/jobs/title-lookup` for job functions).
- **`set_api_key.py`** — interactive prompt that saves the key to
  `~/.config/sumble/api_key` (0600); the other scripts read it automatically.
- **`fetch_people.py`** — Stage 2 data pull. Matches the calibration
  companies, pulls people per org (filter mode, paginated), resolves 1P
  contact/gold rows (match mode; email-only rows only with
  `--resolve-emails`). `--estimate-only` probes counts and prints the credit
  estimate without enriching. `--lean` drops display attributes
  (9 → 6 credits/person) for large production pulls.
- **`merge_data.py`** — parse the responses → `data.csv` +
  `data.calibration-info.json` + `_raw/_merge_report.json`. Derives
  `matched_skills`/`skill_count` from each row's `technologies` attribute ∩
  `spec.skills`; joins the optional `account_scores.csv` and `signals.csv`
  (computing the p99 log-saturation norms for 1P signals); an optional
  `skills.csv` overrides the skill columns (back-compat).
- **`build_config.py`** — `spec.json` + calibration info → `config.json`
  with the policy-default weights and JF ranges.
- **`fit_weights.py`** — regularized fit of the factor blend to the gold set
  (shrinkage to priors, ±20-point boxes, 5-fold CV with the 1-SE rule, paired
  adopt-only-if-it-generalizes test, ≥20-gold guard). Writes each weight's
  `current` value + a `_weight_fit` audit block into `config.json` and a
  report to `_raw/_weight_fit_report.json`. JF ranges are frozen.

## Pipeline order

1. **Resolve ICP** — `python lookup.py --skills … --titles …` → write
   `_raw/spec.json` (schema below).
2. **Inputs** — write `_raw/contacts.csv` / `_raw/gold.csv` as the path needs.
3. **Estimate** — `python fetch_people.py --raw <abs>/_raw --estimate-only`;
   surface the credit cost to the user.
4. **Fetch** — `python fetch_people.py --raw <abs>/_raw`.
5. **Merge** — `python merge_data.py --raw <abs>/_raw` → `data.csv` (skills
   included via the `technologies` attribute).
6. **Config** — `python build_config.py --raw <abs>/_raw` → `config.json`.
7. **Fit** — `python fit_weights.py --raw <abs>/_raw` (no-op without ≥20 gold).

## `spec.json` schema

```json
{
  "schema_version": 1,
  "company": {"name": "Acme", "url": "acme.com", "folder_slug": "acme"},
  "path": "b",
  "personas": [
    {"slug": "sales", "name": "Sales", "tier": "key"},
    {"slug": "revenue-operations", "name": "Revenue Operations", "tier": "other"}
  ],
  "skills": [{"slug": "clay", "name": "Clay"}, {"slug": "zoominfo", "name": "ZoomInfo"}],
  "seniority_floor": {"name": "Head", "rank": 7},
  "calibration_companies": [
    {"name": "Datadog", "domain": "datadoghq.com"}
  ],
  "first_party_signals": [
    {"key": "product_events", "label": "Product events (30d)",
     "source_column": "events_30d", "unit": "events"}
  ],
  "gold": {"definition": "closed_won_opp_contacts", "source": "salesforce OpportunityContactRole"},
  "data_sources": {"contacts": {"source": "...", "size": 1200}}
}
```

- `path` — `a` (1P only), `b` (1P + Sumble whitespace), `c` (Sumble only).
- `personas[].name` is the endpoint's `job_function` term (display name;
  subtree-expanded server-side — no recursive JF expansion needed).
  `tier: key` gets the wider default JF range.
- `seniority_floor` — `null` / rank 0 means all levels. Applied only to
  Sumble-side pulls (paths b/c); 1P rows are never floored.
- `first_party_signals[].source_column` names the raw column in
  `_raw/signals.csv`; the merged columns default to `{key}_raw` / `{key}_norm`.
- `gold.definition` is informational (it documents what the gold set means;
  the default recommendation is contacts role-attached to closed-won
  opportunities).

## Input CSV contracts (under `_raw/`)

- `contacts.csv` — `contact_id,name,linkedin_url,email,is_gold` (paths a/b).
- `gold.csv` — same columns, every row gold (path c only).
- `skills.csv` — optional OVERRIDE (`person_id,skill_count,matched_skills`);
  normally unnecessary — skills come from the `technologies` attribute.
- `account_scores.csv` — `domain,account_score[,account_rank]` (also accepts
  `url`/`score`/`rank` headers, so a sumble-account-scoring `score.csv` works
  after column projection).
- `signals.csv` — `person_id` and/or `linkedin_url`, plus one raw column per
  declared 1P signal.

## Policy constants

- Weights (Sumble-only): **jf 38 / seniority 46 / skills 16**; with N 1P
  signals the Sumble factors scale to 75 and the 25 splits evenly. No ICP
  skills → the skills weight drops and the rest renormalise.
- JF ranges: ICP `key` (0.55, 0.95); ICP `other`/unset (0.50, 0.85);
  non-ICP fallback `default_jf_range` (0.45, 0.80). `skill_cap` 5.
- Job-level ranks: baked map in `sumble_v6.py` (IC 0 … CXO 18, max 18) —
  mirror of the `job_levels` reference table.
- Fit: ±20-point boxes, λ grid 0–32 with the 1-SE rule, adopt floor 0.002
  AUC and 1 SE of the paired per-fold gains, ≥20 gold / ≥40 non-gold,
  ≤5000-row non-gold subsample for speed.

## Credits

- Org match: free (id/name/slug/url attributes only).
- People: `1 + paid-attributes` per returned person — **9**/person with the
  full attribute set, **6**/person with `--lean` (both include
  `technologies`, the matched-skills source).
- Email-only contact rows: +20 credits each when they resolve (max 25 per
  request); skipped unless `--resolve-emails`.
- Count probes (`--estimate-only`): 1 credit per org.
