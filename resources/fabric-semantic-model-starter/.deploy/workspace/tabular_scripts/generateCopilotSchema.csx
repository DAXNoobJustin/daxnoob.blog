// Generate Copilot schema.json from model annotations
using Newtonsoft.Json.Linq;

var schema = new JObject();
schema["$schema"] = "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/copilot/schema/1.0.0/schema.json";

var tablesArray = new JArray();

foreach (var table in Model.Tables)
{
    var tableObj = new JObject();
    tableObj["name"] = table.Name;
    
    // Columns
    var columnsArray = new JArray();
    foreach (var column in table.Columns)
    {
        var columnObj = new JObject();
        columnObj["name"] = column.Name;
        
        var vis = column.GetAnnotation("Copilot_Visibility");
        columnObj["visibility"] = (vis == "Visible") ? "Visible" : "Hidden";
        
        var synsStr = column.GetAnnotation("Copilot_Synonyms");
        var synsArray = new JArray();
        if (!string.IsNullOrWhiteSpace(synsStr))
        {
            foreach (var syn in synsStr.Split('|'))
            {
                var trimmed = syn.Trim();
                if (!string.IsNullOrEmpty(trimmed))
                    synsArray.Add(trimmed);
            }
        }
        columnObj["synonyms"] = synsArray;
        
        columnsArray.Add(columnObj);
    }
    tableObj["columns"] = columnsArray;
    
    // Measures
    var measuresArray = new JArray();
    foreach (var measure in table.Measures)
    {
        var measureObj = new JObject();
        measureObj["name"] = measure.Name;
        
        var vis = measure.GetAnnotation("Copilot_Visibility");
        measureObj["visibility"] = (vis == "Visible") ? "Visible" : "Hidden";
        
        var synsStr = measure.GetAnnotation("Copilot_Synonyms");
        var synsArray = new JArray();
        if (!string.IsNullOrWhiteSpace(synsStr))
        {
            foreach (var syn in synsStr.Split('|'))
            {
                var trimmed = syn.Trim();
                if (!string.IsNullOrEmpty(trimmed))
                    synsArray.Add(trimmed);
            }
        }
        measureObj["synonyms"] = synsArray;
        
        measuresArray.Add(measureObj);
    }
    tableObj["measures"] = measuresArray;
    
    // Hierarchies
    var hierarchiesArray = new JArray();
    foreach (var hierarchy in table.Hierarchies)
    {
        var hierarchyObj = new JObject();
        hierarchyObj["name"] = hierarchy.Name;
        
        var vis = hierarchy.GetAnnotation("Copilot_Visibility");
        hierarchyObj["visibility"] = (vis == "Visible") ? "Visible" : "Hidden";
        
        var synsStr = hierarchy.GetAnnotation("Copilot_Synonyms");
        var synsArray = new JArray();
        if (!string.IsNullOrWhiteSpace(synsStr))
        {
            foreach (var syn in synsStr.Split('|'))
            {
                var trimmed = syn.Trim();
                if (!string.IsNullOrEmpty(trimmed))
                    synsArray.Add(trimmed);
            }
        }
        hierarchyObj["synonyms"] = synsArray;
        
        hierarchiesArray.Add(hierarchyObj);
    }
    tableObj["hierarchies"] = hierarchiesArray;
    
    // Table-level visibility: derived from children.
    // A table is Visible if it has an explicit Copilot_Visibility=Visible annotation,
    // OR if any of its columns, measures, or hierarchies are Visible.
    var tableVis = table.GetAnnotation("Copilot_Visibility");
    bool tableIsVisible = (tableVis == "Visible");

    if (!tableIsVisible)
    {
        tableIsVisible = columnsArray.Any(c => c["visibility"].ToString() == "Visible") ||
                         measuresArray.Any(m => m["visibility"].ToString() == "Visible") ||
                         hierarchiesArray.Any(h => h["visibility"].ToString() == "Visible");
    }

    tableObj["visibility"] = tableIsVisible ? "Visible" : "Hidden";
    
    var tableSynsStr = table.GetAnnotation("Copilot_Synonyms");
    var tableSynsArray = new JArray();
    if (!string.IsNullOrWhiteSpace(tableSynsStr))
    {
        foreach (var syn in tableSynsStr.Split('|'))
        {
            var trimmed = syn.Trim();
            if (!string.IsNullOrEmpty(trimmed))
                tableSynsArray.Add(trimmed);
        }
    }
    tableObj["synonyms"] = tableSynsArray;
    
    tablesArray.Add(tableObj);
}

schema["tables"] = tablesArray;

Output(schema.ToString(Newtonsoft.Json.Formatting.Indented));
