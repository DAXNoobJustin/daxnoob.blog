// ============================================================================
// Preprocessing: Generate _SearchAllValues + _SearchAllLadderColumns bodies
// ============================================================================
// Runs at deploy time via run_model_script. Reads the model's annotations
// and codegens the bodies of these two per-model search helper UDFs:
//
//   * Local.AskADIA._SearchAllValues
//       Scalar string returning ranker dispatcher. Returns a CONCATENATEX of
//       [Rank]<TAB>[SearchResult] rows joined by UNICHAR(10), for the single
//       Copilot_SearchRanker column whose fully-qualified name (e.g.
//       "'Account'[Account]") matches the targetCol argument. Per-ranker
//       branches are guarded by scalar IF so only the matching ranker
//       materializes — non-matching branches return BLANK without evaluating
//       their CONCATENATEX subtree (DAX scalar-IF short-circuit; table-IF
//       would eagerly evaluate every branch). The outer SearchValues
//       dispatcher PATHITEM-splits the result back into rows. Ladder rows
//       are handled separately by _ConcatLadder in SearchValues — they do
//       NOT pass through _SearchAllValues.
//
//   * Local.AskADIA._SearchAllLadderColumns
//       Returns (Ladder, Position, TableName, ColumnName, MatchedValue) for
//       any value in any ladder column that contains searchTerm. Per-column
//       VALUES + CONTAINSSTRING — dictionary-only, never touches base data.
//       Used by SearchHierarchy and by SearchValues._ConcatLadder directly.
//
//       If a level column has a Copilot_ValueSynonyms annotation
//       ("canonical1=syn1;syn2|canonical2=syn3"), the codegen also emits a
//       synonym pass for that column by calling the shared helper UDF
//       Local.AskADIA._GetColumnSynonymMatches(col, searchTerm) and projecting
//       its (MatchedValue) row set into the ladder schema. The synonym data
//       itself lives in the _COPILOT_VALUE_SYNONYMS table (populated below) —
//       no per-column DATATABLE inlining. The per-ladder UNION is always
//       wrapped in DISTINCT to collapse overlap between literal and synonym
//       passes (e.g. searchTerm "DE" matches both literal "DE and DS" AND
//       synonym "Data Engineering" → "DE and DS").
//
//   * _COPILOT_VALUE_SYNONYMS (table partition expression)
//       (TableName, ColumnName, Canonical, Synonym). One row per (canonical,
//       synonym) tuple parsed from any column annotated with
//       Copilot_ValueSynonyms. Read by _GetColumnSynonymMatches at runtime —
//       so synonym matching logic is centralized in that one helper UDF and
//       reused across the ladder branch (_SearchAllLadderColumns) and the
//       generic branch (SearchValues._ConcatGeneric).
//
// Discovery rules:
//   * Ranker entry: any column with annotation Copilot_SearchRanker = "<UDF FQN>".
//     The referenced UDF must exist and is invoked directly inside an IF branch
//     gated by `targetCol = "<colFQN>"`. Per the AskADIA contract the UDF returns
//     TABLE(SearchResult: STRING, Rank: INTEGER) only.
//   * Ladder entry: any hierarchy with annotation Copilot_SearchLadder = "true".
//     ALL such hierarchies are emitted in _SearchAllLadderColumns (which is
//     the single source of truth) so the dispatcher's "is supported" check
//     stays in lock-step with what the helper actually returns.
//   * Synonym entry: any column with annotation Copilot_ValueSynonyms (format
//     above). Honored by ladder branch + generic SearchValues branch via
//     _GetColumnSynonymMatches. NOT supported on ranker columns — annotating a
//     ranker column with Copilot_ValueSynonyms fails the deploy loud (the
//     ranker already does fuzzy/multi-column scoring; layering value-aliasing
//     on top is ambiguous and not implemented). Malformed pairs (missing '='
//     or empty canonical) also fail the deploy loud.
//
// In addition to the body, this script also overwrites the function
// description on each helper so that downstream stale-doc drift is
// impossible. Both helpers are SHARED stub declarations (see
// .deploy/workspace/askadia/udf/common/functions.tmdl) that
// merge_shared_scaffold copies into the per-model functions.tmdl before
// this script runs; this script then fills the per-model body from the
// per-model annotations.
//
// Output is sorted (table, then name) so diffs across deploys are stable.
// Authored against TE2's CSX engine (C# 6 — no local functions / no dynamic).
// ============================================================================

