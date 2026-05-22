// warehouse-query.pq — example of hitting a Fabric warehouse with PQTest.
// Replace the server/database with your own. Register an OAuth2 credential
// before running (see set-credential.ps1).
let
    Source = Sql.Database(
        "<your-warehouse>.msit-datawarehouse.fabric.microsoft.com",
        "<your-database>"
    ),
    Table  = Source{[Schema="<schema>", Item="<table>"]}[Data],
    First5 = Table.FirstN(Table, 5)
in
    First5
