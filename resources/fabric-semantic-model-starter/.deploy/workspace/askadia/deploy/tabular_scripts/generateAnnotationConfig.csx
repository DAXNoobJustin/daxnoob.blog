// ============================================================================
// Preprocessing: Populate _COPILOT_ANNOTATIONS_REGISTRY from shared JSON config
// ============================================================================
// Runs at deploy time via the generate_annotation_config Python op (which sets
// the ASKADIA_CONFIG_JSON env var to the shared askadia_config.json path). Reads
// the annotationRegistry section, validates its shape + semantic constraints,
// builds a DATATABLE() expression, and replaces the
// _COPILOT_ANNOTATIONS_REGISTRY partition source via TOM.
//
// SCOPE: This registry drives the DiscoverColumns Tags + (Phase 4) Behavior
// output columns only. Each row declares "if a column carries AnnotationKey,
// render RenderedValue in the Surface's output column." It does NOT drive
// _FormatAutoApplied / _FormatFactBody / _FormatTopicFactBody — those have
// pre-computed, non-generic data shapes (per-measure scalar columns in
// _COPILOT_MEASURE_COLUMNS, positional params in _FormatAutoApplied) that
// can't iterate the registry without a much larger refactor.
//
// Idempotency: compares old vs new partition expression; skips the assignment
// (and the resulting TMDL rewrite) when identical.
//
// Schema (under askadia_config.json `annotationRegistry`, PascalCase keys
// matching column names):
//   {
//     "annotationRegistry": [
//       {
//         "AnnotationKey": "Copilot_Enumerable",
//         "ObjectType": "Column",
//         "Surface": "DiscoverColumnsTags",
//         "EmitOrder": 1,
//         "RenderedValue": "searchable",
//         "Description": "..."           // comment-only; not emitted to DATATABLE
//       }
//     ]
//   }
//
// Column schema is hardcoded below (`columnNames` + `columnKinds`) and must
// stay in sync with the .tmdl skeleton at
// `.deploy/workspace/askadia/udf/common/tables/_COPILOT_ANNOTATIONS_REGISTRY.tmdl`.
// TE2's TOM exposes `DataType = Unknown` for calculated-table columns until
// the partition is materialized, so we can't read the schema from the model
// at script time. `Description` is preserved in the JSON for reviewability
// (humans skim it to understand each row) but is NOT a model column —
// listed in commentOnlyJsonKeys below so it doesn't trip the unknown-key
// validator.
//
// To add a new tag/behavior: add a JSON row + redeploy. The DiscoverColumns
// UDF iterates this registry via _GetAnnotationsForSurface — no DAX changes
// required.
// ============================================================================

using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

const string targetTableName = "_COPILOT_ANNOTATIONS_REGISTRY";

// Column manifest — single source of truth for codegen. If you add/remove a
// column, also update the shared skeleton (.deploy/workspace/askadia/
// tables/_COPILOT_ANNOTATIONS_REGISTRY.tmdl) so the column defs match.
//   Kind: "string", "integer"
//
// Why hardcoded here instead of derived from TOM (targetTable.Columns):
// calculated-table columns declared via `isNameInferred + sourceColumn:[X]`
// have DataType = Unknown at script time — the type only resolves after the
// partition is materialized. So the script can't read the schema from TOM
// and has to be told it explicitly. Drift is caught at deploy when the
// emitted DATATABLE shape doesn't match the inferred column shape on
// partition refresh.
var columnNames = new string[]
{
    "AnnotationKey",
    "ObjectType",
    "Surface",
    "EmitOrder",
    "RenderedValue",
};
var columnKinds = new string[]
{
    "string",
    "string",
    "string",
    "integer",
    "string",
};
var columnCount = columnNames.Length;

// JSON keys that humans use for documentation but the DATATABLE doesn't
// emit. Allowed in JSON, ignored by codegen + validation. Keep in sync
// with the schema docblock above.
var commentOnlyJsonKeys = new HashSet<string>(new[] { "Description" }, StringComparer.Ordinal);

// Allowed enums.
//
// Surfaces — kept tight to the two real consumers (DiscoverColumns Tags +
// DiscoverColumns Behavior). When you add a third surface, also add
// a consumer UDF that calls _GetAnnotationsForSurface(<new surface>) — empty
// surfaces accumulate as dead config otherwise.
//
// ObjectTypes — matches _INFO_ANNOTATIONS[ObjectType]. Keep tight so typos
// in JSON fail loud.
//
// Per-surface ObjectType constraints — enforced separately at validation
// time, see allowedObjectTypesPerSurface below. Prevents nonsensical rows
// like a Measure-typed row on a column-projection surface.
var allowedSurfaces = new HashSet<string>(new[]
{
    "DiscoverColumnsTags",
    "DiscoverColumnsBehavior",
}, StringComparer.Ordinal);
var allowedObjectTypes = new HashSet<string>(new[]
{
    "Column",
    "Measure",
    "Hierarchy",
    "Table",
    "Level",
}, StringComparer.Ordinal);

