---
name: sumble-people-scoring
description: "Build a people-scoring web app powered by Sumble data and optional first-party data. Interviews the user about their ICP (job functions + skills via GetMyCompanyProfile), then builds a SMALL calibration sample from ~5 user-named companies via the unified v6 REST endpoints (POST /v6/people) so the app is ready in minutes. Optional gold set (closed-won opportunity contacts) drives an Evaluation tab and a conservative regularized weight fit. Generates a self-contained, zero-dependency Python + HTML/JS app at people_scoring/<company>/ with real-time slider re-weighting, a score.csv superset sheet, plus a production score_leads.py that applies the calibrated weights to an entire enriched CRM."
---

# People Scoring

This skill produces two things:

1. A zero-dependency Python **web app** (stdlib `http.server`) that ranks
   people and lets the user tune the scoring factors (Job Function,
   Seniority, Skills, plus any connected 1P signals) with sliders in real
   time. It runs over a **small calibration sample** built from ~5 companies
   the user names, so the whole pipeline finishes in minutes. The Save
   button writes `people-scoring-weights.json` and regenerates `score.csv`
   (the superset score sheet).
2. A portable scoring spec + **production scorer**: `score_leads.py` reads
   `people-scoring-weights.json` and scores an entire enriched leads/CRM
   file with the calibrated weights. You calibrate on ~5 companies; you
   apply to everything.

All Sumble data comes from the **v6 REST endpoints** via the deterministic
`_build/` scripts — `POST /v6/organizations` (company match) and
`POST /v6/people` (people pull + 1P contact resolution, including
reverse-enrichment by email). Skills come from the people endpoint's
`technologies` attribute (the person's LinkedIn skills normalized to Sumble's
technology catalog), so there is **no SQL anywhere** in the pipeline.

Follow the stages closely — input (interview) and output should be
consistent between runs, more deterministic than most skills.

## When to use

Trigger on `/sumble-people-scoring`, or on any of: "score my leads", "rank
people at my accounts", "build a people score", "who should my reps contact
first?". For ranking *companies* instead of people, use
`sumble-account-scoring`.

## Why ~5 companies for calibration

Calibrating weights doesn't need the full CRM — just enough variety for the
sliders to have something to separate. ~5 companies (a few hundred to
low-thousands of people) builds in minutes, costs little, and keeps the
browser snappy. The full-CRM scoring happens later, offline, via
`fetch_people.py --lean` + `score_leads.py` (Stage 5), exactly once, against
final weights.

## Required tools

- **Sumble MCP** (for the ICP interview only):
  - `GetMyCompanyProfile` — pre-fill the ICP (job functions, technologies)
  - `SearchTechnologies` — fuzzy skill discovery when you don't yet have a term
- **Sumble public API key** — `SUMBLE_API_KEY` (from sumble.com/account). All
  Stage-2 people data — including the matched-skills factor, via the
  `technologies` person attribute — comes from `POST /v6/people` (match +
  filter modes) and the org match from `POST /v6/organizations`;
  `_build/fetch_people.py` calls them directly.

  **Check before prompting — the key is usually already set.** BEFORE you
  surface the link or ask the user to do anything about the key, check whether
  it already resolves. Run this one simple command and read the result:
  ```bash
  ls ~/.config/sumble/api_key
  ```
  If that file exists (or `SUMBLE_API_KEY` is exported in the env), the key is
  configured — say so in one line and move on. Do NOT prompt for it, and do NOT
  surface the setup link. Only when the check comes up empty do you fall through
  to the setup flow below.

  **Set the key once (only if the check above came up empty).** First tell the
  user **where to get it: their key is at
  https://sumble.com/account (Account → API key)** — surface this link before
  prompting. Then have them run the helper, which prints that link, reads the
  key **without echoing** (so it never lands in the chat transcript or shell
  history), and saves it to `~/.config/sumble/api_key` (chmod 0600):
  ```bash
  ! python <skill_dir>/template/_build/set_api_key.py
  ```
  Use the hidden-input helper as the default — **don't ask the user to paste the
  key into the chat** (it would be logged). The `_build/` scripts then find it
  automatically. Power-user alternatives the resolver also accepts:
  `export SUMBLE_API_KEY=...` (this session only) or a gitignored `.env` file
  passed via `--env-file path/to/.env`.
