// bad-runtime.pq — intentional runtime error: table doesn't exist.
// PQTest returns Status=Failed with the failing key and the available table shape,
// so an LLM can pick the right name on retry.
let
    Source = Sql.Database(
        "<your-warehouse>.msit-datawarehouse.fabric.microsoft.com",
        "<your-database>"
    ),
    NoSuch = Source{[Schema="<schema>", Item="DOES_NOT_EXIST"]}[Data]
in
    NoSuch
