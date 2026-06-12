# `_build/` — CRM-cleaning pipeline internals

Three scripts, run in order, all taking `--raw <output_root>/_raw`:

1. `fetch_orgs.py` — match `accounts.csv` to Sumble orgs via
   `POST /v6/organizations` (attributes only, no entity selections), then
   resolve non-CRM ancestor orgs by Sumble id (`MAX_PARENT_HOPS = 3`).
2. `analyze.py` — pure, deterministic detection. Writes
   `<output_root>/findings.json` + `findings.csv`.

(`set_api_key.py` / `set_api_key.sh` save the Sumble API key to
`~/.config/sumble/api_key`, chmod 0600 — shared with the other Sumble skills.)

## `_raw/accounts.csv` (the input the agent writes in Stage 1)

| column | required | notes |
|---|---|---|
| `crm_account_id` | yes | CRM/Salesforce account id — the join key for every finding |
| `name` | yes | account name (used for Sumble matching) |
| `domain` | yes* | website domain/URL (*strongly recommended — the strongest Sumble-match signal) |
| `parent_crm_id` | no | the CRM's OWN parent link (SF `ParentId`); enables conflict detection and suppresses already-correct links |
| `owner` | no | rep/owner name or id; drives the survivor suggestion |
| `is_customer` | no | 1/true for customers; drives the survivor suggestion |
| `created_date` | no | ISO date; tiebreak for the survivor suggestion (older wins) |

## `_raw/accounts_meta.csv` (optional display-only sidecar)

Extra CRM metadata for the review UI, keyed by `crm_account_id`. Never used
as detection evidence — `analyze.py` merges it into each account payload as
`crm_city` / `crm_state` / `crm_country` / `crm_linkedin_url` /
`crm_last_modified`, and the app shows a CRM-location column, a LinkedIn
link, and the last-modified date. All columns optional:
`crm_account_id, city, state, country, linkedin_url, last_modified`.
Adding or editing it only requires re-running `analyze.py` (no re-fetch,
no credits).

## `_raw/config.json`

```json
{
  "company": "Acme",
  "checks": ["duplicates", "parent_sub"],
  "crm_url_template": "https://acme.lightning.force.com/lightning/r/Account/{id}/view",
  "crm_source": "salesforce Account export, 2026-06-11"
}
```

`crm_url_template` (optional): the CRM's record URL pattern; `{id}` is
replaced with each account's CRM id to produce a `crm_url` per account
(linked from every account name in the UI, plus a `crm_url` column in
`findings.csv`). Omit → names render unlinked.

## `_raw/org_alternates.json` (optional display-only sidecar)

Alternate names/domains Sumble knows for matched orgs, keyed by Sumble org
id: `{"<org_id>": {"name_alternates": [...], "url_alternates": [...]}}`.
`analyze.py` merges them into account payloads
(`sumble_name_alternates` / `sumble_url_alternates`) and the UI shows them on
each finding's "Sumble match:" line — clarifying WHY accounts resolved to the
same org. Never used as detection evidence. The public `/v6/organizations`
endpoint does not expose alternates yet, so this file is populated
out-of-band (e.g. from Sumble-internal data); absent → no-op. Adding or
editing it only requires re-running `analyze.py` (no re-fetch, no credits).

## Policy constants (in the scripts, not per-run choices)

| constant | value | where |
|---|---|---|
| `BATCH` | 250 orgs/call | fetch_orgs.py |
| `MAX_PARENT_HOPS` | 3 ancestor levels resolved above the CRM's orgs | fetch_orgs.py |
| `MAX_ANCESTOR_DEPTH` | 6 — hierarchy-walk cycle guard | analyze.py |
| `LEGAL_SUFFIXES` | inc/llc/gmbh/… stripped from name ENDS only (dissimilar-names note) | analyze.py |

## Duplicate evidence → confidence

| evidence | meaning | tier |
|---|---|---|
| `same_sumble_org` | both accounts resolve to one Sumble org | high |

`same_sumble_org` is the ONLY duplicate evidence: Sumble's matcher
(`POST /v6/organizations`) mapping two CRM accounts to the same org id. No
domain or name-similarity matching. Pairs already linked parent↔child in the
CRM are never duplicate evidence. Clusters with very dissimilar CRM names
carry a note to check for a parent/subsidiary pair both matching the parent.
Survivor suggestion order: has owner > is customer > most non-empty fields >
oldest `created_date` > lowest id.

## Parent/subsidiary findings

For each matched account, walk its Sumble `parent_id` chain (nearest first):

- First ancestor that is another CRM account →
  - CRM parent unset → `missing_parent_link` (high if direct parent, medium
    beyond one hop)
  - CRM parent set but NOT in the Sumble chain → `parent_conflict` (medium)
  - CRM parent already in the chain → consistent, no finding
- No ancestor in the CRM but a Sumble parent exists → `parent_not_in_crm`
  (info), grouped one finding per missing parent org with all its CRM children.

## Credit cost

`fetch_orgs.py` requests 4 paid attributes (`employee_count`,
`headquarters_country`, `parent_id`, `subsidiary_ids`) →
**~5 credits per matched account** (1 base + 4), plus the same per resolved
ancestor org (usually a small fraction of the account count).