string RANKER_ANNOTATION = "Copilot_SearchRanker";
string LADDER_ANNOTATION = "Copilot_SearchLadder";
string LADDER_VALUE = "true";
string SYN_ANNOTATION = "Copilot_ValueSynonyms";
string SAV_FQN = "Local.AskADIA._SearchAllValues";
string SALC_FQN = "Local.AskADIA._SearchAllLadderColumns";
string SYN_TABLE = "_COPILOT_VALUE_SYNONYMS";

// ----- Emission helpers (Func<> instead of local functions for TE2 compat) -----
Func<string, string> DaxStr = null;
DaxStr = delegate(string s) {
    if (s == null) s = "";
    return "\"" + s.Replace("\"", "\"\"") + "\"";
};

Func<string, string> SafeVar = null;
SafeVar = delegate(string s) {
    var sb = new System.Text.StringBuilder();
    if (s == null) s = "";
    foreach (char ch in s)
    {
        if (char.IsLetterOrDigit(ch) || ch == '_') sb.Append(ch);
    }
    var v = sb.ToString();
    if (v.Length == 0) v = "X";
    if (char.IsDigit(v[0])) v = "_" + v;
    return v;
};

Func<string, string> TableRef = null;
TableRef = delegate(string t) {
    return "'" + (t == null ? "" : t.Replace("'", "''")) + "'";
};

Func<string, string, string> ColRef = null;
ColRef = delegate(string t, string c) {
    // Fail loud on null/empty column name. Otherwise we'd emit invalid DAX
    // ('table'[]) that surfaces only as a downstream parse error in the
    // generated UDF body. Aligns with the f3 fail-loud philosophy.
    if (string.IsNullOrWhiteSpace(c))
    {
        throw new InvalidOperationException(
            "generateSearchHelpers: attempted to generate DAX column reference with null/empty column name " +
            "for table '" + (t ?? "") + "'. Fix the model metadata/annotations so the referenced column has a name."
        );
    }
    // Escape ']' in column names per DAX bracketed-identifier rules: ] -> ]].
    return TableRef(t) + "[" + c.Replace("]", "]]") + "]";
};

// ----- Discover ranker columns -----
var rankerTable = new List<string>();
var rankerColumn = new List<string>();
var rankerFqn = new List<string>();

foreach (var t in Model.Tables)
{
    foreach (var c in t.Columns)
    {
        var fqn = c.GetAnnotation(RANKER_ANNOTATION);
        if (string.IsNullOrWhiteSpace(fqn)) continue;
        rankerTable.Add(t.Name);
        rankerColumn.Add(c.Name);
        rankerFqn.Add(fqn.Trim());
    }
}

var rankerCount = rankerTable.Count;
var rankerOrder = new int[rankerCount];
for (int i = 0; i < rankerCount; i++) rankerOrder[i] = i;
Array.Sort(rankerOrder, delegate(int a, int b) {
    int x = string.CompareOrdinal(rankerTable[a], rankerTable[b]);
    return x != 0 ? x : string.CompareOrdinal(rankerColumn[a], rankerColumn[b]);
});

// ----- Discover ladder hierarchies (and their levels) -----
// Parallel arrays per ladder: ladderTable[idx]/ladderHierarchy[idx] identify the
// ladder; ladderLevel*[idx][k] are the k-th level's metadata. We track which
// level columns have a Copilot_ValueSynonyms annotation in ladderLevelHasSyn so
// the codegen emits a synonym pass for those (the actual synonym data lives in
// _COPILOT_VALUE_SYNONYMS — see the per-column collection below).
var ladderTable = new List<string>();
var ladderHierarchy = new List<string>();
var ladderLevelOrdinals = new List<List<int>>();
var ladderLevelNames = new List<List<string>>();
var ladderLevelColumns = new List<List<string>>();
var ladderLevelHasSyn = new List<List<bool>>();

// Per-column synonym collection (across the whole model, not just ladder
// levels). Drives both the ladder synonym pass emission and the
// _COPILOT_VALUE_SYNONYMS partition rewrite. Keyed by table|column —
// also used by the ranker-column guard below.
var synColTable = new List<string>();
var synColColumn = new List<string>();
var synColCanonicals = new List<List<string>>();  // parallel: per-column list of canonicals
var synColSynonyms = new List<List<string>>();    // parallel: per-column list of synonyms (same length)
var synColKeys = new HashSet<string>();           // table|column lookup

