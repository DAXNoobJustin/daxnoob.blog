// ============================================================================
// Preprocessing: Populate _COPILOT_QUESTIONS rows from per-model JSON registry
// ============================================================================
// Runs at deploy time via the generate_copilot_questions Python op (which sets
// the COPILOT_QUESTIONS_JSON env var to the per-model copilot_questions.json
// path). Reads the JSON, validates its shape, builds a DATATABLE() expression,
// and replaces the _COPILOT_QUESTIONS partition source via TOM.
//
// The _COPILOT_QUESTIONS table itself (column defs + FactName calc col +
// DATATABLE shell with a _PLACEHOLDER row) is provided by the shared askadia
// scaffold (.deploy/workspace/askadia/udf/common/tables/_COPILOT_QUESTIONS.tmdl)
// and synced into the model dir by merge_shared_scaffold. This script only
// replaces the *partition expression* — never touches column defs.
//
// Idempotency: compares old vs new partition expression; skips the assignment
// (and the resulting TMDL rewrite) when identical.
//
// JSON schema (flat array of objects, PascalCase keys matching column names):
//   [
//     {
//       "QuestionId": "usage_mau",
//       "Question": "What's MAU?",
//       "Description": "Monthly Active Users (28-day rolling).",
//       "Measures": "[MAU]",
//       "HardcodedGroupBy": "'Product Master'[Product]",
//       "DefaultFilters": "'Product Master'[Product]=Fabric Core",
//       "HardcodedFilters": "",
//       "HardcodedNotInFilters": "",
//       "RequiredFilters": "",
//       "DaxWrapper": "",
//       "IsOrchestrator": false,
//       "SectionIndex": 1,
//       "SectionLabel": ""
//     }
//   ]
//
// Topic is NOT a JSON field — it is derived at runtime from the question's
// FactName lookup against the fact table's Copilot_Topic annotation. See
// _COPILOT_QUESTIONS.tmdl `column Topic` calc col.
// ============================================================================

using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

const string targetTableName = "_COPILOT_QUESTIONS";

// Column manifest — single source of truth for codegen. If you add/remove a
// column, also update the shared skeleton (.deploy/workspace/askadia/
// tables/_COPILOT_QUESTIONS.tmdl) so the column defs match.
//   Kind: "string", "boolean", "integer"
// Two parallel string arrays (instead of an anonymous-typed array) because
// TE2's Roslyn-scripting host doesn't support anonymous types in arrays.
//
// Why hardcoded here instead of derived from TOM (targetTable.Columns):
// calculated-table columns declared via `isNameInferred + sourceColumn:[X]`
// have DataType = Unknown at script time — the type only resolves after the
// partition is materialized. So the script can't read the schema from TOM
// and has to be told it explicitly. Drift between this list and the .tmdl
// skeleton is caught at deploy by the post-write partition assertion (any
// missing/extra column trips the DATATABLE columns-mismatch check).
var columnNames = new string[]
{
    "QuestionId",
    "Question",
    "Description",
    "Measures",
    "HardcodedGroupBy",
    "DefaultFilters",
    "HardcodedFilters",
    "HardcodedNotInFilters",
    "RequiredFilters",
    "DaxWrapper",
    "IsOrchestrator",
    "SectionIndex",
    "SectionLabel",
};
var columnKinds = new string[]
{
    "string",
    "string",
    "string",
    "string",
    "string",
    "string",
    "string",
    "string",
    "string",
    "string",
    "boolean",
    "integer",
    "string",
};
var columnCount = columnNames.Length;

// Map Kind -> DAX DATATABLE type literal.
// Lambda (Func<>) instead of top-level local function — TE2's Roslyn host
// doesn't support top-level method declarations.
Func<string, string> DaxType = null;
DaxType = kind =>
{
    if (kind == "string")  return "STRING";
    if (kind == "boolean") return "BOOLEAN";
    if (kind == "integer") return "INTEGER";
    throw new Exception("Unknown column kind: " + kind);
};

// --- Locate JSON ------------------------------------------------------------

var jsonPath = Environment.GetEnvironmentVariable("COPILOT_QUESTIONS_JSON");
if (string.IsNullOrEmpty(jsonPath))
{
    throw new Exception(
        "COPILOT_QUESTIONS_JSON env var not set. " +
        "This script must be invoked via the generate_copilot_questions Python op."
    );
}
if (!File.Exists(jsonPath))
{
    throw new Exception("copilot_questions.json not found at: " + jsonPath);
}

// --- Locate target table ----------------------------------------------------

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

// --- Parse + validate JSON --------------------------------------------------

var raw = File.ReadAllText(jsonPath);
JArray arr;
try { arr = JArray.Parse(raw); }
catch (Exception ex) { throw new Exception("copilot_questions.json is not a valid JSON array: " + ex.Message); }

var allowedKeys = new HashSet<string>(columnNames);
var seenSectionKeys = new HashSet<string>(StringComparer.Ordinal);

if (arr.Count == 0)
{
    Info(targetTableName + ": JSON has zero questions — leaving partition unchanged (placeholder remains).");
    return;
}

