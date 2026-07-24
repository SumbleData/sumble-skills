# Building the interactive HTML brief (Step 5d)

A single self-contained `.html` — a clickable page where each **signal** expands into the
play, the call, what to test, who to reach, and their reporting line. Template:
`assets/intelligence-brief-template.html` (fan-out JS + styling baked in; you fill the
`{{TOKENS}}` and duplicate the repeating blocks). Opens anywhere, offline — no build step,
no external requests, no embedded fonts (see the licence note below). Build from the Step 5 research you
already ran; no new queries. One signal → one card → one play.
**Hold every line to `references/writing-rules.md`.**

**Sumble-branded by design** — an internal research artifact ("Sumble Intelligence"), not
prospect-facing, so it skips `references/branding.md`. The template already carries the
brand: one emerald accent (`#16a34a`) on slate/white and the base64-embedded Sumble mark.
Don't recolor it to the prospect or the seller.

**Brand fonts — do NOT embed.** The NEXT brand faces (NextPoster / NextBook) are licensed
from **Optimo Sàrl**, not owned. Their EULA (optimo.ch/information-eula) prohibits
redistribution outright — *"not to copy, resell, redistribute, sub-license, or transfer by
any technical means the Font Software to third parties"* (§5) — and permits embedding into
documents only in a *"secured read-only mode"* where recipients *"cannot extract or use the
embedded Licensed Fonts"* (§2.1.1). A base64 data-URI in a plain `.html` fails that test:
anyone can view-source and decode it. So:

- **Never bundle the woff2 files into this skill.** This skill is published publicly at
  `github.com/SumbleData/sumble-skills-public` and offered as a download from sumble.com —
  shipping the fonts there is redistribution.
- **Never base64-embed them into a brief**, including internal ones. The extraction test
  fails either way, and briefs get forwarded.
- The template's `--font-display` / `--font-body` tokens *name* NextPoster/NextBook first
  (naming a family is not distribution). On a machine with the fonts installed under a
  desktop licence the brief renders on-brand for free; everywhere else it falls back
  cleanly to Inter → system-ui. That is the intended behaviour — **do not "fix" it.**

If a genuinely on-brand, portable deliverable is ever needed, that is a licensing question
for whoever holds the Optimo Order (an ePub/app-tier licence or written permission), not
something to solve in this skill.