foreach (var t in Model.Tables)
{
    foreach (var c in t.Columns)
    {
        var ann = c.GetAnnotation(SYN_ANNOTATION);
        if (string.IsNullOrWhiteSpace(ann)) continue;

        // Format: "canonical1=syn1;syn2;syn3|canonical2=syn4;syn5"
        // Fail loud on malformed pairs (no '=', extra '=', empty canonical,
        // empty synonym list) so a typo surfaces at deploy, not as a confusing
        // missing-result at query time. Aligns with the f3/ColRef fail-loud
        // philosophy elsewhere in this file.
        var cans = new List<string>();
        var syns = new List<string>();
        foreach (var pair in ann.Split('|'))
        {
            var p = pair.Trim();
            if (p.Length == 0) continue;
            var eq = p.IndexOf('=');
            if (eq < 0)
            {
                throw new InvalidOperationException(
                    "generateSearchHelpers: Copilot_ValueSynonyms on '" + t.Name + "'[" + c.Name +
                    "] is malformed (no '=' in pair): \"" + p + "\". Expected format: " +
                    "\"canonical1=synonym1;synonym2|canonical2=synonym3\"."
                );
            }
            var canonical = p.Substring(0, eq).Trim();
            var synList = p.Substring(eq + 1).Trim();
            if (synList.IndexOf('=') >= 0)
            {
                throw new InvalidOperationException(
                    "generateSearchHelpers: Copilot_ValueSynonyms on '" + t.Name + "'[" + c.Name +
                    "] has more than one '=' in pair: \"" + p + "\". Format does not support '=' " +
                    "inside synonyms or canonicals."
                );
            }
            if (canonical.Length == 0)
            {
                throw new InvalidOperationException(
                    "generateSearchHelpers: Copilot_ValueSynonyms on '" + t.Name + "'[" + c.Name +
                    "] has empty canonical in pair: \"" + p + "\"."
                );
            }
            var addedForThisPair = 0;
            foreach (var s in synList.Split(';'))
            {
                var st = s.Trim();
                if (st.Length == 0) continue;
                cans.Add(canonical);
                syns.Add(st);
                addedForThisPair++;
            }
            if (addedForThisPair == 0)
            {
                throw new InvalidOperationException(
                    "generateSearchHelpers: Copilot_ValueSynonyms on '" + t.Name + "'[" + c.Name +
                    "] has empty synonym list for canonical '" + canonical + "' in pair: \"" + p +
                    "\". Provide at least one synonym after the '='."
                );
            }
        }
        if (cans.Count == 0) continue;
        synColTable.Add(t.Name);
        synColColumn.Add(c.Name);
        synColCanonicals.Add(cans);
        synColSynonyms.Add(syns);
        synColKeys.Add(t.Name + "|" + c.Name);
    }
}

foreach (var t in Model.Tables)
{
    foreach (var h in t.Hierarchies)
    {
        var v = h.GetAnnotation(LADDER_ANNOTATION);
        if (v == null || v != LADDER_VALUE) continue;

        // Snapshot levels into an indexable list
        var levelOrdinalsRaw = new List<int>();
        var levelNamesRaw = new List<string>();
        var levelColsRaw = new List<string>();
        var levelHasSynRaw = new List<bool>();
        foreach (var lvl in h.Levels)
        {
            var colName = lvl.Column != null ? (lvl.Column.Name ?? "") : "";
            if (colName.Length == 0) continue;
            levelOrdinalsRaw.Add(lvl.Ordinal);
            levelNamesRaw.Add(lvl.Name ?? "");
            levelColsRaw.Add(colName);
            levelHasSynRaw.Add(synColKeys.Contains(t.Name + "|" + colName));
        }
        if (levelOrdinalsRaw.Count == 0) continue;

        // Sort by ordinal asc
        var lo = new int[levelOrdinalsRaw.Count];
        for (int i = 0; i < lo.Length; i++) lo[i] = i;
        Array.Sort(lo, delegate(int a, int b) {
            return levelOrdinalsRaw[a].CompareTo(levelOrdinalsRaw[b]);
        });

        var ords = new List<int>();
        var lnames = new List<string>();
        var lcols = new List<string>();
        var lhasSyn = new List<bool>();
        for (int i = 0; i < lo.Length; i++)
        {
            ords.Add(levelOrdinalsRaw[lo[i]]);
            lnames.Add(levelNamesRaw[lo[i]]);
            lcols.Add(levelColsRaw[lo[i]]);
            lhasSyn.Add(levelHasSynRaw[lo[i]]);
        }

        ladderTable.Add(t.Name);
        ladderHierarchy.Add(h.Name ?? "");
        ladderLevelOrdinals.Add(ords);
        ladderLevelNames.Add(lnames);
        ladderLevelColumns.Add(lcols);
        ladderLevelHasSyn.Add(lhasSyn);
    }
}

