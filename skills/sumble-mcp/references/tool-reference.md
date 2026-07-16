# Sumble MCP Tool Reference

This reference is the standalone operating guide for the Sumble MCP skill.

## Required first step for most sessions

Before running any other Sumble tool, call `GetMyCompanyProfile` first.

Use it to pull:

- company summary and sales plays
- key and other-tier technologies
- key and other-tier tech concepts
- key and other-tier job functions
- key and other-tier projects

Exceptions:

- checking credits with `GetAccountInformation`
- the user already supplied complete targeting criteria in the current session

## `reason` parameter

When a Sumble tool exposes a `reason: str` parameter, make it specific and tied
to the actual action, not a generic placeholder.

Good:

- `Checking AI hiring signals in my territory`
- `Resolving Snowflake to Sumble technology slugs`
- `Finding data engineering leaders at Stripe`

Bad:

- `user asked`
- `research`

## Tool inventory

### Free account tools

| Tool | Purpose |
|---|---|
| `GetMyCompanyProfile` | Pull ICP, competitive landscape, key personas, and project signals. Usually call first. |
| `GetAccountInformation` | Check API key validity, credits, and plan information. |
| `ReportDataQualityIssue` | Report incorrect, missing, or stale Sumble data. Routed to the Sumble data team. |
| `SubmitSupportRequest` | Submit a general account, billing, or product support request. Routed to the Sumble support team. |

### Organization search and enrichment

| Tool | Purpose | Cost |
|---|---|---|
| `FindMatchAndEnrichOrganizations` | Find, match, and enrich organizations in one call. Use advanced query filters or resolve supplied names, URLs, or IDs; request only the attributes and technology/job/team/people metrics needed for the task. | 1 credit per matched org + 1 per paid attribute + per-entity metric costs |
| `GetIntelligenceBrief` | Generate an LLM sales intelligence brief for one target account from Sumble structured data. Use only after narrowing to a high-priority account. | 50 credits per completed brief |

### Jobs