**Don't use file size as a check.** With the embedded logo a finished brief is roughly
60–110KB depending on how much you write. Size tells you nothing about whether the template
was used — the class markers below do. (Briefs built before v10 run 150–220KB because they
embedded fonts; that's the old, retired behaviour, not a target.)

**Self-check before you hand it over.** The file must contain: `signal-card`,
`trigger-box`, `stack-tags`, `contact-row`, `fan` / `fan-rank` / `fan-none`, `detail-col`,
`sources`, `contact-role`, the sticky `nav`, the three closing `legend-box` blocks and the
dark `footer`. It must contain **no `@font-face`** (see the licence note above). It must
make **zero remote requests** — no
external `<link>`, `<script>` **or `<img src="http…">`** (the logo is base64-embedded in the
template; keep it that way). Grep for `https?://` inside `src=`/`href=` on `<link>`,
`<script>` and `<img>` before you ship — a broken logo on a plane is the giveaway. Every fan
row needs its score plus whichever of LinkedIn / Sumble exist for that person. If markers are missing
you wrote bespoke HTML instead of filling the template — start again from
`assets/intelligence-brief-template.html`.

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
  (`<Tech> 42/81`) only from a real `RunSqlQuery` pass — never invent them.
- **The call** (`.call-line`) — **one quoted sentence in the seller's voice**: what the
  rep *says to the prospect*. **Never Sumble vocabulary** — no "used/mentioned", "N
  postings", "Sumble sees", no raw counts. Say what a rep says ("you're running that at
  real scale — what are you paying that you shouldn't be?"). Counts stay in the Signal box
  and Stack.
- **What to test** (`.detail-col p`) — the discovery question as the rep's curiosity
  ("how's that renewal going?"), not a metric. Bold the key qualifier. Natural
  sentences, no "**Label:** sentence" bullets.
- **Sources** — `Sumble · {{ACCOUNT}} profile` link plus any web sources.

## Buying group + the reporting fan-out

The **buying group is defined in SKILL.md Step 5c** — the contacts, the scored reporting
lines (`related_people` + `confidence` → 1–10), both links per person, the path in, and the
"every person accounted for" rule. This section is just its **HTML rendering** (`.buygroup`
header, role chips, `.fan` blocks, `.plinks`); don't re-derive the data rules here — Step 5c
is the source of truth, and the same group feeds the deck, call-prep, and outreach
deliverables too.

**Freshness gate — full strength for contacts, lighter for fan rows.** A `.contact-row`
person is someone you're telling the rep to approach, so they get the full check: verify
currently in seat before they go on a card, no exceptions. A `.fan-row` person is context —
Sumble's inferred line, already labelled inferred — so verifying all 15–20 of them is
disproportionate. Rule: **verify every contact; fan rows may ship unverified, but then (a)
say so once in that card's `.orgtree-note`, and (b) never promote a fan-row person into a
`.contact-row`, or name them in `.bg-path`, without verifying them first.** Crossing from
context to recommendation is what triggers the gate.

Only include people *currently at the
company*. Verify each name (web / current LinkedIn role) before it goes on a card.
Departed → drop (don't list, don't anchor a fan-out, don't reveal). Active but with a
stale Sumble record (wrong title / mislabeled / 0 reports) → keep, but show the
**verified current title** (not the Sumble one) and note the record is stale. Same for
fan-out reports: a departed report comes off the line.

Every card ends in a **labelled buying group**: the team that owns the signal, the path to
the buyer, the role-tagged people, then each person's scored reporting line. Don't leave the
people as a bare list.

**1 · Team header (`.buygroup`).** Anchor the card on a **real, navigable Sumble team** —
never a noisy auto-cluster ("Manager", "AVP", a generic "Security"). The clean source is the
team that recurs across your contacts' `FindMatchAndEnrichPeople` `confidence.matched_features`
with `match_type:"team"` — it carries the team `name` **and `slug`**. Roster link is slug-form,
not numeric ids: `https://sumble.com/orgs/<org-slug>/teams/<team-slug>/people`, text **"See
who's on this team →"** (Sumble's inferred, confidence-scored membership, not a confirmed
roster).

**Roster-link copy is hedged, always.** Sumble team membership is *inferred and
confidence-scored*, never a confirmed roster, so the link never claims otherwise. Use exactly
— no quote marks in the rendered link:

    See who might be on this team →

**No curated team → walk down this ladder.** Some orgs surface only the generic org-level
cluster — its slug is just the org's own name; don't anchor on that. Take the first rung
that resolves, name the group by the function you're selling into, and say which rung you used
in `.bg-path` so the rep knows what they're clicking:

| Rung | Link | Link copy |
|---|---|---|
| 1. Real curated team | `/orgs/<org-slug>/teams/<team-slug>/people` — slug from a contact's `matched_features` `match_type:"team"` | `See who might be on this team →` |
| 2. Function-scoped people | the `people_count_url` returned by `FindMatchAndEnrichOrganizations` for a `job_function` entity (e.g. `Finance`) — org × function, far tighter than the org page | `See who Sumble links to <function> here →` |
| 3. Tech-scoped people | the `people_count_url` from a `technology` entity — everyone at the org listing that tech | `See who here lists <tech> →` |
| 4. Last resort | `/orgs/<org-slug>/people` | `See who Sumble links to this org →` |

Rungs 2 and 3 come free with entity metrics you already requested in Step 5b — you don't need
an extra call, just keep the `*_count_url` fields instead of discarding them. Prefer them over
rung 4: a rep clicking "the whole org" on a 3,000-person account gets nothing usable.
**Never invent a team slug to make rung 1 work** — if you didn't see the slug in
`matched_features`, you don't have a team, so drop to rung 2.

**2 · Path in (`.bg-path`).** One line naming the entry point and the buyer above it:
`{{champion}} (champion) → {{economic buyer}} (economic buyer)`. Don't render an empty "above"
fan for a senior contact whose inferred manager is missing — just name the path here.

**No champion on a card?** Sometimes the natural champion seat is an **open requisition**, or
everyone on the card is a buyer/blocker. Don't invent a champion and don't force the chip onto
someone who doesn't fit. Say what's actually true in `.bg-path` — e.g. `Head of Treasury role
open (posted 9 Jun) → Tracy Farr (economic buyer); the vacancy is the timing lever` — and let
the card carry buyer + multithread chips only. An unfilled req next to a stated mandate is
often the sharpest why-now on the page; treat it as a signal, not a gap.

**Repeating a contact across cards.** The economic buyer usually belongs on more than one
card. Give them the chip on the cards where they're genuinely the decision-maker for that
signal; elsewhere name them in `.bg-path` only. Don't repeat the same chip on all five cards —
it reads as padding and inflates the contact count.

**3 · Contacts (`.contact-row`), each with a role chip + both links.** The 2–3 Step 5c people
— avatar initials, name with **LinkedIn + Sumble** links (`.plinks`), title, `location ·
why-this-person` (the play's persona) — plus a **`.contact-role` chip**: `Economic buyer` /
`Champion` (green) or `Multithread` (`class="contact-role multi"`, slate). The role is a
visible label, not buried in the prose.

**4 · Reporting fan-out (`.fan`)** — a `.fan` block per contact: their **direct reports** (who
rolls up to them, `▼`), each row carrying the **real Sumble 1–10 confidence** and its own
LinkedIn + Sumble links.

**Every listed contact gets a block — no silent omissions.** For each contact on the card,
render **either** their own `.fan` (their reporting line) **or** a `.fan-none` note that says
why there isn't one — *no reports mapped in Sumble*, *shown as a report under {anchor} above
({score})*, or *reporting line already shown on the {other} card*. Never list a contact and
leave their line out: if you didn't pull it (you batched only some anchors, or they're a VP
with no mapped reports), say so and point the rep to reach directly. **Self-check before
delivering: per card, exactly one `.fan` block per `.contact-row` — each `.fan` contains
either a `.fan-branch` of scored rows or a single `.fan-none` note, never neither.**
(`.fan-none` nests *inside* a `.fan`, so count `.fan` blocks, not both.) Don't repeat an
identical fan across cards — cross-reference it ("line shown on card N") instead.

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
   **`sumble_url` sits at the TOP level of each related-person object, NOT under
   `attributes`** — the single easiest thing to lose. A `jq` that only walks
   `.attributes.*` silently drops every fan-row Sumble link. Extract both together:
   ```bash
   jq -r '.people[] | "=== \(.attributes.name)",
     (.related_people.direct_reports // [] | sort_by(-(.confidence.score//0)) | .[:5][]
      | "  \((.confidence.score*100|ceil)/10)\t\(.attributes.name)\t\(.attributes.job_title)\t\(.attributes.linkedin_url)\t\(.sumble_url)")' <saved-result>.txt
   ```
   **Same person, two Sumble URLs.** The API can return different `l/person/…` ids for one
   human depending on whether they came back as a direct match or inside `related_people`.
   Both resolve. Convention: **use the direct-match URL on `.contact-row`s and the
   related-people URL on `.fan-row`s** — each link then matches the call it came from — and
   note the split once in the caveats `legend-box`. Don't try to reconcile them, and don't
   drop one. If the same name shows two *different people's* titles, that's a genuine
   duplicate-record issue: flag it in caveats and use the one you verified.

   **Missing-link fallback.** Some people have a LinkedIn URL but no Sumble record (or the
   reverse). Render whichever link(s) exist — never fabricate a URL, never drop the row —
   and if any row on a card is single-linked, say so once in that card's `.orgtree-note`
   (e.g. "rows without a Sumble link had no matched Sumble person record"). Contacts with
   no Sumble page at all also get a line in `.contact-loc` saying they were verified
   independently.
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