var ladderCount = ladderTable.Count;
var ladderOrder = new int[ladderCount];
for (int i = 0; i < ladderCount; i++) ladderOrder[i] = i;
Array.Sort(ladderOrder, delegate(int a, int b) {
    int x = string.CompareOrdinal(ladderTable[a], ladderTable[b]);
    return x != 0 ? x : string.CompareOrdinal(ladderHierarchy[a], ladderHierarchy[b]);
});

// ----- Validate ranker UDFs exist before regenerating anything -----
var udfNames = new HashSet<string>();
foreach (var f in Model.Functions) udfNames.Add(f.Name);

var missingMsgs = new List<string>();
for (int i = 0; i < rankerCount; i++)
{
    if (!udfNames.Contains(rankerFqn[i]))
    {
        missingMsgs.Add("'" + rankerTable[i] + "'[" + rankerColumn[i] + "] -> " + rankerFqn[i]);
    }
}
if (missingMsgs.Count > 0)
{
    throw new Exception("Copilot_SearchRanker references UDFs that don't exist in the model:\n  - " + string.Join("\n  - ", missingMsgs.ToArray()));
}

// ----- Validate Copilot_ValueSynonyms is NOT set on ranker columns -----
// Ranker columns (Copilot_SearchRanker) are deliberately excluded: the ranker
// already does fuzzy/multi-column scoring with rich enrichment in its returned
// SearchResult string (e.g. "Contoso Inc. (AccountKey: 1234567, MAU: 1234, ...)"). Layering
// value-aliasing on top would either lose that enrichment (synonym-pass result
// would be just the canonical with no fields) or require per-ranker enrichment
// plumbing — unnecessary for this case (ranker columns are typically
// proper nouns / IDs, not aliased values). Fail loud at deploy so the
// authoring intent surfaces clearly. Ladder + generic SearchValues branches
// honor Copilot_ValueSynonyms uniformly via _GetColumnSynonymMatches.
var rankerColKeys = new HashSet<string>();
for (int i = 0; i < rankerCount; i++)
{
    rankerColKeys.Add(rankerTable[i] + "|" + rankerColumn[i]);
}
var rankerSynonymCols = new List<string>();
for (int i = 0; i < synColTable.Count; i++)
{
    var key = synColTable[i] + "|" + synColColumn[i];
    if (rankerColKeys.Contains(key))
    {
        rankerSynonymCols.Add("'" + synColTable[i] + "'[" + synColColumn[i] + "]");
    }
}
if (rankerSynonymCols.Count > 0)
{
    throw new Exception(
        "Copilot_ValueSynonyms is not supported on columns that also have Copilot_SearchRanker. " +
        "Ranker columns get rich enrichment from their per-model ranker UDF; layering value-" +
        "aliasing on top would either lose that enrichment or require per-ranker plumbing. " +
        "Either drop the synonym annotation on these columns, or — if you really need synonym " +
        "resolution there — extend the ranker UDF itself to consult _COPILOT_VALUE_SYNONYMS. " +
        "Offending columns:\n  - " +
        string.Join("\n  - ", rankerSynonymCols.ToArray())
    );
}

// ----- Build _SearchAllValues body -----
// Scalar-string returning dispatcher: emits CONCATENATEX of [Rank]<FS>[SearchResult]
// rows joined by RS, gated per-ranker by scalar IF so DAX scalar-IF short-circuit
// keeps non-matching ranker branches from evaluating their CONCATENATEX subtree.
// Caller SearchValues PATHITEM-splits the result back into rows. This is the only
// proven way to avoid eager table-IF eval — see SearchValues body for the parallel
// pattern at the outer dispatcher layer.
var sav = new System.Text.StringBuilder();
sav.AppendLine("\t\t(searchTerm: SCALAR STRING VAL, targetCol: SCALAR STRING VAL) =>");
sav.AppendLine("\t\t// BEGIN GENERATED — DO NOT EDIT (regenerated by generateSearchHelpers.csx)");

var savRefs = new List<string>();

if (rankerCount > 0)
{
    sav.AppendLine("\t\tVAR _RS = UNICHAR(10)");
    sav.AppendLine("\t\tVAR _FS = UNICHAR(9)");
    sav.AppendLine("\t\tVAR _PE = UNICHAR(57344)");
}

for (int idx = 0; idx < rankerCount; idx++)
{
    int i = rankerOrder[idx];
    var tbl = rankerTable[i];
    var col = rankerColumn[i];
    var fqn = rankerFqn[i];
    var concatName = "_" + SafeVar(tbl) + "_" + SafeVar(col) + "_Concat";
    var colRef = ColRef(tbl, col);
    sav.AppendLine("\t\tVAR " + concatName + " =");
    sav.AppendLine("\t\t    IF(targetCol = " + DaxStr(colRef) + ",");
    sav.AppendLine("\t\t        CONCATENATEX(");
    sav.AppendLine("\t\t            " + fqn + "(searchTerm),");
    sav.AppendLine("\t\t            [Rank] & _FS & SUBSTITUTE(SUBSTITUTE([SearchResult], _RS, \" \"), \"|\", _PE),");
    sav.AppendLine("\t\t            _RS");
    sav.AppendLine("\t\t        )");
    sav.AppendLine("\t\t    )");
    savRefs.Add(concatName);
}