- **First-party MCPs (optional)** — Salesforce, HubSpot, warehouse
  (Snowflake/BigQuery/Databricks/Postgres), Sheets/Drive. CSV path is always a
  valid fallback. If a Postgres MCP disconnects mid-query
  (`MCP error -32000: Connection closed`), ask the user to re-run `/mcp` —
  the connection stays dead for the session until they reload.

If the Sumble MCP isn't available in the session, stop and tell the user
how to install it: https://docs.sumble.com/api/mcp.

## Shell-command discipline

This runs unattended AND is shipped to non-technical users — and it may run in
**Claude Code, Codex, Cursor, or any other coding agent**. They all gate shell
commands behind a command-approval / permission system that **interrupts the run
on anything complex** (compound, redirected, `cd`-prefixed, or
substitution-bearing commands). Each interruption stalls the run, in every
agent. Keeping commands trivially simple is the portable way to avoid that
everywhere. Follow these rules exactly:

- **One simple command per shell call.** No `&&` / `;` / `|` chains, no `cd`, no
  output redirection (`>`, `>>`, `2>&1`), no backgrounding (`&`, `nohup`), and no
  command substitution (`$(…)` or backticks).
- **Use absolute paths, never `cd`.** Every `_build/*` script takes its
  directory as an argument, so run e.g.
  `python3 <skill_dir>/template/_build/fetch_people.py --raw <output_root>/_raw`
  from anywhere.
- **Run the pipeline in the foreground.** The scripts stream progress to stdout
  and finish in minutes. NEVER background a step and poll it.
- **No inline Python, no heredocs.** Any multi-line Python, JSON shaping,
  counting, or CSV writing → write a `.py` to `<output_root>/_raw/` (with your
  agent's file tool) and run it as a single `python3 <abs>.py`. Never
  `python3 -c "…{…}…"` (the `{`+`"` trips the approval prompt).
- **Inspect with your agent's file tools, not the shell.** Use the native
  file-read / glob / grep tools — never `cat` / `tail` / `head` / `ls` / `wc` /
  `grep`.
- **No subagents needed.** The `_build/` scripts replaced the old multi-batch
  MCP work that needed them. Stage everything under `<output_root>/_raw/` —
  the old `$TMPDIR` staging rule is obsolete.

The only shell this skill needs is `mkdir -p <abs>`, `cp <abs> <abs>`, and
`python3 <abs>/script.py [args]` — each as one standalone command.

**Running a command in the user's own terminal.** A couple of steps (the
API-key helper, launching `app.py`) are best run by the user so they're
interactive / stay up. In **Claude Code** prefix the command with `!` to run it
in the user's terminal. In **Codex / Cursor** (no `!` syntax), tell the user to
paste the same command (without the `!`) into a terminal themselves.

## Output

```
people_scoring/<company>/
  app.py                      stdlib http.server (copied from template/, unchanged)
  score_sheet.py              GENERATOR SCRIPT — regenerates score.csv from
                              data.csv + the live weights on Save/startup
  score_leads.py              production scorer (copied from template/, unchanged)
  config.json                 weights, JF ranges, 1P signal mappings — written
                              by _build/build_config.py, then nudged by
                              _build/fit_weights.py when a gold set exists
  data.csv                    IMMUTABLE raw pull (calibration sample); the
                              re-score source, never rewritten by the app
  score.csv                   THE one file you use — a SUPERSET of data.csv:
                              rank → all data columns (deep links included) →
                              people_score → per-factor contribution columns
  data.calibration-info.json  the ~5 companies + per-company people counts
  people-scoring-weights.json self-describing scoring spec (written by Save)
  static/                     UI: account picker, sliders, tables, breakdown,
                              Evaluation tab, Download score sheet button
  README.md / SCHEMA.md / .gitignore
  _raw/                       spec.json, input CSVs, responses/, reports
```