| Tool | Purpose | Cost |
|---|---|---|
| `FindMatchAndEnrichJobs` | Find, look up, and enrich job postings in one call. Search with advanced query filters or enrich a list of `job_id`s; request only the attributes needed (the full `description` is a paid attribute). To scope to companies, resolve them to IDs first and pass the `organization_ids` param; for saved lists pass the `organization_list_id` param (prefer both over the query language's fuzzy `organization` / `organizations_list` nodes). Optional `related_people` returns hiring managers and adjacent team members per job. | 1 credit per job + 1 per paid attribute (title is free) + 1 per related person returned |

### People

| Tool | Purpose | Cost |
|---|---|---|
| `FindMatchAndEnrichPeople` | Find, match, and enrich people in one call. Resolve person IDs, LinkedIn URLs, or emails (match mode), or search within organizations (filter mode — `organization_ids` and/or `organization_list_id` is REQUIRED) with advanced query filters; request only the attributes needed. The `person_score` attribute ranks people 0-100 against the account's ICP (filter mode, single org only). Optional `related_people` (inferred managers and direct reports) and `email`/`phone` contact reveals. | 1 credit per person + 1 per paid attribute (name is free) + 1 per related person; matching by email costs 20 extra credits when it resolves (unresolved is free); 10 credits per first email reveal, 80 credits per first phone reveal, free on repeat reveals of the same type or if unavailable |

### Signals

| Tool | Purpose | Cost |
|---|---|---|
| `SearchSignals` | Search Sumble Signals (champion moves, hires and promotions, technology/product mentions, projects, hiring trends) across accounts. Filter by signal IDs, organization IDs, person IDs, technology slugs, job functions, priorities, or saved organization lists; filters AND together, values within a filter OR. Job-post signals include ranked `suggested_contacts`. | 1 credit per signal returned |
| `SearchPrioritySignals` | Search the user's Priority Signals digest items by source signal IDs, organization IDs, person IDs, or job post IDs. Returns the most recent 20 matches. | 1 credit per priority signal returned; empty results free |
| `GetOrganizationSignals` | Recent sales signals for ONE target account by Sumble organization ID (resolve names/domains with `FindMatchAndEnrichOrganizations` first). Optional technology-slug filter. Use for "what changed at X" and why-reach-out-now angles. | 1 credit per signal returned |

Signals return `sumble_url` deep links plus `person_id` / `job_post_id` fields
you can feed into `FindMatchAndEnrichPeople` / `FindMatchAndEnrichJobs` for
follow-up research.

### Organization lists

| Tool | Purpose | Cost |
|---|---|---|
| `ListOrganizationLists` | List org lists with IDs, URLs, counts, read-only/deletable flags, deleted status, and Signals inclusion settings. Prefer `type = group` when the user says "my accounts" or "my territory". | 1 credit per list |
| `GetOrganizationList` | Fetch contents of one org list, including each organization's Sumble profile URL and own website URL. | 1 credit per org |
| `CreateOrganizationList` | Create an empty org list. | Free |
| `AddOrganizationsToList` | Add organizations by IDs or slugs. | Free |
| `SetOrganizationListDeleted` | Soft-delete an org list, or restore a deleted one. | Free |
| `SetOrganizationListSignals` | Include or exclude a list's accounts from future Signals delivery (lists are included by default). | Free |

### Contact lists

| Tool | Purpose | Cost |
|---|---|---|
| `ListContactLists` | List contact lists and metadata. | 1 credit per list |
| `GetContactList` | Fetch people in a contact list. | 1 credit per person |
| `CreateContactList` | Create an empty contact list. | Free |
| `AddContactsToList` | Add people by Sumble person IDs. | Free |

### Reference lookups

| Tool | Purpose | Cost |
|---|---|---|
| `SearchTechnologies` | Fuzzy free-text technology discovery ("what does Sumble call X?"). | 1 credit per search |
| `LookupTechnologies` | Resolve a batch of technology names, slugs, or aliases to canonical IDs, slugs, names, and categories. Prefer this over repeated `SearchTechnologies` calls when you already know the names. | 1 credit per 100 matched technologies |
| `LookupTechnologyCategories` | Resolve technology category slugs or names to canonical categories and their constituent technologies. | 1 credit per 100 matched categories |
| `LookupJobTitles` | Resolve raw job titles to canonical job function and level for use in filters. | 1 credit per 100 matched titles |
| `LookupProjects` | Resolve project names or slugs to canonical IDs, slugs, and names. | 1 credit per 100 matched projects |

### Database

| Tool | Purpose | Cost |
|---|---|---|
| `RunSqlQuery` | Read-only DuckDB SQL. Last resort only. Warn the user when using it. | 1 credit per 100 bytes of response |
| `ListTables` | List available DuckDB tables and columns before writing raw SQL. | Free |

## Query DSL notes

### Common organization filters

- `technology`: `EQ`, `IN`, `NOT IN`
- `technology_category`: `EQ`, `IN`, `NOT IN`
- `organization`: `EQ`
- `industry`: `EQ`, `IN`, `NOT IN`
- `employee_count`: `EQ`, `IN`, range strings like `'100-1000'`, `'1000-'`, `'-500'`
- `hq_location`: `EQ`, `IN`, `NEQ`, hierarchical values like `'US:Texas:Austin'`
- `tag`: `EQ`, `IN`
- `sic_code`: `EQ`
- `naics_code`: `EQ`

### Common job filters

- `organizations_list`: `EQ`, `IN`
- `project`: `EQ`, `IN`
- `job_function`: `EQ`, `IN`, `NOT IN`
- `job_level`: `EQ`, `IN`, `NOT IN`
- `country`: `EQ`, `IN`, `NOT IN`
- `hiring_period`: `EQ` only, one of `'1mo'`, `'3mo'`, `'6mo'`, `'1yr'`, `'18mo'`, `'2yr'`

### Common people filters

- `job_function`: `EQ`, `IN`, `NOT IN`
- `job_level`: `EQ`, `IN`, `NOT IN`
- `country`: `EQ`, `IN`, `NOT IN`
- `technology`: `EQ`, `IN`, `NOT IN`
- `hiring_period`: `EQ` only
- `since`: `EQ` only, `YYYY-MM-DD`
- `person_name`: `EQ`

### Guardrails

- Resolve technologies before passing `technologies`: `LookupTechnologies` for
  known names (batch, 1 credit per 100), `SearchTechnologies` for fuzzy
  discovery.
- Use `LookupJobTitles` to map raw titles to canonical job functions and levels
  before filtering on them.
- Scope jobs/people to companies via the `organization_ids` /
  `organization_list_id` parameters, not the query language's fuzzy
  `organization EQ '<name>'` or `organizations_list` nodes.
- People filter mode requires an organization scope
  (`organization_ids` and/or `organization_list_id`).
- Do not combine org filters with job filters using `OR`.
- Use full state names in country/location filters.
- `job_title` and `job_description` are not filterable. Use function and level.
- Prefer structured tools over `RunSqlQuery`.

## Technology category slugs

Use these exact slugs with `technology_category` or `technology_categories`:

`crm`, `business-intelligence`, `cloud-data-warehouse`, `data-catalog`, `gen-ai`, `mlops`, `ml-training`, `cybersecurity`, `cloud-security`, `ci-cd`, `ipaas`, `event-streaming`, `data-pipeline-orchestration`, `etl`, `logging-observability-monitoring`, `data-quality-and-observability`, `customer-data-platform`, `feature-flagging-and-a-b-testing`, `vector-database`, `oss-data-science`, `commercial-data-science`, `infrastructure-as-code-tools`, `design`, `javascript`, `siem`, `edr`, `headless-cms`, `ccaas`, `endpoint-management`, `ecommerce-platform`, `vibe-coding`, `coding-agents`, `marketing-automation-platforms`, `frontier-ai-models`, `processing-units-and-chips`, `cloud-and-container-orchestration-platforms`, `identity-and-access-management`

## Priority workflows

### P1: Book of business prioritization

Trigger: "here's my book, how do I prioritize it"

1. Call `GetMyCompanyProfile` and hold key tier categories, job functions, and projects in memory.
2. Call `ListOrganizationLists` and prefer a `group` list. If the user pasted raw names instead, use `FindMatchAndEnrichOrganizations` to resolve them, then `CreateOrganizationList` and `AddOrganizationsToList`.
3. Call `GetOrganizationList` for the chosen list.
4. Run one cheap signal pass with `FindMatchAndEnrichJobs`, passing the
   `organization_list_id` parameter for the chosen list plus the query:

```text
(project IN (<key_projects>) OR technology_category IN (<key_categories>))
AND hiring_period EQ '3mo'
```

   Optionally also call `SearchSignals` filtered to the list
   (`account_list_ids`) for champion moves and other non-hiring triggers.

5. Tier accounts:
   A. hiring signal on key projects or key categories
   B. weaker or older signals
   C. no recent signal
6. Present ranked evidence and stop before deeper enrich spend. Ask which A-tier accounts to deep-dive.

Budget: roughly 300 credits for a 100-account list. The key cost saver is using
one `FindMatchAndEnrichJobs` pass with few attributes and only requesting
expensive organization attributes or entity metrics after the list is narrowed.

### P2: Live demo, one account end to end

Trigger: demo flow, deep research to outreach in under 3 minutes

1. `GetMyCompanyProfile`
2. Get the target account from the user. Prefer domain.
3. `FindMatchAndEnrichOrganizations` for the target domain with only the key organization attributes and entity metrics needed for the demo.
4. `FindMatchAndEnrichJobs` for key projects in the last 6 months. Fallback to key job functions in the last 3 months.
5. `FindMatchAndEnrichJobs` again with the strongest signal's `job_id`, requesting the `description` attribute and `related_people` for the hiring manager.
6. Build the account brief inline.
7. `FindMatchAndEnrichPeople` for VP, Director, Senior Director, and Head roles in key functions.
8. `FindMatchAndEnrichPeople` with the `email` attribute for only 2-3 priority targets.
10. `CreateContactList` and `AddContactsToList` for everyone you want saved.
11. Draft two outreach variants:
    A. signal-led, using language from the job description
    B. reference-customer-led, using the company profile

Budget: roughly 100 credits.

### P3: Inbound MQL response

Trigger: "got this inbound, help me work it"

1. Extract person, company, and trigger.
2. `GetMyCompanyProfile`
3. `FindMatchAndEnrichOrganizations` first to match the account and check fit.
4. Stop if the account is a weak fit. Do not keep spending credits on a bad lead.
5. `FindMatchAndEnrichJobs` to identify the why-now initiative.
6. Decide whether the MQL is the buyer, a researcher, or a referrer.
7. If needed, `FindMatchAndEnrichPeople` for the real buyer.
8. If needed, `FindMatchAndEnrichJobs` with the active initiative's `job_id` and `related_people` for the hiring manager.
9. `FindMatchAndEnrichPeople` with contact-reveal attributes for at most two people.
10. Save the relevant people to a contact list.
11. Draft response and multithread outreach.

Budget: roughly 60-80 credits.

## Additional workflow patterns

### Tech-based prospecting

1. `GetMyCompanyProfile`
2. `SearchTechnologies`
3. `FindMatchAndEnrichOrganizations`
4. `CreateOrganizationList`
5. `AddOrganizationsToList`
6. Optionally request deeper attributes or entity metrics only for the top few accounts

### Champion org mapping

1. `GetMyCompanyProfile`
2. Start from a known `person_id`
3. `FindMatchAndEnrichPeople` with `related_people` for that person
4. Prioritize `managers` for buyers and `direct_reports` for implementers
5. `FindMatchAndEnrichPeople` with the `email` attribute for 2-3 people
6. Save to a contact list

### Job-signal outreach

1. `GetMyCompanyProfile`
2. `ListOrganizationLists`
3. `FindMatchAndEnrichJobs` scoped to a territory list and project slug
4. `FindMatchAndEnrichJobs` for the top job's `job_id` with the `description` attribute and `related_people`
5. `FindMatchAndEnrichPeople` with contact-reveal attributes on only the top few targets

### External list import

1. `GetMyCompanyProfile`
2. `FindMatchAndEnrichOrganizations`
3. `CreateOrganizationList`
4. `AddOrganizationsToList`
5. Optional selective attributes, entity metrics, or `GetIntelligenceBrief`

### Single-company deep dive

1. `GetMyCompanyProfile`
2. `FindMatchAndEnrichOrganizations`
3. `FindMatchAndEnrichPeople`
4. `FindMatchAndEnrichJobs`
5. Save targets to a contact list

## Cost management

- Free tools can be used liberally.
- Tighten organization filters before `FindMatchAndEnrichOrganizations`, then request only needed paid attributes and entity metrics.
- `GetIntelligenceBrief` is 50 credits per completed brief. Use it after narrowing to a high-priority account.
- Phone reveals in `FindMatchAndEnrichPeople` are expensive (80 credits). Prefer email-only when email is enough; keep contact reveals to the top 2-3 targets.
- Signals tools bill 1 credit per signal returned — filter tightly (list, org, technology, priority) rather than pulling an unfiltered feed.
- `RunSqlQuery` bills by response size. Always use `LIMIT` and select only the columns you need.
- On a 402 response, direct the user to purchase more credits.
- Always surface URLs returned by the tools.