if (savRefs.Count == 0)
{
    sav.AppendLine("\t\t\"\"");
    sav.AppendLine("\t\t// END GENERATED");
}
else
{
    sav.AppendLine("\t\t// END GENERATED");
    if (savRefs.Count == 1)
    {
        sav.AppendLine("\t\tRETURN COALESCE(" + savRefs[0] + ", \"\")");
    }
    else
    {
        sav.AppendLine("\t\tRETURN COALESCE(" + string.Join(", ", savRefs.ToArray()) + ", \"\")");
    }
}

// ----- Build _SearchAllLadderColumns body -----
var salc = new System.Text.StringBuilder();
salc.AppendLine("\t\t(searchTerm: SCALAR STRING VAL) =>");
salc.AppendLine("\t\t// BEGIN GENERATED — DO NOT EDIT (regenerated by generateSearchHelpers.csx)");

var salcRefs = new List<string>();

for (int idx = 0; idx < ladderCount; idx++)
{
    int i = ladderOrder[idx];
    var tbl = ladderTable[i];
    var hier = ladderHierarchy[i];
    var ords = ladderLevelOrdinals[i];
    var lnames = ladderLevelNames[i];
    var lcols = ladderLevelColumns[i];
    var lhasSyn = ladderLevelHasSyn[i];

    // Include hierarchy name + sorted loop index in rowsName for defense-in-depth.
    // The ASKADIA_SEARCHLADDER_MULTIPLE_PER_TABLE BPA rule already prevents two
    // Copilot_SearchLadder=true hierarchies on the same table, but that rule is
    // advisory (not pipeline-blocking), so we make the codegen self-defending
    // against accidental duplicates.
    //
    // SafeVar strips non-alphanumerics so distinct hierarchy names could still
    // collapse to the same identifier (e.g., "A-B" vs "AB", or names that fully
    // strip to empty -> "X"). Suffixing with the sorted loop idx guarantees
    // unique DAX VAR names within the emitted body. idx is stable across runs
    // (sorted by table-then-hierarchy) so this does not introduce diff churn.
    var rowsName = "_" + SafeVar(tbl) + "_" + SafeVar(hier) + "_" + idx + "_LadderColMatches";

    var perLevel = new List<string>();
    for (int k = 0; k < lcols.Count; k++)
    {
        var col = ColRef(tbl, lcols[k]);
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("\t\t        SELECTCOLUMNS(");
        sb.AppendLine("\t\t            FILTER(VALUES(" + col + "), CONTAINSSTRING(" + col + ", searchTerm)),");
        sb.AppendLine("\t\t            " + DaxStr("Ladder") + ", " + DaxStr(hier) + ", " + DaxStr("Position") + ", " + ords[k] + ",");
        sb.AppendLine("\t\t            " + DaxStr("TableName") + ", " + DaxStr(tbl) + ", " + DaxStr("ColumnName") + ", " + DaxStr(lcols[k]) + ",");
        sb.AppendLine("\t\t            " + DaxStr("MatchedValue") + ", " + col + " & \"\"");
        sb.Append("\t\t        )");
        perLevel.Add(sb.ToString());

        // Synonym pass: when the level column has a Copilot_ValueSynonyms
        // annotation, append a second SELECTCOLUMNS contributor that delegates
        // to the shared helper UDF. The UDF reads _COPILOT_VALUE_SYNONYMS and
        // applies the canonical-existence gate, so this codegen no longer
        // inlines per-column DATATABLE / FILTER / CONTAINSROW boilerplate. The
        // outer DISTINCT (always emitted, see below) collapses overlap with
        // the literal pass.
        if (lhasSyn[k])
        {
            var sb2 = new System.Text.StringBuilder();
            sb2.AppendLine("\t\t        SELECTCOLUMNS(");
            sb2.AppendLine("\t\t            Local.AskADIA._GetColumnSynonymMatches(" + col + ", searchTerm),");
            sb2.AppendLine("\t\t            " + DaxStr("Ladder") + ", " + DaxStr(hier) + ", " + DaxStr("Position") + ", " + ords[k] + ",");
            sb2.AppendLine("\t\t            " + DaxStr("TableName") + ", " + DaxStr(tbl) + ", " + DaxStr("ColumnName") + ", " + DaxStr(lcols[k]) + ",");
            sb2.AppendLine("\t\t            " + DaxStr("MatchedValue") + ", [MatchedValue]");
            sb2.Append("\t\t        )");
            perLevel.Add(sb2.ToString());
        }
    }

    salc.AppendLine("\t\tVAR " + rowsName + " =");
    if (perLevel.Count == 1)
    {
        // Single contributor (one level, no synonyms) — no UNION/DISTINCT needed.
        salc.AppendLine(perLevel[0]);
    }
    else
    {
        // DISTINCT collapses literal+synonym overlap (e.g. searchTerm "DE"
        // matches both literal "DE and DS" AND synonym "Data Engineering" →
        // "DE and DS"). Always emitted when there are 2+ contributors —
        // negligible cost on dictionary-shaped row sets, and uniform body
        // shape simplifies codegen (no _HasAnySyns tracking needed).
        salc.AppendLine("\t\t    DISTINCT(");
        salc.AppendLine("\t\t        UNION(");
        salc.AppendLine(string.Join(",\n", perLevel.ToArray()));
        salc.AppendLine("\t\t        )");
        salc.AppendLine("\t\t    )");
    }
    salcRefs.Add(rowsName);
}

