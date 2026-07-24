# Example: account scoring (Sumble's own ICP)

A real, runnable example of what the [`account-scoring`](../../skills/sumble-account-scoring)
skill produces — built against Sumble's own ICP over a universe of ~4,090 public
companies. Drag the sliders, watch the ranking re-sort, click a row for the
per-signal breakdown.

**▶ Live demo: https://account-scoring-demo.sumble.com/**

> ## ⚠️ The "gold" set here is FICTITIOUS
>
> The **account universe is real** (public companies and their public Sumble
> signals). But the `is_icp_gold` flags — the accounts marked as "customers" /
> won deals — are a **fabricated, illustrative set**, not Sumble's real customer
> list. They're a deterministic mix designed only to make the Evaluation tab and
> the fit-to-gold behaviour realistic for a demo. **Do not interpret any flagged
> account as an actual Sumble customer.** Real CRM identity columns have been
> removed from the data, and the weights were re-calibrated against this fake
> gold set.

## Run it

```bash
python app.py        # then open http://localhost:8001
```

Stdlib only — no `pip install`, no virtualenv. Needs Python 3.10+. Override the
port with `python app.py 9001` or `PORT=9001 python app.py`.

## What's here

| File | What it is |
|---|---|
| `app.py` | The zero-dependency web app (stdlib `http.server`). |
| `account-scoring-weights.json` | The model: signals, weights, p99s, formula metadata. `customer_name` is labelled DEMO. |
| `data.csv` | One row per company: real universe + signals, with the **fictitious** `is_icp_gold` flags. CRM identity columns removed. |
| `score_sheet.py` / `score_accounts.py` | The scored-sheet builder and the portable public-API scorer. |
| `static/` | The UI. |

`score.csv` is regenerated from `data.csv` + the weights on startup and on Save
(it's git-ignored here).
