// ============================================================================
// Preprocessing: Generate _INFO_HIERARCHIES DATATABLE from model hierarchies
// ============================================================================
// Runs at deploy time via run_model_script. Walks every hierarchy/level in the
// model and writes a DATATABLE expression into _INFO_HIERARCHIES that maps
// columns to their position in any user hierarchy.
//
// Columns: [TableName], [HierarchyName], [LevelOrdinal], [LevelName], [ColumnName]
//
// Used by GenerateQuery/SearchHierarchy UDFs to:
//   1. Detect that a sliced column is part of a hierarchy
//   2. Find its parent levels (lower Ordinal) for auto-injection
//   3. Drive progressive search across related columns
//
// Reason for script: DAX's INFO.HIERARCHIES() / INFO.LEVELS() cannot be used
// in calculated tables (schema is not inferrable — returns 0 columns). Only
// INFO.VIEW.TABLES/COLUMNS/MEASURES/RELATIONSHIPS support calc-table use.
// ============================================================================

var targetTableName = "_INFO_HIERARCHIES";
var rows = new List<string>();

foreach (var table in Model.Tables)
{
    var tn = (table.Name ?? "").Replace("\"", "\"\"");

    foreach (var hier in table.Hierarchies)
    {
        var hn = (hier.Name ?? "").Replace("\"", "\"\"");

        foreach (var lvl in hier.Levels)
        {
            var ln = (lvl.Name ?? "").Replace("\"", "\"\"");
            var cn = (lvl.Column != null ? lvl.Column.Name ?? "" : "").Replace("\"", "\"\"");
            var ord = lvl.Ordinal;

            rows.Add("        {\"" + tn + "\", \"" + hn + "\", " + ord + ", \"" + ln + "\", \"" + cn + "\"}");
        }
    }
}

// Fallback placeholder row if the model has no hierarchies (avoids empty DATATABLE syntax error)
if (rows.Count == 0)
{
    rows.Add("        {\"_PLACEHOLDER\", \"_PLACEHOLDER\", 0, \"_PLACEHOLDER\", \"_PLACEHOLDER\"}");
}

var dax = "DATATABLE(\n" +
    "    \"TableName\", STRING,\n" +
    "    \"HierarchyName\", STRING,\n" +
    "    \"LevelOrdinal\", INTEGER,\n" +
    "    \"LevelName\", STRING,\n" +
    "    \"ColumnName\", STRING,\n" +
    "    {\n" +
    string.Join(",\n", rows) +
    "\n    }\n" +
    ")";

var targetTable = Model.Tables.FirstOrDefault(t => t.Name == targetTableName);
if (targetTable == null)
{
    Info("_INFO_HIERARCHIES: table not found in model, skipping.");
}
else
{
    var partition = targetTable.Partitions.First();
    partition.Expression = dax;
    Info("_INFO_HIERARCHIES: " + rows.Count + " level rows generated.");
}