// Per-surface ObjectType allow-list. Mirrors the projection logic in
// Local.AskADIA._GetTaggedObjectsForSurface: only Column and Hierarchy
// rows project onto the DiscoverColumns per-column output surfaces.
// If you add a new surface or extend the helper's projection logic,
// expand this map in lockstep.
var allowedObjectTypesPerSurface = new Dictionary<string, HashSet<string>>(StringComparer.Ordinal)
{
    { "DiscoverColumnsTags",     new HashSet<string>(new[] { "Column" },              StringComparer.Ordinal) },
    { "DiscoverColumnsBehavior", new HashSet<string>(new[] { "Column", "Hierarchy" }, StringComparer.Ordinal) },
};

// Map Kind -> DAX DATATABLE type literal.
// Lambda (Func<>) instead of top-level local function — TE2's Roslyn host
// doesn't support top-level method declarations.
Func<string, string> DaxType = null;
DaxType = kind =>
{
    if (kind == "string")  return "STRING";
    if (kind == "integer") return "INTEGER";
    throw new Exception("Unknown column kind: " + kind);
};

// --- Locate JSON ------------------------------------------------------------

var jsonPath = Environment.GetEnvironmentVariable("ASKADIA_CONFIG_JSON");
if (string.IsNullOrEmpty(jsonPath))
{
    throw new Exception(
        "ASKADIA_CONFIG_JSON env var not set. " +
        "This script must be invoked via the generate_annotation_config Python op."
    );
}
if (!File.Exists(jsonPath))
{
    throw new Exception("askadia_config.json not found at: " + jsonPath);
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
try
{
    var root = JObject.Parse(raw);
    var token = root["annotationRegistry"];
    if (token == null)
    {
        throw new Exception("missing required property 'annotationRegistry'.");
    }
    if (token.Type != JTokenType.Array)
    {
        throw new Exception("'annotationRegistry' must be a JSON array, got " + token.Type + ".");
    }
    arr = (JArray)token;
}
catch (Exception ex) { throw new Exception("askadia_config.json annotationRegistry is invalid: " + ex.Message); }

// Allowed keys = TOM-derived column names + comment-only keys. Comment-only
// keys are accepted in JSON but never required and never emitted.
var allowedKeys = new HashSet<string>(columnNames, StringComparer.Ordinal);
foreach (var k in commentOnlyJsonKeys) allowedKeys.Add(k);
var seenIdentityKeys = new HashSet<string>(StringComparer.Ordinal);

// Refuse to emit an empty registry on a bootstrapped model. The framework
// requires at least the Tags rows so DiscoverColumns.Tags has something to
// render. Silently emitting a 0-row DATATABLE would also leave the
// _PLACEHOLDER stub row in the deployed model.
if (arr.Count == 0)
{
    throw new Exception(
        targetTableName + ": askadia_config.json annotationRegistry contains zero entries. " +
        "The framework requires at least the DiscoverColumnsTags rows to function."
    );
}

for (int rowIdx = 0; rowIdx < arr.Count; rowIdx++)
{
    var token = arr[rowIdx];
    if (token.Type != JTokenType.Object)
    {
        throw new Exception("askadia_config.json.annotationRegistry[" + rowIdx + "]: expected object, got " + token.Type);
    }
    var obj = (JObject)token;

    // Required keys + no unknowns
    foreach (var key in obj.Properties().Select(p => p.Name))
    {
        if (!allowedKeys.Contains(key))
        {
            throw new Exception(
                "askadia_config.json.annotationRegistry[" + rowIdx + "]: unknown key '" + key + "'. " +
                "Allowed keys: " + string.Join(", ", allowedKeys)
            );
        }
    }
    for (int ci = 0; ci < columnCount; ci++)
    {
        if (obj.Property(columnNames[ci]) == null)
        {
            throw new Exception(
                "askadia_config.json.annotationRegistry[" + rowIdx + "]: missing required key '" + columnNames[ci] + "'."
            );
        }
    }

    // Type checks
    for (int ci = 0; ci < columnCount; ci++)
    {
        var colName = columnNames[ci];
        var colKind = columnKinds[ci];
        var val = obj[colName];
        if (colKind == "integer")
        {
            if (val.Type != JTokenType.Integer)
                throw new Exception("askadia_config.json.annotationRegistry[" + rowIdx + "]." + colName + ": expected integer, got " + val.Type);
        }
        else // string
        {
            if (val.Type != JTokenType.String && val.Type != JTokenType.Null)
                throw new Exception("askadia_config.json.annotationRegistry[" + rowIdx + "]." + colName + ": expected string, got " + val.Type);
        }
    }

    // Domain rules
    var annKey       = ((string)obj["AnnotationKey"]  ?? "").Trim();
    var objType      = ((string)obj["ObjectType"]     ?? "").Trim();
    var surface      = ((string)obj["Surface"]        ?? "").Trim();
    var emitOrd      = (int)obj["EmitOrder"];
    var renderedVal  = ((string)obj["RenderedValue"]  ?? "");

    if (string.IsNullOrEmpty(annKey))
    {
        throw new Exception("askadia_config.json.annotationRegistry[" + rowIdx + "].AnnotationKey: must be non-empty.");
    }
    if (!annKey.StartsWith("Copilot_", StringComparison.Ordinal))
    {
        throw new Exception(
            "askadia_config.json.annotationRegistry[" + rowIdx + "].AnnotationKey '" + annKey +
            "': must start with 'Copilot_' (matches generateInfoAnnotations.csx scope)."
        );
    }
    if (!allowedObjectTypes.Contains(objType))
    {
        throw new Exception(
            "askadia_config.json.annotationRegistry[" + rowIdx + "].ObjectType '" + objType +
            "': must be one of " + string.Join(", ", allowedObjectTypes) + "."
        );
    }
    if (!allowedSurfaces.Contains(surface))
    {
        throw new Exception(
            "askadia_config.json.annotationRegistry[" + rowIdx + "].Surface '" + surface +
            "': must be one of " + string.Join(", ", allowedSurfaces) + "."
        );
    }
    HashSet<string> allowedForSurface;
    if (allowedObjectTypesPerSurface.TryGetValue(surface, out allowedForSurface) && !allowedForSurface.Contains(objType))
    {
        throw new Exception(
            "askadia_config.json.annotationRegistry[" + rowIdx + "]: ObjectType '" + objType +
            "' not allowed for Surface '" + surface +
            "'. Allowed: " + string.Join(", ", allowedForSurface) +
            ". Extend allowedObjectTypesPerSurface (and the helper's projection logic) if you need more."
        );
    }
    if (emitOrd < 1)
    {
        throw new Exception("askadia_config.json.annotationRegistry[" + rowIdx + "].EmitOrder: must be >= 1, got " + emitOrd);
    }
    if (string.IsNullOrEmpty(renderedVal))
    {
        throw new Exception(
            "askadia_config.json.annotationRegistry[" + rowIdx + "].RenderedValue: must be non-empty. " +
            "Empty values would produce render artifacts like 'searchable, , sliceable' in DiscoverColumns output."
        );
    }

    var identityKey = annKey + "::" + objType + "::" + surface;
    if (!seenIdentityKeys.Add(identityKey))
    {
        throw new Exception(
            "askadia_config.json.annotationRegistry[" + rowIdx + "]: duplicate (AnnotationKey, ObjectType, Surface) = (" +
            annKey + ", " + objType + ", " + surface + ")."
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
    // descriptions shouldn't contain them, and they break single-line
    // DATATABLE row formatting.
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
sb.Append("\n\t\t\t\tDATATABLE(\n");
for (int i = 0; i < columnCount; i++)
{
    sb.Append("\t\t\t\t    \"").Append(columnNames[i]).Append("\", ").Append(DaxType(columnKinds[i]));
    sb.Append(",\n");
}
sb.Append("\t\t\t\t    {\n");

for (int rowIdx = 0; rowIdx < arr.Count; rowIdx++)
{
    var obj = (JObject)arr[rowIdx];
    sb.Append("\t\t\t\t        {");
    for (int i = 0; i < columnCount; i++)
    {
        var colKind = columnKinds[i];
        var val = obj[columnNames[i]];
        if (i > 0) sb.Append(", ");

        if (colKind == "integer")
        {
            sb.Append((int)val);
        }
        else
        {
            var rawStr = val.Type == JTokenType.Null ? "" : (string)val;
            // Trim parity with validation: AnnotationKey/ObjectType/Surface are
            // .Trim()'d at validation (see ~241-243). Without matching .Trim()
            // here, a value with trailing whitespace would pass validation
            // (trimmed) but emit untrimmed — producing a row whose key column
            // doesn't equal the value the validator approved.
            var colName = columnNames[i];
            var s = (colName == "AnnotationKey" || colName == "ObjectType" || colName == "Surface")
                ? rawStr.Trim()
                : rawStr;
            sb.Append("\"").Append(EscapeDax(s)).Append("\"");
        }
    }
    sb.Append("}");
    if (rowIdx < arr.Count - 1) sb.Append(",");
    sb.Append("\n");
}

sb.Append("\t\t\t\t    }\n");
sb.Append("\t\t\t\t)");

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
