# Partner Specialization

Partner specialization program status — which partners hold which specializations, which are one criterion away from earning a specialization.

> **Illustrative showcase.** This topic demonstrates the AskADIA "model-as-typed-API" pattern against a **richer semantic model than the minimal sample in this repo** — the `'Partner Specialization Program Requirement'` and `'Partner Certification'` tables and their measures (e.g. `[Partner Specialization PartnerGlobal Count]`, `[Partner Specialization PartnerGlobal Count - One Req Remaining]`, `[Active Partner Certifications]`) are not part of the trimmed sample Partner & Community model. Treat it as a reference for the *pattern*, not a turnkey skill against the sample model.

## Domain Notes

- **Source table**: `'Partner Specialization Program Requirement'`.
- **Default period**: point-in-time (specialization status is a snapshot, not a time series).
- **Notable measures**: `[Partner Specialization PartnerGlobal Count - One Req Remaining]` (counts qualifying partners per criterion context — used by the "one req remaining" curated question). `[Active Partner Certifications]` lives on the `'Partner Certification'` fact (also tagged `specialization`) — note its body sums fundamentals + new role-based + expiring + YTD renewed, mixing point-in-time and YTD time windows; flag the methodology when the user asks for it. `DiscoverMeasures("specialization" | "Partner Certification")` lists the rest.

## Resolution

- **Specialization**: names (for example, "AI Platform on Microsoft Azure", "Analytics on Microsoft Azure") are values of `'Partner Specialization Program Requirement'[Partner Specialization]`. Resolve via `SearchValues('Partner Specialization Program Requirement'[Partner Specialization], "<term>")` — NEVER hard-code from memory.
- **Partner**: resolve via `SearchValues('Partner'[Partner Name], "<term>")`. **Filter by Name, NOT Id** — see Gotchas below.

## Gotchas

> **CRITICAL — Partner-by-Name (NOT Id):** Specialization queries filter `'Partner'[Partner Name]`, NOT `'Partner'[Partner Id]`. A single Partner maps to multiple `DIM_PartnerGlobalId` values; Name-level scope surfaces them all together. For a specific Partner Global ID, filter `'Partner Specialization Program Requirement'[DIM_PartnerGlobalId]` directly.

- **Specialization-status query has no measure in the SELECT.** The "specialization status for partner" curated question returns row-level criteria records (every program × every criterion detail). Read the rows directly — don't add a measure expecting a count. To count programs, post-process the rows (DISTINCT over `[Partner Specialization]`).
- **"One req remaining" wraps an `ISBLANK` filter.** The "partners one req remaining for specialization" question wraps `[Partner Specialization PartnerGlobal Count - One Req Remaining]` in `NOT ISBLANK(...)` so only qualifying partners surface. Preserve the wrapper on any custom variant.
- **Use the `[Partner Specialization PartnerGlobal Count - One Req Remaining]` measure — don't try to filter by `[OneReqRemainingFlag]` directly.** The flag column isn't framework-exposed; the measure body encapsulates the flag-based filter and pairs with a `NOT ISBLANK` wrapper at runtime so only qualifying partners surface.
