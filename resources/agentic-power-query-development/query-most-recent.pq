// query-most-recent.pq — example test for one of the queries defined in _project.pq.
//
// The // #include line below is replaced with the contents of _project.pq
// before PQTest sees the file, giving this expression access to SourceUrl,
// TargetState, fnAddDayBucket, RawIssues, and IssuesTyped.
//
// Run with:  .\Invoke-PQTestComposed.ps1 -QueryFile .\query-most-recent.pq
//
// Tip: pass -ShowComposed to write the fully unfolded file next to this one
// as query-most-recent.composed.pq, so you can see exactly what PQTest ran.

let
    // #include _project.pq

    MostRecent5 = Table.FirstN(
        Table.Sort(IssuesTyped, {{"CreatedAt", Order.Descending}}),
        5
    )
in
    MostRecent5
