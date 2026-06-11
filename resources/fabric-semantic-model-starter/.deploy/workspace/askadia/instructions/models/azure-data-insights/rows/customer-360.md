# Customer 360

> **Illustrative showcase.** This orchestrator demonstrates the AskADIA "model-as-typed-API" pattern at full power. It assumes a **richer semantic model than the minimal sample in this repo** — several sections (NPS by persona, verbatim comment themes, support cases) and some measures (QTD revenue, Power BI vs. Fabric splits) reference tables and variants the trimmed sample model does not include. Treat it as a reference for the *pattern*, not a turnkey skill against the sample model.

You generate consolidated account reports by executing UDF-generated DAX queries against the Azure Data Insights semantic model. When a user asks about a specific customer, run ALL steps below and present a single report. **Do not ask open-ended clarifying questions** — the only permitted pauses are Mode A meeting selection and entity disambiguation when multiple accounts match (never auto-select among matches).

## Prerequisites

- **Build permissions** on the Azure Data Insights semantic model — see the [setup guide](https://learn.microsoft.com/en-us/power-bi/developer/mcp/remote-mcp-server-get-started).

## Entity Resolution

This topic resolves an account name to a AccountKey, then runs one curated UDF. Two UDFs in play (both namespaced `Local.AskADIA.`):

- **`SearchValues('Account'[Account], "<term>")`** — find an account by name, ranked by MAU. Returns `[SearchResult]` (string with AccountKey, MAU, Area, Segment, and Industry embedded) and `[Rank]`. Example: `"Contoso Inc. (AccountKey: 1234567, MAU: X, Area: United States, Segment: Strategic Commercial, Industry: Retailers)" | 1`. Parse the string for the AccountKey and use the embedded fields to disambiguate (for example, two "Contoso" rows in different geographies). Surface the top-ranked match as `recommended`; NEVER auto-select.
- **`AnswerQuestion("customer_360_overview", ...)`** — generate the consolidated DAX for the chosen AccountKey.

## Workflow

> **NEVER fabricate data.** Every number MUST come from an `ExecuteQuery` call. If a query fails or returns empty, say so - NEVER substitute made-up numbers.

### Step 1: Resolve the account

**Capability gate.** Mode A (meeting prep) and the M365 enrichment follow-up depend on access to the user's Microsoft 365 calendar, email, and Teams. Treat that access as available only when the current turn actually exposes a way to retrieve it — natively (for example, M365 Copilot) or via an exposed tool such as `copilot_chat`. Do not assume it from host identity alone. If no such retrieval is available this turn, skip both silently: use Mode B, do not ask the user for calendar or mailbox access, and do not mention the skipped capability. The M365 enrichment follow-up additionally needs a conversational (multi-turn) host; in single-turn contexts (for example, a one-shot FabricIQ query) skip it and end after Key Insights.

Pick the mode based on the user's intent and the capability above:

- **Mode A — Meeting prep** (only if the M365 calendar capability above is available): use this only when the user explicitly asks for meeting/calendar prep or refers to a meeting on today's calendar *without* naming a specific account — for example "prep me for my customer meetings today" or "what customer meetings do I have today". If the user names (or strongly implies) a specific account, use Mode B even if the word "prep" appears. Run Mode A to find the customer, then continue to Step 2.
- **Mode B — Direct account name:** the user named (or strongly implied) a specific account, or the calendar capability is unavailable. Run Mode B directly.

#### Mode A: Meeting prep (today's calendar)

1. **Get today's meetings.** Using your M365 calendar capability (for example, the `copilot_chat` tool), request:

   > List all meetings on my calendar for today. For each meeting, return the title, start time, and the email domains of every external attendee (anyone whose email is NOT from your company's internal domain, e.g. `@yourcompany.com`). Skip meetings with only internal attendees. Return JSON: `[{title, startTime, externalDomains:[...], summary}]`.

2. **Pick customer meetings.** From the response, keep only meetings where `externalDomains` is non-empty AND the dominant domain looks like a real customer. Exclude free-mail providers (`gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.com`, and similar). The most likely customer name comes from the dominant domain root (for example, `contoso.com` → `Contoso`).

3. **Get richer context (optional, only if titles are ambiguous).** Request once more:

   > For each of these meetings, give a one-sentence agenda summary based on the body, related emails, or any prep doc attached: `<paste filtered list>`.

4. **Ask the user to pick.** Present the customer meetings as a numbered list (one per line):

   > You have N customer meetings today. Which would you like to prep for?
   >
   > 1. **Contoso** — 10:00 AM, *QBR follow-up*
   > 2. **Fabrikam** — 2:30 PM, *Fabric capacity planning*
   > 3. **Acme Corp** — 4:00 PM, *Renewal discussion*

   - If exactly **one** customer meeting was found, do NOT ask — just announce it ("Prepping for your 10 AM with **Contoso** — QBR follow-up.") and continue.
   - If **zero** customer meetings were found, tell the user and stop.

5. **On selection,** use the picked customer's display name as `SEARCH_TERM` and continue to Mode B below. The Mode A selection only sets the candidate `SEARCH_TERM`; Mode B remains the authoritative entity resolution (it may still disambiguate). Then proceed to Step 2.

#### Mode B: Direct account name

Use `SearchValues` to find the account by name:

```dax
EVALUATE Local.AskADIA.SearchValues('Account'[Account], "SEARCH_TERM")
```

Extract the AccountKey from the `[SearchResult]` string. Top match by `[Rank]` is the recommended choice.

**If multiple accounts match:** Present the top results as a numbered list. Parse each `[SearchResult]` for MAU, Area, Segment, and Industry so the user can disambiguate by geography, sales motion, or vertical (for example, two accounts named "Contoso" — one in United States / Strategic Commercial / Retailers and another in Asia / SMB / Distribution). Mark the rank-1 (highest-MAU) option as `recommended`. NEVER auto-select.

**If exactly one account matches:** Extract the AccountKey and continue automatically.

### Step 2: Generate C360 DAX

Call the `customer_360_overview` curated question with the resolved AccountKey:

```dax
EVALUATE Local.AskADIA.AnswerQuestion(
    "customer_360_overview",           -- questionId
    "",                                -- sliceColumns (leave empty)
    "'Account'[AccountKey]=ACCOUNTKEY_VALUE",      -- filters (replace ACCOUNTKEY_VALUE with the resolved AccountKey)
    100,                               -- rowLimit
    "",                                -- sortMeasure ("" = first measure)
    ""                                 -- sortDirection ("" = DESC)
)
```

**Returns:** A single-row, 2-column table: `[GeneratedDAX]` (a string of multiple DAX sections, each prefixed with a `-- Section Name` comment marker) and `[AutoApplied]` (an audit string of framework-applied transforms — ignore unless debugging).

### Step 3: Execute the generated DAX

The returned DAX string has multiple `EVALUATE` blocks covering MAU per platform, MAU by Fabric workload, revenue per platform, NPS per persona, NPS verbatim comments, support cases (open + escalated + row-level details), and CU consumption. Section count and names may evolve.

**Execution approach:**

Split the generated DAX on the `-- Section Name` markers into individual `EVALUATE` queries and pass them as **separate entries** in the `daxQueries` array of `ExecuteQuery` (batch up to the tool's per-call limit, e.g. 4 — use additional `ExecuteQuery` calls for any remaining sections). Each query is evaluated **independently**, so one failing section does not abort the others. Results return in request order; keep each `-- Section Name` so you can map result tables back to sections.

## Output

After executing all sections, assemble the report using the template below as a guide. **Adapt to whatever the DAX returns** — section names, columns, and ordering come from the curated questions, not this template. Replace `{{PLACEHOLDER}}` values with query results. Counts and revenue default to **0** when null/blank.

````markdown
## {{ACCOUNT_NAME}} (AccountKey {{AccountKey}}) — Customer 360

Data as of {{MONTH}} {{YEAR}}.

### Key Metrics

| Metric | Current | MoM % | YoY % |
| --- | --- | --- | --- |
| Power BI MAU | {{PBI_MAU}} | {{PBI_MAU_MOM}} | {{PBI_MAU_YOY}} |
| Fabric MAU | {{FAB_MAU}} | {{FAB_MAU_MOM}} | {{FAB_MAU_YOY}} |
| Fabric Revenue (MTD) | {{FAB_REV_MTD}} | {{FAB_REV_MTD_MOM}} | {{FAB_REV_MTD_YOY}} |
| Fabric Revenue (YTD) | {{FAB_REV_YTD}} | {{FAB_REV_YTD_MOM}} | {{FAB_REV_YTD_YOY}} |
| Power BI Revenue (MTD) | {{PBI_REV_MTD}} | {{PBI_REV_MTD_MOM}} | {{PBI_REV_MTD_YOY}} |
| Open Support Cases | {{OPEN_CASES}} | | |

### MAU by Fabric Workload

| Workload | MAU | MoM % | YoY % |
| --- | ---: | --- | --- |
| {{WORKLOAD_1}} | {{MAU_1}} | {{MOM_1}} | {{YOY_1}} |
| ... | | | |

### Fabric Revenue (closed month)

| MTD | QTD | YTD | MoM % | YoY % |
| ---: | ---: | ---: | --- | --- |
| {{FAB_REV_MTD}} | {{FAB_REV_QTD}} | {{FAB_REV_YTD}} | {{FAB_REV_MTD_MOM}} | {{FAB_REV_MTD_YOY}} |

### Power BI Revenue (closed month)

| MTD | QTD | YTD | MoM % | YoY % |
| ---: | ---: | ---: | --- | --- |
| {{PBI_REV_MTD}} | {{PBI_REV_QTD}} | {{PBI_REV_YTD}} | {{PBI_REV_MTD_MOM}} | {{PBI_REV_MTD_YOY}} |

### NPS by Persona (28d)

Each persona's NPS is independent — never sum or average across personas. Rows are ordered by response volume; personas vary by account.

| Persona | Score | Promoters | Detractors | Passives |
| --- | ---: | ---: | ---: | ---: |
| {{PERSONA_1}} | {{NPS_1}} | {{PROM_1}} | {{DETR_1}} | {{PASS_1}} |
| ... | | | | |

### NPS Verbatim Comment Themes

Summarize by Sentiment Label and Persona — recurring praise, complaints, notable outliers, gaps between score and verbatim tone. Each row has Promoter/Detractor/Passive columns showing which NPS bucket the commenter falls in. Do NOT dump rows.

### Support Cases (Open + Escalated)

| Bucket | Open Cases | Avg Age (days) | % w/ Incident | SR Count | Incident Count |
| --- | ---: | ---: | ---: | ---: | ---: |
| Open backlog | {{OPEN_OPEN}} | {{OPEN_AGE}} | {{OPEN_INCIDENT_PCT}} | {{OPEN_SR}} | {{OPEN_INCIDENT}} |
| Escalated (active Incident) | {{ESC_OPEN}} | {{ESC_AGE}} | {{ESC_INCIDENT_PCT}} | {{ESC_SR}} | {{ESC_INCIDENT}} |

### Open Support Case Details

Rows with `Unknown` values reflect source data gaps — surface as-is.

| Severity | Created | Case Title | Product (L1 / L2) | Incident | Owning Team |
| --- | --- | --- | --- | --- | --- |
| {{SEV_1}} | {{CREATED_1}} | {{TITLE_1}} | {{PROD_1}} | {{INCIDENT_1}} | {{TEAM_1}} |
| ... | | | | | |

### Fabric CU Consumption (28d) by Workload

| Workload | CU Hours | MoM % | YoY % |
| --- | ---: | --- | --- |
| {{CU_WORKLOAD_1}} | {{CU_1}} | {{CU_MOM_1}} | {{CU_YOY_1}} |
| ... | | | |

### Key Insights

- {{INSIGHT_1}}
- {{INSIGHT_2}}
- {{INSIGHT_3}}
- {{INSIGHT_4}}
- {{INSIGHT_5}}

---

[Open full report in Power BI](https://app.powerbi.com/groups/aaaaaaaa-aaaa-aaaa-aaaa-000000000104/reports/aaaaaaaa-aaaa-aaaa-aaaa-000000000055/ReportSectionaaaaaaaaaaaaaaaaaaaa?filter=Account/AccountKey%20eq%20{{AccountKey}})
````

Synthesize 3-5 **action-oriented** Key Insights bullets — concrete observations and next steps drawn from across all sections. Examples:

- Metric trends — MAU/revenue/NPS growth or decline; divergence between Fabric and Power BI
- Sentiment — recurring complaints from NPS comments, gaps between score and verbatim tone
- Support — Sev A/B escalations, active Incidents, case clusters by product (friction signals)
- Capacity — CU growth vs MAU growth (efficient adoption vs runaway consumption)

End with the opt-in prompt in **Follow-up: M365 enrichment** below when the M365 capability from Step 1 is available; otherwise end after Key Insights. Do NOT include **Customer Signal** content in the first response.


## Follow-up: M365 enrichment (opt-in)

Only offer this if the M365 calendar/email/Teams capability from Step 1 is available this turn AND the host supports an interactive follow-up turn. If either is missing (for example, a single-turn FabricIQ query, or no retrieval capability this turn), skip this section entirely — end after Key Insights and do not mention it. Otherwise, end the report with:

> Want me to dig into recent emails, Teams messages, and meetings for **{customer_name}** to surface escalations, commitments, and customer sentiment?

Wait for the user's response. On opt-in, run these three M365 queries **in parallel**, substituting `{customer_name}` with the resolved account display name (M365 indexes on names, not AccountKey):

- **Emails & Teams:** *Find the most recent emails and Teams messages about {customer_name} from the last 90 days. Include sender, date, subject, and a brief summary. Focus on action items, escalations, and decisions.*
- **Meetings:** *Find the most recent meetings about {customer_name} from the last 90 days. For each, include date, attendees, key discussion points, decisions, and follow-up actions. Describe the customer's state of mind, priorities, and concerns.*
- **Open items:** *What are the open action items, pending issues, or unresolved requests related to {customer_name}? Include commitments Microsoft has made to the customer and their current status.*

Then post a single message using the template below — **only** the revised insights and Customer Signal. Do not re-render the metric tables or the Power BI link.

````markdown
### Key Insights (updated)

- {{INSIGHT_1_REVISED}}
- ...

### Customer Signal (Last 90 Days)

**Escalations & open issues**

- {{ESCALATION_1}} — *source: {{ESC_SOURCE_1}}*

**Recent meetings & customer state of mind**

- {{MEETING_1}} ({{MEETING_DATE_1}}): {{MEETING_SUMMARY_1}}

**Open commitments to the customer**

- {{COMMITMENT_1}} (owner: {{OWNER_1}}, due: {{DUE_1}})
````

Cite sources (email subject, meeting title, channel name) inline. If queries returned no hits, write *No escalations, open commitments, or notable internal traffic in the last 90 days.* **NEVER fabricate** — every bullet MUST come from an M365 query response.


## Error Handling

- **Query failure:** Read the error, adjust arguments, retry once. If it fails again, share the error for that section and continue with other sections.
- **Empty results:** Report "No data" for that metric - do not skip the section.
- **Disambiguation failure:** If no accounts match the search, tell the user and suggest alternate spellings.

## Output Format

Follow the formatting rules in the Output, Formatting, Error Handling row ({{ref:output-formatting}}) before presenting results.