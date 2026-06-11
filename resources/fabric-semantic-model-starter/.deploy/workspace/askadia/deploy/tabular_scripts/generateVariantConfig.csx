// ============================================================================
// Preprocessing: Populate _COPILOT_VARIANT_CONFIG from shared AskADIA config
// ============================================================================
// Runs at deploy time via the generate_variant_config Python op (which sets
// ASKADIA_CONFIG_JSON to .deploy/workspace/askadia/udf/common/askadia_config.json).
// Reads the measureVariants section, validates it, builds a DATATABLE()
// expression, and replaces the _COPILOT_VARIANT_CONFIG partition source.
// ============================================================================

using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

const string targetTableName = "_COPILOT_VARIANT_CONFIG";

var columnNames = new string[]
{
    "Suffix",
    "EmitOrder",
};
var columnKinds = new string[]
{
    "string",
    "integer",
};
var columnCount = columnNames.Length;

Func<string, string> DaxType = null;
DaxType = kind =>
{
    if (kind == "string") return "STRING";
    if (kind == "boolean") return "BOOLEAN";
    if (kind == "integer") return "INTEGER";
    throw new Exception("Unknown column kind: " + kind);
};

var jsonPath = Environment.GetEnvironmentVariable("ASKADIA_CONFIG_JSON");
if (string.IsNullOrEmpty(jsonPath))
{
    throw new Exception(
        "ASKADIA_CONFIG_JSON env var not set. " +
        "This script must be invoked via the generate_variant_config Python op."
    );
}
if (!File.Exists(jsonPath))
{
    throw new Exception("askadia_config.json not found at: " + jsonPath);
}

var targetTable = Model.Tables.FirstOrDefault(t => t.Name == targetTableName);
if (targetTable == null)
{
    Info(targetTableName + ": table not found in model — skipping codegen.");
    return;
}
if (targetTable.Partitions.Count == 0)
{
    throw new Exception(targetTableName + ": no partitions found.");
}

var raw = File.ReadAllText(jsonPath);
JArray arr;
try
{
    var root = JObject.Parse(raw);
    var token = root["measureVariants"];
    if (token == null)
    {
        throw new Exception("missing required property 'measureVariants'.");
    }
    if (token.Type != JTokenType.Array)
    {
        throw new Exception("'measureVariants' must be a JSON array, got " + token.Type + ".");
    }
    arr = (JArray)token;
}
catch (Exception ex) { throw new Exception("askadia_config.json measureVariants is invalid: " + ex.Message); }

var allowedKeys = new HashSet<string>(columnNames, StringComparer.Ordinal);
var seenSuffixes = new HashSet<string>(StringComparer.Ordinal);
var seenOrders = new HashSet<int>();

if (arr.Count == 0)
{
    throw new Exception(targetTableName + ": askadia_config.json measureVariants contains zero entries.");
}

for (int rowIdx = 0; rowIdx < arr.Count; rowIdx++)
{
    var token = arr[rowIdx];
    if (token.Type != JTokenType.Object)
    {
        throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "]: expected object, got " + token.Type);
    }
    var obj = (JObject)token;

    foreach (var key in obj.Properties().Select(p => p.Name))
    {
        if (!allowedKeys.Contains(key))
        {
            throw new Exception(
                "askadia_config.json.measureVariants[" + rowIdx + "]: unknown key '" + key + "'. " +
                "Allowed keys: " + string.Join(", ", allowedKeys)
            );
        }
    }
    for (int ci = 0; ci < columnCount; ci++)
    {
        if (obj.Property(columnNames[ci]) == null)
        {
            throw new Exception(
                "askadia_config.json.measureVariants[" + rowIdx + "]: missing required key '" + columnNames[ci] + "'."
            );
        }
    }

    for (int ci = 0; ci < columnCount; ci++)
    {
        var colName = columnNames[ci];
        var colKind = columnKinds[ci];
        var val = obj[colName];
        if (colKind == "boolean")
        {
            if (val.Type != JTokenType.Boolean)
                throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "]." + colName + ": expected boolean, got " + val.Type);
        }
        else if (colKind == "integer")
        {
            if (val.Type != JTokenType.Integer)
                throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "]." + colName + ": expected integer, got " + val.Type);
        }
        else
        {
            if (val.Type != JTokenType.String && val.Type != JTokenType.Null)
                throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "]." + colName + ": expected string, got " + val.Type);
        }
    }

    var suffix = ((string)obj["Suffix"] ?? "").Trim();
    var emitOrder = (int)obj["EmitOrder"];
    if (suffix.Length == 0)
    {
        throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "].Suffix: must be non-empty.");
    }
    if (suffix.IndexOf("|") >= 0)
    {
        throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "].Suffix: must not contain '|'.");
    }
    if (emitOrder < 1)
    {
        throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "].EmitOrder: must be >= 1.");
    }
    if (!seenSuffixes.Add(suffix))
    {
        throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "]: duplicate Suffix '" + suffix + "'.");
    }
    if (!seenOrders.Add(emitOrder))
    {
        throw new Exception("askadia_config.json.measureVariants[" + rowIdx + "]: duplicate EmitOrder " + emitOrder + ".");
    }
}

Func<string, string> EscapeDax = null;
EscapeDax = s =>
{
    if (s == null) return "";
    foreach (var c in s)
    {
        if (c == '\r' || c == '\n' || c == '\t')
            throw new Exception("Control characters are not allowed in _COPILOT_VARIANT_CONFIG values.");
    }
    return "\"" + s.Replace("\"", "\"\"") + "\"";
};

var rows = new List<string>();
for (int rowIdx = 0; rowIdx < arr.Count; rowIdx++)
{
    var obj = (JObject)arr[rowIdx];
    var vals = new List<string>();
    for (int ci = 0; ci < columnCount; ci++)
    {
        var colName = columnNames[ci];
        var colKind = columnKinds[ci];
        var val = obj[colName];
        if (colKind == "boolean")
            vals.Add(((bool)val) ? "TRUE" : "FALSE");
        else if (colKind == "integer")
            vals.Add(((int)val).ToString());
        else
            vals.Add(EscapeDax(((string)val ?? "").Trim()));
    }
    rows.Add("        {" + string.Join(", ", vals) + "}");
}

var sb = new StringBuilder();
sb.AppendLine("DATATABLE(");
for (int ci = 0; ci < columnCount; ci++)
{
    sb.AppendLine("    \"" + columnNames[ci] + "\", " + DaxType(columnKinds[ci]) + ",");
}
sb.AppendLine("    {");
sb.AppendLine(string.Join(",\n", rows));
sb.AppendLine("    }");
sb.Append(")");

var newExpression = sb.ToString();
var partition = targetTable.Partitions.First();
var oldExpression = partition.Expression ?? "";
if (oldExpression.Trim() == newExpression.Trim())
{
    Info(targetTableName + ": partition already up to date (" + rows.Count + " rows).");
}
else
{
    partition.Expression = newExpression;
    Info(targetTableName + ": " + rows.Count + " rows generated.");
}
