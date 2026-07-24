# Building the interactive HTML brief (Step 5d)

A single self-contained `.html` — a clickable page where each **signal** expands into the
play, the call, what to test, who to reach, and their reporting line. Template:
`assets/intelligence-brief-template.html` (fan-out JS + styling baked in; you fill the
`{{TOKENS}}` and duplicate the repeating blocks). Opens anywhere — no build step, no
embedded fonts. Build from the Step 5 research you already ran; no new queries. One
signal → one card → one play. **Hold every line to `references/writing-rules.md`.**

**Sumble-branded by design** — an internal research artifact ("Sumble Intelligence"), not
prospect-facing, so it skips `references/branding.md`. The template already carries the
brand: one emerald accent (`#16a34a`) on slate/white, the hosted Sumble mark, Inter.
Don't recolor it to the prospect or the seller.

## Map the plays to pills + badges

The pills and badges are the user's **sales plays** — already settled in the Step 3
profile (and the play(s) you're chasing for this account). Don't re-pick them here; just
map them onto the template:

- the **filter pills** (`data-filter` = a slug of the play name; keep `All plays`),
- each signal's **badge** and **`data-play`** (must match a pill's slug).

If the profile has no distinct named plays, keep only the `All plays` pill and drop the
badges — the cards still work; they just aren't play-filtered.

## Fill the shell

| Token | What goes in |
|---|---|
| `{{ACCOUNT}}` | Company name (nav, hero pill, footer, sources). |
| `{{MONTH_YEAR}}` | e.g. `June 2026`. |
| `{{RECIPIENT}}` | Who it's for (the rep / their manager), or omit. |
| `{{CONTEXT}}` | Short framing, e.g. `Account brief` or `Expansion`. |
| `{{HEADLINE}}` | The one-line "so what" for the whole account — a consequence, not a topic. |
| `{{ACCOUNT_NARRATIVE}}` | 2–4 sentences on the situation + why now. NOT a recap of the signals. |
| `{{SUMBLE_ORG_URL}}` | `sumble.com/orgs/<slug>/overview`. |
| `{{AUTHOR}}` / `{{AUTHOR_EMAIL}}` | The seller, or omit. |

## Fill each signal card (duplicate `.signal-card` per signal)

Order strongest-first; each card maps one Step 5b signal to one play.

- **`sig-num`** — `01`, `02`, … in order.
- **`sig-title`** — the "so what" in one line (the consequence, not the artifact).
- **`sig-sub`** — `team · one-line evidence` (mono, truncates — keep it short).
- **`sig-badge`** + **`data-play`** — the play (slug must match the pill).
- **Signal box** (`.trigger-text`) — the evidence; lead with the confirmed tech or hiring
  signal, hyperlink the org + the single strongest job posting to Sumble.
- **Stack** (`.stack-tags`) — `um-strong` = tech confirmed in their profile; `um-weak` =
  competitor / displacement tech, or postings-only (not confirmed adopted). Append counts
  (`Splunk 42/81`) only from a real `RunSqlQuery` pass — never invent them.
- **The call** (`.call-line`) — **one quoted sentence in the seller's voice**: what the
  rep *says to the prospect*. **Never Sumble vocabulary** — no "used/mentioned", "N
  postings", "Sumble sees", no raw counts. Say what a rep says ("you're running Splunk at
  real scale — what are you paying that you shouldn't be?"). Counts stay in the Signal box
  and Stack.
- **What to test** (`.detail-col p`) — the discovery question as the rep's curiosity
  ("how's the Splunk renewal going?"), not a metric. Bold the key qualifier. Natural
  sentences, no "**Label:** sentence" bullets.
- **Sources** — `Sumble · {{ACCOUNT}} profile` link plus any web sources.

## Contacts + the reporting fan-out

**Freshness gate first (SKILL.md Step 5c).** Only include people *currently at the
company*. Verify each name (web / current LinkedIn role) before it goes on a card.
Departed → drop (don't list, don't anchor a fan-out, don't reveal). Active but with a
stale Sumble record (wrong title / mislabeled / 0 reports) → keep, but show the
**verified current title** (not the Sumble one) and note the record is stale. Same for
fan-out reports: a departed report comes off the line.

Per card, surface the Step 5c people (economic buyer, champion/user, multithread — 2–3).
Each is a `.contact-row`: avatar initials, name, then **both a LinkedIn link and a Sumble
people-page link** (`.plinks` → `LinkedIn · Sumble`), title, and `location · why-this-person`
(tied to the play's persona). Then a `.fan` block per contact — their **direct reports**
(who rolls up to them, `▼`), each row carrying the **real Sumble 1–10 confidence** and its
own LinkedIn + Sumble links.

**One call gets the scores + both links.** `FindMatchAndEnrichPeople` in **match mode**,
batching all a card's contacts by `person_id`/`linkedin_url`, with the reporting line and
its confidence requested *inside* `related_people` (the inner `attributes` is what returns
names/titles/links/scores — omit it and you get bare ids with no score):

```
attributes: ["name","job_title","job_level","linkedin_url"]
related_people: { direction: ["direct_reports"],
                  attributes: ["name","job_title","job_level","linkedin_url","confidence"] }
```

1. **Sumble link** = each person's free `sumble_url` (`https://sumble.com/l/person/…`),
   returned on the contact **and** every related person. Put it next to the LinkedIn link on
   every row — anchor contacts and fan rows alike. That Sumble page is where the user sees
   the full confidence-scored roll-up.
2. **Score** (`.fan-rank`) = each related person's `confidence.score` (a 0–1 float at the
   **top level** of the report object, *not* under `attributes`). Convert to the web app's
   1–10 exactly: `ceil(score*100)/10` (`0.3865 → 3.9`, `0.51 → 5.1`). These are the same
   numbers on the person's Sumble page. Rank each contact's `direct_reports` by score, show
   the **top ~5**.
3. **Direction.** Use `direct_reports` (`▼`). The `managers` (up) direction is near-empty
   for senior contacts (a CXO/SVP rarely has an inferred manager) — don't render an empty
   `▲` fan; express the path-to-buyer in prose instead.
4. **Noisy / off-target line → don't show a misleading fan.** Common for CXOs (e.g. a CISO
   whose top "reports" are physical-security or strategy people, or a CDAO whose Sumble
   record is stale with 0 reports). Render a `.fan-none` note ("reach them through the
   champion") instead of padding. Never invent reports.
5. The response is large and usually spills to a file — read it back with `jq`
   (`.people[].related_people.direct_reports | sort_by(-.confidence.score)`), not inline.

Apply this to **every** recommended contact — the economic buyer and the champion both get
the dual links and their scored reporting line, exactly as on the Sumble people page.

**Load-bearing honesty:** the fan-out is an *inferred* map from shared signals (tech,
function, team, title, location) — the same figure shown on each person's Sumble page — a
suggested map, **not** a confirmed org chart, and the score is confidence-the-person-sits-in-
that-line, **not** confidence-the-play-lands. Keep the `.orgtree-note` disclaimer.

## Deliver

Write the `.html` and hand it back (Claude Code / connected folder → disk; ephemeral chat
→ downloadable file). Reveal email/phone for top contacts only if the user wants to act
(Step 5e) — the brief stands on its own without reveals.