**Only two CSVs, with one clear job each** (`score_sheet.py` is the generator
*script*, not a third CSV):
- `data.csv` — the **immutable** raw pull. The app never rewrites it.
- `score.csv` — **the one file you use.** A *superset* of `data.csv`: `rank` →
  every data column (including the `sumble_url`, `linkedin_url` and
  `org_sumble_url` deep links) → `people_score` (0–100) → one per-factor
  **contribution** column (points; they sum exactly to `people_score`),
  ordered most-impactful first. Regenerated on every **Save** and at startup;
  the in-app **Download score sheet** button produces the same sheet from the
  current sliders. The per-person breakdown panel tells the same story.

Before handing over (Stage 4), spot-check the `score.csv` header with your file
tools: it must contain `sumble_url`, `linkedin_url`, `people_score`, and at
least one `(pts)` contribution column. If any is missing, the config or data
was built wrong — fix it before telling the user the app is ready.

**Zero-dependency rule:** `app.py` uses only the stdlib — no
`requirements.txt`, no third-party imports, so any teammate can
`python app.py` on the first try.

`data.csv` schema: see `template/SCHEMA.md`. `score_leads.py` consumes the
same schema for the full CRM in production (Stage 5).

## Scoring

```
seniority_frac  = job_level_rank / max_job_level_rank
jf_score        = jf_range[jf].min + (jf_range[jf].max - jf_range[jf].min) * seniority_frac
seniority_score = seniority_frac
skill_score     = min(skill_count, skill_cap) / skill_cap   # default cap = 5
1p_score        = <signal>_norm   # pre-normalised at merge time
total           = Σ (weight_pct/100) * factor_score
```

Weights sum to 100%. `job_level_rank` comes from the canonical job-level map
baked into `_build/sumble_v6.py` (the endpoint returns level *names* only;
IC 0 … CXO 18).

### Default weights + calibration

**Two-step weighting: policy priors, then a regularized fit to gold.**
`build_config.py` lays down the policy defaults (Sumble-only:
`jf=38 / seniority=46 / skills=16`; with 1P signals those scale to 75% and
the 1P signals split the remaining 25%; no ICP skills → the skills weight
drops and the rest renormalise). `fit_weights.py` then nudges ONLY the
factor blend toward separating the gold contacts — without overfitting:

- **Low DOF.** Only the 3–6 top-level factor weights are fit. The per-JF
  ranges are FROZEN — that's where overfitting would otherwise live.
- **Shrinkage to the priors** (`AUC(gold) − λ·‖w − w_default‖²`), **box
  bounds** (±20 points), **K-fold CV** with the 1-SE rule on paired per-fold
  gains, and an **adopt-only-if-it-generalizes** test (mean held-out AUC gain
  must clear 0.002 AND one SE of the per-fold gains).
- **Small-gold guard.** Fewer than 20 gold rows → skip the fit, keep priors.