// Empty-stub fallback: when no Copilot_SearchLadder hierarchies exist, emit a
// 0-row VAR with the right column shape and treat it like any other ladder
// contributor. This collapses the count==0 case into the standard 1-VAR RETURN
// path below, keeping the rendered body shape uniform (VAR ... RETURN <expr>)
// across all models. Critical: a bare "RETURN <expr>" with no preceding VAR
// is INVALID DAX UDF syntax — DO NOT hoist the SELECTCOLUMNS into a bare RETURN.
if (salcRefs.Count == 0)
{
    salc.AppendLine("\t\tVAR _Empty =");
    salc.AppendLine("\t\t    SELECTCOLUMNS(");
    salc.AppendLine("\t\t        FILTER(ROW(\"_\", 1), FALSE()),");
    salc.AppendLine("\t\t        \"Ladder\", \"\", \"Position\", 0, \"TableName\", \"\", \"ColumnName\", \"\", \"MatchedValue\", \"\"");
    salc.AppendLine("\t\t    )");
    salcRefs.Add("_Empty");
}

salc.AppendLine("\t\t// END GENERATED");

if (salcRefs.Count == 1)
{
    salc.AppendLine("\t\tRETURN " + salcRefs[0]);
}
else
{
    salc.AppendLine("\t\tRETURN UNION(" + string.Join(", ", salcRefs.ToArray()) + ")");
}

// ----- Apply to model -----
var savBody = sav.ToString().TrimEnd();
var salcBody = salc.ToString().TrimEnd();

// Function descriptions (replace per-deploy so they never go stale).
var savDescription = "INTERNAL per-model ranker dispatcher. Returns a CONCATENATEX'd scalar " +
    "string of [Rank]<TAB>[SearchResult] rows joined by UNICHAR(10), for the single " +
    "Copilot_SearchRanker column whose fully-qualified name (e.g. \"'Account'[Account]\") " +
    "matches targetCol. Per-ranker branches are guarded by scalar IF so only the matching " +
    "ranker materializes — non-matching branches return BLANK without evaluating their " +
    "CONCATENATEX subtree. Caller SearchValues splits the result back into rows via PATHITEM " +
    "on UNICHAR(10). Body regenerated by .deploy/workspace/askadia/deploy/tabular_scripts/generateSearchHelpers.csx " +
    "— DO NOT hand-edit between BEGIN/END GENERATED markers.";
var salcDescription = "INTERNAL per-model search helper. Returns (Ladder, Position, TableName, " +
    "ColumnName, MatchedValue) for any value in any annotated ladder column that contains " +
    "searchTerm. Per-column VALUES + CONTAINSSTRING — dictionary-only, never touches base " +
    "data. Columns with a Copilot_ValueSynonyms annotation also contribute a synonym pass: " +
    "delegates to Local.AskADIA._GetColumnSynonymMatches (which reads _COPILOT_VALUE_SYNONYMS) " +
    "and projects MatchedValue into the ladder schema. Used by SearchHierarchy. Body " +
    "regenerated by .deploy/workspace/askadia/deploy/tabular_scripts/generateSearchHelpers.csx — DO NOT " +
    "hand-edit between BEGIN/END GENERATED markers.";

