# Azure Data Partner & Community — Model Reference

> Read the matching topic row first — topic rows own measure-level routing rules. This row covers cross-topic model context (key dimensions, hierarchies, account & partner disambiguation). UDF signatures live in the UDF Reference row ({{ref:udf-reference}}).

## Key Dimensions

### Calendar

`'Calendar'` carries filterable columns. `[RelativeMonthNumber]` is filter-only — pass it via `filters=`, NEVER `sliceColumns=`. Slicing by `[Fiscal Month]` or `[Calendar Date]` triggers a trailing-13-month auto-window (current month plus the 12 prior; `0` = current, `-12` = 12 months ago). Year-grain and quarter-grain slices do NOT trigger it. Any explicit filter on any `'Calendar'` column — user-passed, measure default, or hardcoded — suppresses the auto-injection.

| Column | Grain | Value format | Example (single `filters` entry) |
| - | - | - | - |
| `'Calendar'[RelativeMonthNumber]` | Month | Integer, `0` = current month | `'Calendar'[RelativeMonthNumber]=-5;-4;-3;-2;-1;0` or range `'Calendar'[RelativeMonthNumber]>=-5` |
| `'Calendar'[Fiscal Year]` | Year | `FYxx` | `'Calendar'[Fiscal Year]=FY25` or `FY24;FY25` |
| `'Calendar'[Fiscal Quarter]` | Quarter | `FYxx-Qn` (dash) | `'Calendar'[Fiscal Quarter]=FY25-Q3` |
| `'Calendar'[Fiscal Month]` | Month | `"Month, YYYY"` (comma + space) | `'Calendar'[Fiscal Month]=March, 2025` |
| `'Calendar'[Calendar Date]` | Day | ISO date | `'Calendar'[Calendar Date]=2025-03-15` or range `>=2025-01-01..<=2025-03-31` |

### Account (AccountKey)

ALWAYS use `'Account'[AccountKey]` with the digits-only AccountKey value (no inner quotes around the number) in filter strings — for example `filters="'Account'[AccountKey]=1234567"`. When a user names a company, use `SearchValues('Account'[Account], "name")` to resolve to AccountKey — NEVER hard-code account keys from memory.

`SearchValues('Account'[Account], "<term>")` returns `[SearchResult]` + `[Rank]`, where `[SearchResult]` carries the account name plus its **AccountKey** (paired via `Copilot_PairWith`) — quote the AccountKey directly instead of issuing a follow-up query. When multiple candidates surface, present the account names + account keys so the user can pick unambiguously.

> **"Microsoft" is a customer account, not a corporate rollup.** The dataset measures per-customer telemetry — resolve via `SearchValues` like any other customer.

When you need a filter beyond `[AccountKey]`, run `DiscoverColumns("Account")` first.

### Partner

Most partner-scoped queries filter `'Partner'[Partner Id]` (Int64; **with a space** — NOT `[PartnerId]`, that column does not exist). One topic — Specialization ({{ref:specialization}}) — filters by `'Partner'[Partner Name]` instead because a single Partner maps to multiple `DIM_PartnerGlobalId` values; that topic row documents the divergence.

When a user names a partner, use `SearchValues('Partner'[Partner Name], "<term>")` to resolve — NEVER hard-code Partner Ids from memory.

`SearchValues('Partner'[Partner Name], "<term>")` returns `[SearchResult]` + `[Rank]`. The `[SearchResult]` string has the partner name plus **Partner Id, Influenced Revenue MTD, Membership** (level + status together, for example `Specialization Partner Active`) — quote those fields directly from the result instead of issuing a follow-up query. When multiple candidates surface, present membership context alongside the name + id so the user can pick unambiguously. The ranker is scoped to active, non-internal, non-test partners — search misses are typically inactive or internal records that won't surface.

For partner attributes beyond `[Partner Id]` / `[Partner Name]` / `[Membership Level]` / `[Membership Status]`, run `DiscoverColumns("Partner")` first. **Partner has no geographic columns** — for partner-by-region queries, filter `'Geography'` (joined via the topic's fact table).

### Product Master

`[Product]` is the canonical column. Resolve user terms via `SearchValues('Product Master'[Product], "<term>")`.

### Geography

Hierarchy: **Big Area → Area → Region → Sub Region → Subsidiary**. No `[Country]` column exists — when the user asks about a country, filter on `'Geography'[Subsidiary]`. Use `SearchValues` on the right column to discover exact values.

### Hierarchies

**Product Master** — Product Group → Product Mid Group → Product.

## Gotchas

_None at the model level._
