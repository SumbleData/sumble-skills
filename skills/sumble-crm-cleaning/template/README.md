# CRM Cleaning — review app

Findings from matching your CRM account list against Sumble's organization
graph. Two kinds of problems are surfaced:

1. **Duplicates** — CRM accounts that look like the same company (same Sumble
   org, same domain, same/similar name).
2. **Hierarchy gaps** — accounts whose Sumble parent (or grandparent) is
   another CRM account, but the CRM has no parent link (or a conflicting one);
   plus parent companies missing from the CRM entirely.

## Run the app

```bash
python3 app.py
# open http://localhost:8002
```

No pip install, no venv — stdlib only, Python 3.10+. Custom port:
`python3 app.py 9002` or `PORT=9002 python3 app.py`.

## Reviewing

- **Accept** a finding when the suggested change is right; **Reject** when it
  isn't; **Skip** to defer. Every click saves to `decisions.json` immediately.
- In a duplicate cluster, the **Keep** radio picks the surviving record (the
  app pre-selects a sensible default: owned > customer > most complete >
  oldest).
- **Export actions.csv** writes one row per CRM change implied by your
  accepted findings:
  - `merge` — fold `account_id` into `target_account_id`
  - `set_parent` — set `target_account_id` as the parent of `account_id`
  - `create_parent_and_link` — create the suggested parent account, then
    parent `account_id` under it

## Files

| File | What it is |
|---|---|
| `findings.json` | Everything the app shows (read-only; regenerate via `_build/analyze.py`) |
| `findings.csv` | Flat spreadsheet export of all findings (decision-independent) |
| `decisions.json` | Your accept/reject/skip choices, survivor picks, notes |
| `actions.csv` | The change list for your CRM admin, from accepted findings |
| `_raw/` | Inputs + raw API responses (accounts.csv, config.json, responses/) |

## Re-running

Data refresh (new CRM export → new findings; decisions for unchanged finding
ids are kept):

```bash
python3 _build/fetch_orgs.py --raw _raw
python3 _build/analyze.py  --raw _raw
```