It's a warm start, not an autopilot: the fitted weights are the app's initial
slider positions (each weight's `current`; `default` stays the prior), still
fully tunable, and the Evaluation tab shows the gold-lift you're tuning
against. Deterministic — no RNG. Surface the `_raw/_weight_fit_report.json`
summary to the user (default vs fitted held-out AUC, adopted or not) so they
know how the sliders were set.

Policy constants live in `template/_build/build_config.py` /
`fit_weights.py` / `sumble_v6.py` — same `spec.json` + same endpoint
responses → byte-identical output. The agent does NOT pick weights, ranges,
or thresholds per run. See `template/_build/README.md`.

---

## Pipeline

Execute these stages in order. Surface progress between stages.

### Stage 1 — Interview

Follow this script exactly. **One question, not three** for the ICP step.

1. **Company name + URL.** Pre-fill if you recognise it; ask to confirm. Also
   ask where the app should be stored — default
   `./tmp/people_scoring/<company>/`.

2. **Confirm ICP via `GetMyCompanyProfile`.** Call it on the URL. If it
   succeeds, do **not** trim the returned job functions or technologies.
   If it fails, propose with an LLM. Either way, resolve every term to its
   canonical slug/name BEFORE presenting (Stage 2a's `lookup.py` — early
   invocation, so the user confirms the FINAL shape). Render one summary
   block and ask one yes/edit question:

   ```
   Proposed ICP for <company>:
     • Job functions: Sales, Revenue Operations, Marketing
     • Skills: clay, common-room, hg-insights, zoominfo

   Is this ICP OK? Reply "yes" to accept, or describe what to change
   (e.g. "drop marketing, add SDR").
   ```

   Loop on edits until accepted. (`SearchTechnologies` is for fuzzy
   *discovery* when the user names something you can't resolve.)

3. **People scope.** Pick one path (this decides where calibration people
   *come from*; Step 3.5 restricts them to ~5 companies). Record as
   `spec.path`:

   - **a. 1P only** — score the people already in the user's own systems
     (CRM contacts, product userbase). The candidate set is exactly what
     they bring.
   - **b. 1P + Sumble whitespace** — score their 1P people AND surface new
     "whitespace" people from the Sumble corpus at the same accounts.
   - **c. Sumble universe only** — score people pulled from Sumble for a
     target account list, without touching any internal system.

   **If a or b** — ask where to find the 1P people. Inspect the session's
   MCPs and surface relevant ones by name (Salesforce, HubSpot, warehouse,
   Sheets); else ask for a CSV path. Confirm the source, sample-read
   `LIMIT 10` to verify join keys, then pull. The join key is the LinkedIn
   URL (preferred); rows with only an email can be resolved by reverse
   enrichment (20 credits each — Stage 2c surfaces the count and cost and
   asks before spending). Also ask whether they have 1P *signals* to fold
   into the score: product/PLG usage, marketing touches, third-party intent
   on individuals — one weighted factor each (`spec.first_party_signals`).

   **If b or c** — ask the **seniority floor** for the Sumble-side pull.
   Free-form, default **Head and above**; "all levels", "Manager and above",
   "Director and above", "VP and above" are common. It resolves to a
   `job_level_min` clause server-side. Scope: path a — not applied (keep
   every 1P row); path b — applied only to the Sumble whitespace pull; path
   c — applied to the whole pull.

3.5. **Calibration companies (~5).** Ask the user to name **about 5
   companies** to build the calibration sample from — the single biggest
   lever on runtime and credit cost.

   ```
   Which ~5 companies should I calibrate on? Name them (domains or names).
   Pick a spread you know well — ideally a mix of strong-fit and weak-fit
   accounts, and a couple of different sizes — so the sliders have variety
   to work against. Reply "you pick" and I'll choose a representative 5
   from your data.
   ```

   - "you pick": for a/b choose 5 employers from the 1P set spanning
     customer / non-customer and size; for c choose 5 from the target
     account list.
   - Default 5; accept 3–10. Push back gently above 10 (slow + costly).
   - They go in `spec.calibration_companies`; `fetch_people.py` resolves
     them to org_ids via `POST /v6/organizations` and surfaces the matches —
     confirm them with the user before the people pull (an unmatched or
     wrong-org match here poisons everything downstream).

4. **Account score (optional).** Yes / default-no. If yes: do they have
   account scores to join (MCP or CSV)? Write them to
   `_raw/account_scores.csv` (`domain,account_score[,account_rank]`). A
   `score.csv` from a **sumble-account-scoring** run works directly — project
   the `url`/`score`/`rank` columns. Joined on the org-match domain.

5. **Gold set (evaluation + weight fit).** Strongly encouraged, default-no
   only if they truly have nothing. Ask whether they can provide people who
   *turned out to be great leads*. **Propose this default definition:
   contacts role-attached to closed-won opportunities** — in Salesforce,
   `OpportunityContactRole` rows on `Opportunity.StageName = 'Closed Won'`
   (`SELECT Contact.Name, Contact.Email, Contact.LinkedIn_URL__c FROM
   OpportunityContactRole WHERE Opportunity.StageName = 'Closed Won'` —
   adjust field names); in HubSpot, contacts associated to `closedwon`
   deals. Offer the broader alternative (all ICP-function contacts at
   closed-won accounts — bigger but noisier) and a plain CSV. Matched rows
   get `is_icp_gold = 1`: they drive the Evaluation tab AND the
   `fit_weights.py` warm start (≥20 gold rows needed for the fit).

   Paths a/b: gold is the `is_gold` column in `_raw/contacts.csv`. Path c:
   a separate `_raw/gold.csv` (resolved + enriched like any contact row —
   they appear in the app alongside the Sumble pull).

Show a single summary back before running anything that costs credits.

### Stage 2 — Fetch data from the v6 endpoints

#### 2a — Resolve ICP slugs/names

ONE call to the lookup helper (v6 lookup endpoints; needs `SUMBLE_API_KEY`):

```bash
python3 <skill_dir>/template/_build/lookup.py --skills clay,common-room,zoominfo --titles "Sales,Revenue Operations,Marketing"
```

It prints `{skills, job_functions}`, each item `{input, slug, name}`. Job
functions: the people query's `job_function` term is the **display name**,
and it matches the whole descendant subtree server-side — **no recursive JF
expansion needed** (the old "handful of people per company" failure mode is
gone). Surface unmatched inputs to the user.

Write **`_raw/spec.json`** (schema: `template/_build/README.md`): `path`,
`personas` (`{slug, name, tier}` — tier `key`/`other` from
`GetMyCompanyProfile`, it sets the default JF range), `skills`,
`seniority_floor` (`{name, rank}` or null), `calibration_companies`,
`first_party_signals`, `gold`. Show the resolved set back before fetching.

#### 2b — Write the input lists

- **`_raw/contacts.csv`** (`contact_id,name,linkedin_url,email,is_gold`) —
  paths a/b: the 1P contact rows at the ~5 calibration companies (filter the
  1P set by employer before writing; hundreds of rows, not the whole CRM).
- **`_raw/gold.csv`** (same columns, all rows gold) — path c only.

#### 2c — Estimate, then fetch

```bash
python3 <skill_dir>/template/_build/fetch_people.py --raw <output_root>/_raw --estimate-only
```

This matches the calibration companies (confirm the org matches with the
user), probes the people counts (1 credit per org) and prints the credit
estimate: **`1 + paid-attributes` per returned person — 9/person with the
full attribute set** — plus 20 extra per email-only contact row. Surface the
estimate and get a go-ahead, then:

```bash
python3 <skill_dir>/template/_build/fetch_people.py --raw <output_root>/_raw
```

Add `--resolve-emails` only after the user approves the email-resolution
cost (the script prints the skipped count otherwise). The script saves
`_raw/responses/people_*.json` + `_raw/fetch_index.json` + 
`_raw/org_matches.json`. Filter-mode pages are 200 people; match-mode
batches are 1000 (25 for email-only rows) — all handled internally.

#### 2d — Merge

If 1P signals were connected, first write `_raw/signals.csv` (`person_id`
and/or `linkedin_url` + one raw column per signal) — `merge_data.py` computes
the p99 log-saturation norms. Then:

```bash
python3 <skill_dir>/template/_build/merge_data.py --raw <output_root>/_raw
```

Matched skills need no extra step: each response row carries the
`technologies` attribute (LinkedIn skills normalized to Sumble's catalog) and
`merge_data.py` intersects it with `spec.skills` into
`matched_skills`/`skill_count`. (A `_raw/skills.csv` with
`person_id,skill_count,matched_skills`, if present, overrides those columns —
back-compat for older runs.)

**Sanity check** (from `_raw/_merge_report.json` + `data.calibration-info.json`,
read with file tools): people per calibration company (flag any 0 — usually a
bad org match), total people, contact match rate, gold count. Surface a
one-line summary: `5 companies, 1,240 people, 312 CRM contacts, 38 gold`.

### Stage 3 — Generate the app

```bash
mkdir -p <output_root>/static
cp <skill_dir>/template/app.py          <output_root>/app.py
cp <skill_dir>/template/score_sheet.py  <output_root>/score_sheet.py
cp <skill_dir>/template/score_leads.py  <output_root>/score_leads.py
cp <skill_dir>/template/README.md       <output_root>/README.md
cp <skill_dir>/template/SCHEMA.md       <output_root>/SCHEMA.md
cp <skill_dir>/template/.gitignore      <output_root>/.gitignore
cp <skill_dir>/template/static/app.js     <output_root>/static/app.js
cp <skill_dir>/template/static/index.html <output_root>/static/index.html
cp <skill_dir>/template/static/style.css  <output_root>/static/style.css
cp <skill_dir>/template/static/favicon.png <output_root>/static/favicon.png
python3 <skill_dir>/template/_build/build_config.py --raw <output_root>/_raw
python3 <skill_dir>/template/_build/fit_weights.py --raw <output_root>/_raw
```

`build_config.py` renders `spec.json` into `config.json` with the
policy-default weights and JF ranges; `fit_weights.py` nudges the factor
blend toward the gold set (see "Default weights + calibration") and rewrites
`config.json` in place. Surface the `_raw/_weight_fit_report.json` summary to
the user (default vs fitted held-out AUC, adopted or not). Do NOT hand-edit
`config.json` — fix the spec and re-run the scripts instead.

App behaviour (tabs, filters, badges, Save button, Download score sheet,
weights overlay) is implemented in the template and documented in
`template/README.md` — don't restate it in the generated README.

### Stage 4 — Calibrate (run instructions)

Print to the user (do **not** try to launch the server inside the agent —
let the user start it in a real terminal):

```bash
cd ./tmp/people_scoring/<company>
python app.py 8002
# open http://localhost:8002 — tune the sliders, then click Save
```

Tell them the loop: tune sliders → **Save** (writes
`people-scoring-weights.json` AND regenerates `score.csv`) → that file
drives the production scorer in Stage 5. **Download score sheet** exports
the current sliders' sheet. `data.csv` here is only the calibration sample;
it is intentionally small. Before handing over, spot-check the `score.csv`
header (see Output).

Security: the generated `README.md` covers the no-auth warning and
127.0.0.1-only binding — don't restate it unless the user is about to expose
the port.

### Stage 5 — Score the full CRM in production

Once weights are calibrated, score the **entire** lead/CRM universe:

1. **Enrich the full list** with the same pipeline, no 5-company
   restriction: write the full `_raw/contacts.csv` (all CRM people), run
   `fetch_people.py --raw <prod_raw> --lean` (6 credits/person instead of 9;
   match-mode batches of 1000 handle tens of thousands of rows; skills come
   back on every row via the `technologies` attribute), then
   `merge_data.py` → `leads_enriched.csv` (rename/copy the produced
   data.csv). **Surface the credit estimate first** (`--estimate-only`) —
   a 30K-contact CRM at 6 credits/person is ~180K credits; for
   Sumble-internal runs the free internal route (DuckDB
   `sumble_people_info`) is the cheaper alternative — offer both.
2. **Score it** (stdlib, no browser, no row cap):

```bash
python score_leads.py \
  --leads leads_enriched.csv \
  --weights people-scoring-weights.json \
  --out scored_leads.csv
```

Offer to build `leads_enriched.csv` when the user is ready — but only after
weights are calibrated, so the expensive full-CRM enrichment happens exactly
once, against final weights.