for (int rowIdx = 0; rowIdx < arr.Count; rowIdx++)
{
    var token = arr[rowIdx];
    if (token.Type != JTokenType.Object)
    {
        throw new Exception("copilot_questions.json[" + rowIdx + "]: expected object, got " + token.Type);
    }
    var obj = (JObject)token;

    // Required keys + no unknowns
    foreach (var key in obj.Properties().Select(p => p.Name))
    {
        if (!allowedKeys.Contains(key))
        {
            throw new Exception(
                "copilot_questions.json[" + rowIdx + "]: unknown key '" + key + "'. " +
                "Allowed keys: " + string.Join(", ", allowedKeys)
            );
        }
    }
    for (int ci = 0; ci < columnCount; ci++)
    {
        if (obj.Property(columnNames[ci]) == null)
        {
            throw new Exception(
                "copilot_questions.json[" + rowIdx + "]: missing required key '" + columnNames[ci] + "'."
            );
        }
    }

    // Type checks
    for (int ci = 0; ci < columnCount; ci++)
    {
        var colName = columnNames[ci];
        var colKind = columnKinds[ci];
        var val = obj[colName];
        if (colKind == "boolean")
        {
            if (val.Type != JTokenType.Boolean)
                throw new Exception("copilot_questions.json[" + rowIdx + "]." + colName + ": expected boolean, got " + val.Type);
        }
        else if (colKind == "integer")
        {
            if (val.Type != JTokenType.Integer)
                throw new Exception("copilot_questions.json[" + rowIdx + "]." + colName + ": expected integer, got " + val.Type);
        }
        else // string
        {
            if (val.Type != JTokenType.String && val.Type != JTokenType.Null)
                throw new Exception("copilot_questions.json[" + rowIdx + "]." + colName + ": expected string, got " + val.Type);
        }
    }

    // Domain rules
    var sectionIdx = (int)obj["SectionIndex"];
    if (sectionIdx < 1)
    {
        throw new Exception("copilot_questions.json[" + rowIdx + "].SectionIndex: must be >= 1, got " + sectionIdx);
    }
    var qid = (string)obj["QuestionId"] ?? "";
    if (string.IsNullOrEmpty(qid))
    {
        throw new Exception("copilot_questions.json[" + rowIdx + "].QuestionId: must be non-empty.");
    }
    var sectionKey = qid + "::" + sectionIdx;
    if (!seenSectionKeys.Add(sectionKey))
    {
        throw new Exception(
            "copilot_questions.json[" + rowIdx + "]: duplicate (QuestionId, SectionIndex) = (" +
            qid + ", " + sectionIdx + ")."
        );
    }
}

// --- Build DATATABLE expression --------------------------------------------

// Lambda (Func<>) instead of top-level local function — TE2's Roslyn host
// doesn't support top-level method declarations.
Func<string, string> EscapeDax = null;
EscapeDax = s =>
{
    if (s == null) return "";
    // Reject control chars (CR/LF/tab) — DAX strings handle them but our
    // pipe/semicolon-encoded fields shouldn't contain them, and they break
    // single-line DATATABLE row formatting.
    foreach (var c in s)
    {
        if (c == '\r' || c == '\n' || c == '\t')
        {
            throw new Exception(
                "Field value contains a control character (CR/LF/TAB). " +
                "Use spaces instead — they break DATATABLE row formatting."
            );
        }
    }
    // DAX double-quote escape
    return s.Replace("\"", "\"\"");
};

var sb = new StringBuilder();
sb.Append("\n\t\t\t\t\tDATATABLE(\n");
for (int i = 0; i < columnCount; i++)
{
    sb.Append("\t\t\t\t\t    \"").Append(columnNames[i]).Append("\", ").Append(DaxType(columnKinds[i]));
    sb.Append(",\n"); // trailing comma always (next is `{` or another column)
}
sb.Append("\t\t\t\t\t    {\n");

for (int rowIdx = 0; rowIdx < arr.Count; rowIdx++)
{
    var obj = (JObject)arr[rowIdx];
    sb.Append("\t\t\t\t\t        {");
    for (int i = 0; i < columnCount; i++)
    {
        var colKind = columnKinds[i];
        var val = obj[columnNames[i]];
        if (i > 0) sb.Append(", ");

        if (colKind == "boolean")
        {
            sb.Append((bool)val ? "TRUE" : "FALSE");
        }
        else if (colKind == "integer")
        {
            sb.Append((int)val);
        }
        else
        {
            // string (allow null -> empty)
            var s = val.Type == JTokenType.Null ? "" : (string)val;
            sb.Append("\"").Append(EscapeDax(s)).Append("\"");
        }
    }
    sb.Append("}");
    if (rowIdx < arr.Count - 1) sb.Append(",");
    sb.Append("\n");
}

sb.Append("\t\t\t\t\t    }\n");
sb.Append("\t\t\t\t\t)");

var newExpression = sb.ToString();

// --- Idempotency: write only if changed ------------------------------------

var partition = targetTable.Partitions.First();
var oldExpression = partition.Expression ?? "";
if (oldExpression == newExpression)
{
    Info(targetTableName + ": partition expression unchanged (" + arr.Count + " rows) — skipping write.");
    return;
}

partition.Expression = newExpression;
Info(targetTableName + ": " + arr.Count + " rows written to partition expression.");
