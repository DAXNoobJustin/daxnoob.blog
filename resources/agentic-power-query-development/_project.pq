// _project.pq — shared definitions for the example "project".
//
// This is how you'd capture the contents of a real PBIX or dataflow:
// each parameter, function, and named query in your project becomes one
// `name = expression,` binding here. M's `let` is order-independent, so
// bindings can reference each other in any order (UDFs can call queries,
// queries can call UDFs, etc).
//
// This file is a fragment — it is NOT a valid standalone M expression.
// It only makes sense when spliced into a `let` block via a `// #include`
// in another .pq file. See query-most-recent.pq for how that looks.

// ----- Parameters -----
SourceUrl    = "https://api.github.com/repos/microsoft/TypeScript/issues",
TargetState  = "open",

// ----- Functions -----
fnAddDayBucket = (issueDate as datetime) as text =>
    let
        daysOld = Duration.Days(DateTime.LocalNow() - issueDate)
    in
        if      daysOld <= 7   then "0-7 days"
        else if daysOld <= 30  then "8-30 days"
        else if daysOld <= 90  then "31-90 days"
        else                        "90+ days",

// ----- Queries -----
RawIssues =
    let
        Source = Json.Document(
            Web.Contents(SourceUrl, [Query = [state = TargetState, per_page = "50"]])
        )
    in
        Table.FromList(Source, Splitter.SplitByNothing(), null, null, ExtraValues.Error),

IssuesTyped =
    let
        Expanded = Table.ExpandRecordColumn(
            RawIssues, "Column1",
            {"number", "title", "state", "created_at", "user"},
            {"Number", "Title", "State", "CreatedAt", "User"}
        ),
        TypedDates = Table.TransformColumns(
            Expanded,
            {{"CreatedAt", each DateTime.FromText(_), type datetime}}
        ),
        WithBucket = Table.AddColumn(
            TypedDates, "DayBucket",
            each fnAddDayBucket([CreatedAt]),
            type text
        )
    in
        WithBucket,