// ----- Build _COPILOT_VALUE_SYNONYMS partition expression -----
// One row per (canonical, synonym) tuple parsed from any column with a
// Copilot_ValueSynonyms annotation. Sorted (table, column, canonical, synonym)
// for stable diffs across deploys. Read by _GetColumnSynonymMatches at runtime
// — single source of truth for synonym matching across ladder + generic
// branches of SearchValues. Empty-stub fallback when the model has no synonym
// annotations: emits a placeholder row matching the shape shipped in
// askadia/udf/common/tables/_COPILOT_VALUE_SYNONYMS.tmdl, which the canonical-
// existence gate in _GetColumnSynonymMatches treats as inert.
var synAllT = new List<string>();
var synAllC = new List<string>();
var synAllK = new List<string>();
var synAllS = new List<string>();
for (int i = 0; i < synColTable.Count; i++)
{
    var tbl = synColTable[i];
    var col = synColColumn[i];
    var cans = synColCanonicals[i];
    var syns = synColSynonyms[i];
    for (int j = 0; j < cans.Count; j++)
    {
        synAllT.Add(tbl);
        synAllC.Add(col);
        synAllK.Add(cans[j]);
        synAllS.Add(syns[j]);
    }
}
var synOrder = new int[synAllT.Count];
for (int i = 0; i < synOrder.Length; i++) synOrder[i] = i;
Array.Sort(synOrder, delegate(int a, int b) {
    int x = string.CompareOrdinal(synAllT[a], synAllT[b]);
    if (x != 0) return x;
    x = string.CompareOrdinal(synAllC[a], synAllC[b]);
    if (x != 0) return x;
    x = string.CompareOrdinal(synAllK[a], synAllK[b]);
    if (x != 0) return x;
    return string.CompareOrdinal(synAllS[a], synAllS[b]);
});

var synSb = new System.Text.StringBuilder();
synSb.AppendLine("\t\t\t\tDATATABLE(");
synSb.AppendLine("\t\t\t\t    \"TableName\", STRING,");
synSb.AppendLine("\t\t\t\t    \"ColumnName\", STRING,");
synSb.AppendLine("\t\t\t\t    \"Canonical\", STRING,");
synSb.AppendLine("\t\t\t\t    \"Synonym\", STRING,");
synSb.AppendLine("\t\t\t\t    {");
if (synAllT.Count == 0)
{
    // Empty-stub: matches the placeholder shipped in the shared scaffold so
    // the diff for unannotated models is zero-bytes. Single _PLACEHOLDER row
    // is filtered out by callers (canonical-existence gate in
    // _GetColumnSynonymMatches makes it inert).
    synSb.AppendLine("\t\t\t\t        {\"_PLACEHOLDER\", \"_PLACEHOLDER\", \"_PLACEHOLDER\", \"_PLACEHOLDER\"}");
}
else
{
    var rowLines = new List<string>();
    for (int idx = 0; idx < synOrder.Length; idx++)
    {
        int i = synOrder[idx];
        rowLines.Add("\t\t\t\t        {" + DaxStr(synAllT[i]) + ", " + DaxStr(synAllC[i]) + ", " + DaxStr(synAllK[i]) + ", " + DaxStr(synAllS[i]) + "}");
    }
    synSb.AppendLine(string.Join(",\n", rowLines.ToArray()));
}
synSb.AppendLine("\t\t\t\t    }");
synSb.Append("\t\t\t\t)");
var synExpr = synSb.ToString();

// Pre-scan Model.Functions for both required helpers BEFORE mutating either,
// so we either apply both updates or none (avoids partial-update state if
// SAV exists but SALC is missing or vice versa).
// Without this guard, a misconfigured model (e.g. merge_shared_scaffold skipped)
// would silently leave one or both helper UDFs at their stub bodies post-deploy,
// with no failure surfaced.
bool savFound = false;
bool salcFound = false;
foreach (var f in Model.Functions)
{
    if (f.Name == SAV_FQN) savFound = true;
    else if (f.Name == SALC_FQN) salcFound = true;
}

// Skip silently if BOTH helpers are missing AND the model has zero
// Copilot_SearchRanker / Copilot_SearchLadder / Copilot_ValueSynonyms
// annotations. This means the model is not framework-enabled (e.g. another model
// in the HelixFabric-Insights workspace), so
// generateSearchHelpers has nothing to do. Same defensive pattern as
// generateInfoAnnotations / generateInfoHierarchies which skip silently when
// their target table is absent. Without this gate, the T6 fail-loud guard
// below incorrectly fires on every non-framework model that the deploy
// pipeline iterates over.
if (!savFound && !salcFound && rankerCount == 0 && ladderCount == 0 && synAllT.Count == 0)
{
    Info("generateSearchHelpers: model has no Copilot_SearchRanker / Copilot_SearchLadder / Copilot_ValueSynonyms annotations and no helper UDFs — model is not framework-enabled, skipping.");
    return;
}

