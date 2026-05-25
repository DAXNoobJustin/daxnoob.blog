// bad-syntax.pq — intentional syntax error: trailing commas in Sql.Database args.
// PQTest returns Status=Failed with exact line/column.
let
    Source = Sql.Database("<your-warehouse>.msit-datawarehouse.fabric.microsoft.com", "<your-database>",,,)
in
    Source
