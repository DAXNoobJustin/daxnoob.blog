// ============================================================================
// Preprocessing: Generate _INFO_ANNOTATIONS DATATABLE from model annotations
// ============================================================================
// Runs at deploy time via run_model_script. Reads ALL Copilot_* annotations
// from the model (auto-discovered — no hardcoded list) and writes a DATATABLE
// expression into _INFO_ANNOTATIONS.
// Columns: [TableName], [ObjectName], [ObjectType], [AnnotationName], [AnnotationValue]
// Joinable to _INFO_COLUMNS, _INFO_MEASURES, _INFO_TABLES via name columns.
// Adding a new Copilot_* annotation type requires NO script change — it is
// picked up automatically as soon as any object carries it.
// ============================================================================

var targetTableName = "_INFO_ANNOTATIONS";
const string annotationPrefix = "Copilot_";
var rows = new List<string>();

foreach (var table in Model.Tables)
{
    var tn = (table.Name ?? "").Replace("\"", "\"\"");

    // Table-level annotations
    foreach (var annName in table.GetAnnotations())
    {
        if (!annName.StartsWith(annotationPrefix, StringComparison.Ordinal)) continue;
        var val = table.GetAnnotation(annName);
        if (val == null) continue;
        rows.Add("        {\"" + tn + "\", \"" + tn + "\", \"Table\", \"" + annName.Replace("\"", "\"\"") + "\", \"" + val.Replace("\"", "\"\"") + "\"}");
    }

    // Column annotations
    foreach (var col in table.Columns)
    {
        var on = (col.Name ?? "").Replace("\"", "\"\"");
        foreach (var annName in col.GetAnnotations())
        {
            if (!annName.StartsWith(annotationPrefix, StringComparison.Ordinal)) continue;
            var val = col.GetAnnotation(annName);
            if (val == null) continue;
            rows.Add("        {\"" + tn + "\", \"" + on + "\", \"Column\", \"" + annName.Replace("\"", "\"\"") + "\", \"" + val.Replace("\"", "\"\"") + "\"}");
        }
    }

    // Measure annotations
    foreach (var meas in table.Measures)
    {
        var on = (meas.Name ?? "").Replace("\"", "\"\"");
        foreach (var annName in meas.GetAnnotations())
        {
            if (!annName.StartsWith(annotationPrefix, StringComparison.Ordinal)) continue;
            var val = meas.GetAnnotation(annName);
            if (val == null) continue;
            rows.Add("        {\"" + tn + "\", \"" + on + "\", \"Measure\", \"" + annName.Replace("\"", "\"\"") + "\", \"" + val.Replace("\"", "\"\"") + "\"}");
        }
    }

    // Hierarchy (and hierarchy level) annotations
    foreach (var hier in table.Hierarchies)
    {
        var on = (hier.Name ?? "").Replace("\"", "\"\"");
        foreach (var annName in hier.GetAnnotations())
        {
            if (!annName.StartsWith(annotationPrefix, StringComparison.Ordinal)) continue;
            var val = hier.GetAnnotation(annName);
            if (val == null) continue;
            rows.Add("        {\"" + tn + "\", \"" + on + "\", \"Hierarchy\", \"" + annName.Replace("\"", "\"\"") + "\", \"" + val.Replace("\"", "\"\"") + "\"}");
        }

        foreach (var lvl in hier.Levels)
        {
            var lvlName = (hier.Name + "." + lvl.Name).Replace("\"", "\"\"");
            foreach (var annName in lvl.GetAnnotations())
            {
                if (!annName.StartsWith(annotationPrefix, StringComparison.Ordinal)) continue;
                var val = lvl.GetAnnotation(annName);
                if (val == null) continue;
                rows.Add("        {\"" + tn + "\", \"" + lvlName + "\", \"Level\", \"" + annName.Replace("\"", "\"\"") + "\", \"" + val.Replace("\"", "\"\"") + "\"}");
            }
        }
    }
}

// Update the target table partition (skip silently if table doesn't exist in this model)
var targetTable = Model.Tables.FirstOrDefault(t => t.Name == targetTableName);
if (targetTable == null)
{
    Info("_INFO_ANNOTATIONS: table not found in model, skipping.");
}
else
{
    // Fail loud on zero annotations. _INFO_ANNOTATIONS feeds dispatch
    // decisions in SearchValues, ladder/ranker discovery in
    // _SearchAllValues, and the entire AskADIA codegen pipeline. A model
    // with zero Copilot_* annotations cannot meaningfully use the
    // framework — silently emitting a 0-row DATATABLE would also break
    // the codegen scripts downstream (they regex over annotation values).
    // If you hit this, follow the bootstrap checklist in
    // .deploy/workspace/askadia/README.md.
    if (rows.Count == 0)
    {
        Error(
            "_INFO_ANNOTATIONS: zero Copilot_* annotations found on model '" +
            (Model.Name ?? "(unnamed)") +
            "'. The AskADIA UDF framework requires at least one Copilot_* annotation. " +
            "See .deploy/workspace/askadia/README.md → Bootstrapping a new model."
        );
        throw new InvalidOperationException(
            "generateInfoAnnotations: model has zero Copilot_* annotations — refusing to emit empty DATATABLE."
        );
    }

    // Build DATATABLE expression
    var dax = "DATATABLE(\n" +
        "    \"TableName\", STRING,\n" +
        "    \"ObjectName\", STRING,\n" +
        "    \"ObjectType\", STRING,\n" +
        "    \"AnnotationName\", STRING,\n" +
        "    \"AnnotationValue\", STRING,\n" +
        "    {\n" +
        string.Join(",\n", rows) +
        "\n    }\n" +
        ")";

    var partition = targetTable.Partitions.First();
    partition.Expression = dax;
    Info("_INFO_ANNOTATIONS: " + rows.Count + " annotation rows generated.");
}
