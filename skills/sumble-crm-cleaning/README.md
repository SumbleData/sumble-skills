# sumble-crm-cleaning

Skill that builds a CRM-cleaning review web app from a CRM account list +
Sumble's organization graph. Finds potential **duplicate accounts** and
**missing/conflicting parent–subsidiary links**, and emits an `actions.csv`
of approved changes.

- Workflow: `SKILL.md` (interview → fetch → analyze → app)
- Pipeline internals + detection policy: `template/_build/README.md`
- Data source: `POST https://api.sumble.com/v6/organizations` only
  (attributes incl. `parent_id`/`subsidiary_ids`; parent orgs resolved by
  Sumble `id`). No SQL / RunSqlQuery anywhere.
- Output app: zero-dependency stdlib Python + vanilla HTML/JS, modeled on
  `sumble-account-scoring`.
