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

Per card, surface the Step 5c people (economic buyer, champion/user, multithread — 2–3).
Each is a `.contact-row`: avatar initials, name → LinkedIn, title, `location ·
why-this-person` (tied to the play's persona). Then a `.fan` block per contact — people
above (`▲`) and below (`▼`):

1. `FindMatchAndEnrichPeople` with **`related_people`**, once per contact (1 cr per
   related person). Returns each person's direction + LinkedIn/Sumble URLs.
2. **Score** (`.fan-rank`) = Sumble's match/relatedness confidence the person sits in that
   line. Normalize the 0–1 score like the web app: `max(0.1, ceil(score*100)/10)` (`0.56
   → 5.6`, `0.65 → 6.5`).
3. **No numeric score → don't fabricate:** render `fan-rank na` with `—`, keep the people,
   and note in `.orgtree-note` that the number wasn't available.
4. ~2 above + ~3 below, strongest first. No related people → `.fan-none` note; never pad
   with invented reports.

**Load-bearing honesty:** the fan-out is an *inferred* map from shared signals, not a
confirmed org chart, and the score is confidence-the-person-is-in-that-line, **not**
confidence-the-play-lands. Keep the `.orgtree-note` disclaimer. "Above" is often sparse
for senior contacts — show what's there.

## Deliver

Write the `.html` and hand it back (Claude Code / connected folder → disk; ephemeral chat
→ downloadable file). Reveal email/phone for top contacts only if the user wants to act
(Step 5e) — the brief stands on its own without reveals.