if (!savFound || !salcFound)
{
    var missing = new List<string>();
    if (!savFound) missing.Add(SAV_FQN);
    if (!salcFound) missing.Add(SALC_FQN);
    throw new InvalidOperationException(
        "generateSearchHelpers: required helper UDF(s) missing from Model.Functions: " +
        string.Join(", ", missing.ToArray()) +
        ". The shared scaffold should have provided these. Verify that " +
        "merge_shared_scaffold ran successfully in pre_process and that the " +
        "model has a per-model overlay dir at " +
        ".deploy/workspace/askadia/udf/models/<slug>/README.md " +
        "(setup_askadia_framework gates on that file)."
    );
}

foreach (var f in Model.Functions)
{
    if (f.Name == SAV_FQN)
    {
        f.Expression = savBody;
        f.Description = savDescription;
        Info("UDF '" + SAV_FQN + "' regenerated.");
    }
    else if (f.Name == SALC_FQN)
    {
        f.Expression = salcBody;
        f.Description = salcDescription;
        Info("UDF '" + SALC_FQN + "' regenerated.");
    }
}

// ----- Self-check: emitted bodies must NOT match the empty-stub form when
// the model has any rankers or ladders. Catches a logic bug in this csx where
// rankerCount/ladderCount > 0 but savRefs/salcRefs accidentally end up empty
// (e.g. a downstream change that filters refs out). The empty-stub body is
// what we deliberately commit as source for drift-proofing — it is correct
// ONLY when the model genuinely has zero rankers AND zero ladders.
string EMPTY_STUB_MARKER = "FILTER(ROW(\"_\", 1), FALSE())";
bool savIsStub = savBody.Contains(EMPTY_STUB_MARKER);
bool salcIsStub = salcBody.Contains(EMPTY_STUB_MARKER);
if ((rankerCount > 0 || ladderCount > 0) && savIsStub)
{
    throw new InvalidOperationException(
        "generateSearchHelpers ASSERT FAILED: " + SAV_FQN +
        " produced empty-stub body but rankerCount=" + rankerCount +
        " ladderCount=" + ladderCount + ". Codegen has a logic bug — DO NOT DEPLOY.");
}
if (ladderCount > 0 && salcIsStub)
{
    throw new InvalidOperationException(
        "generateSearchHelpers ASSERT FAILED: " + SALC_FQN +
        " produced empty-stub body but ladderCount=" + ladderCount +
        ". Codegen has a logic bug — DO NOT DEPLOY.");
}

// ----- Apply _COPILOT_VALUE_SYNONYMS partition expression -----
// Idempotent: only writes when expression actually changes (mirrors the
// generateCopilotQuestions.csx pattern). Defensive about table absence:
// fail loud if the model has synonym annotations but the table is missing
// (incomplete shared scaffold), but skip silently when both are absent
// (older scaffold without value-synonyms support).
Table synTable = null;
foreach (var t in Model.Tables)
{
    if (t.Name == SYN_TABLE) { synTable = t; break; }
}
if (synTable == null)
{
    if (synAllT.Count > 0)
    {
        throw new InvalidOperationException(
            "generateSearchHelpers: model has " + synAllT.Count +
            " Copilot_ValueSynonyms entries but the " + SYN_TABLE + " table is missing. " +
            "The shared scaffold should have provided this table. Re-run merge_shared_scaffold."
        );
    }
    Info("generateSearchHelpers: " + SYN_TABLE + " table absent (older scaffold) — skipping synonym table population.");
}
else
{
    if (synTable.Partitions.Count == 0)
    {
        throw new InvalidOperationException(
            "generateSearchHelpers: " + SYN_TABLE + " has no partitions — shared scaffold is malformed."
        );
    }
    var synPartition = synTable.Partitions.First();
    var oldExpr = synPartition.Expression ?? "";
    if (oldExpr.Trim() != synExpr.Trim())
    {
        synPartition.Expression = synExpr;
        Info(SYN_TABLE + ": partition rewritten with " + synAllT.Count + " synonym row(s) from " + synColTable.Count + " column(s).");
    }
    else
    {
        Info(SYN_TABLE + ": partition unchanged (" + synAllT.Count + " row(s)) — skipping write.");
    }
}

Info("generateSearchHelpers: " + rankerCount + " ranker(s), " + ladderCount + " ladder hierarchy(ies), " + synAllT.Count + " synonym row(s) across " + synColTable.Count + " column(s).");
