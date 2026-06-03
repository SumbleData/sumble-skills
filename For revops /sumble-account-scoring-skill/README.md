# Sumble Account Scoring Skill

A Claude Code skill that turns a sales team's ICP and GTM motion into a working
**account-scoring web app**. Pulls signal data from Sumble (via the
[Sumble MCP server](https://sumble.com/docs/mcp)), optionally joins in any
first-party data you have (CRM intent, past purchases, engagement), and
generates a self-contained FastAPI + HTML/JS app you can run locally and
tweak weights with sliders.

The slider-driven workflow mirrors the
[approach Sumble uses internally](https://blog.sumble.com/how-sumble-scores-your-accounts)
to build customer scoring models — generalised so any account team can
onboard their own.

## What you get

After running the skill, you'll have:

```
account_scoring/<your-customer-name>/
  app.py                          stdlib http.server (no deps)
  account-scoring-weights.json    signals, weights, p99s, data-source metadata
  data.csv                        one aggregated CSV — Sumble + 1P merged by org_id
  static/                         UI: sliders, table, per-row breakdown
  README.md                       how to run
```

Start the server, open `http://localhost:8001`, drag sliders, watch the
ranking update in real time. Click a row to see exactly which signals are
driving its score.

## Requirements

- **Claude Code** (the CLI from Anthropic).
- **Sumble MCP server** configured in your Claude Code MCP settings. See
  https://sumble.com/docs/mcp. You'll need a Sumble account with API
  access — sign up at https://sumble.com.
- **Python 3.10+** for the generated FastAPI app.

## Install

Copy the skill folder into your user-level Claude Code skills directory:

```bash
git clone https://github.com/SumbleData/sumble-account-scoring-skill.git
ln -s "$PWD/sumble-account-scoring-skill" ~/.claude/skills/sumble-account-scoring
```

Or, if you prefer a copy you can edit in place:

```bash
git clone https://github.com/SumbleData/sumble-account-scoring-skill.git \
  ~/.claude/skills/sumble-account-scoring
```

Restart Claude Code. The skill is available as `/sumble-account-scoring`.

## Use

In Claude Code, type:

```
/sumble-account-scoring build for <your customer name>
```

Claude will walk you through a short interview, pull the right Sumble data,
and generate the scoring app at `account_scoring/<customer>/`. The
generated `README.md` in that folder explains how to start the app.

## Structure

```
sumble-account-scoring-skill/
  SKILL.md             instructions Claude follows when the skill is invoked
  template/            files copied verbatim into each generated app
    app.py
    requirements.txt
    config.example.json
    README.md
    static/
      index.html
      app.js
      style.css
  README.md            this file
```

The generated `app.py` is the same across customers — the per-customer
customisation lives entirely in `account-scoring-weights.json` and
`data.csv`. Improving the template once improves every customer's app
on regeneration.

## License

MIT.
