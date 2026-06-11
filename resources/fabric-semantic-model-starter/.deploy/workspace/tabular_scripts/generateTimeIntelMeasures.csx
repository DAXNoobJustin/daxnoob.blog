// generateTimeIntelMeasures.csx
//
// Pre-deploy Tabular Editor 2 script. Generates the standard time-intelligence
// variant family for any base measure tagged with `TimeIntel_Anchor`.
//
// Annotation contract (single annotation on the base measure):
//   TimeIntel_Anchor = Local.X.MaxDate    // zero-arg anchor UDF; presence = opt-in
//
// Shift family is inferred from the anchor UDF name:
//   - name contains "MonthId" => Month family (PM/PY/MoM/MoM %/YoY/YoY %)
//   - otherwise              => Day family   (PW/PM/PY/WoW/WoW %/MoM/MoM %/YoY/YoY %)
//
// Cleanup: every generated measure carries `Auto_TimeIntel = True`. The script
// deletes all such measures at the start of each run.
//
// NOTE: TE2's CSX engine is finicky — this script keeps EVERYTHING inside the
// top-level script body (no field-then-method declarations, no classes, no
// verbatim strings, no Regex). All catalog data and helpers are defined inline.

using System;
using System.Collections.Generic;
using System.Linq;

const string AnnotationAnchor      = "TimeIntel_Anchor";
const string AnnotationGenerated   = "Auto_TimeIntel";
const string DisplayFolderVariants = "-> Additional Aggregations of Base Measures";
const string PercentFormat         = "#,0.0%;-#,0.0%;#,0.0%";

// ---- Variant catalog (parallel arrays) ---------------------------------------
// Kinds: "Shift" | "POP" | "POPPercent"

// Day family (anchor returns a date; shifts in days)
var DaySuffix  = new string[] { "PW",  "PM",  "PY",   "WoW", "WoW %", "MoM", "MoM %", "YoY", "YoY %" };
var DayDescTpl = new string[] {
    "Prior-week value of {0}.",
    "Prior-month value of {0}.",
    "Prior-year value of {0}.",
    "Week-over-week change in {0}.",
    "Week-over-week percentage change in {0}.",
    "Month-over-month change in {0}.",
    "Month-over-month percentage change in {0}.",
    "Year-over-year change in {0}.",
    "Year-over-year percentage change in {0}."
};
var DayKind  = new string[] { "Shift","Shift","Shift","POP", "POPPercent","POP", "POPPercent","POP", "POPPercent" };
var DayShift = new int[]    { -7,    -28,   -365,  0,     0,           0,     0,           0,     0 };
var DayPrior = new string[] { "",    "",    "",    "PW",  "PW",        "PM",  "PM",        "PY",  "PY" };

// Month family (anchor returns a fiscal month id; shifts in months — no PW/WoW)
var MonthSuffix  = new string[] { "PM",  "PY",   "MoM", "MoM %",     "YoY", "YoY %" };
var MonthDescTpl = new string[] {
    "Prior-month value of {0}.",
    "Prior-year value of {0}.",
    "Month-over-month change in {0}.",
    "Month-over-month percentage change in {0}.",
    "Year-over-year change in {0}.",
    "Year-over-year percentage change in {0}."
};
var MonthKind  = new string[] { "Shift","Shift","POP", "POPPercent","POP", "POPPercent" };
var MonthShift = new int[]    { -1,    -12,    0,     0,           0,     0 };
var MonthPrior = new string[] { "",    "",     "PM",  "PM",        "PY",  "PY" };

// ---- Inline helpers (Funcs so the script body owns them) --------------------

Func<string, bool> IsAnchorValid = anchor =>
{
    if (string.IsNullOrEmpty(anchor)) return false;
    char first = anchor[0];
    bool firstOk = (first >= 'A' && first <= 'Z') || (first >= 'a' && first <= 'z') || first == '_';
    if (!firstOk) return false;
    foreach (char c in anchor)
    {
        bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '.';
        if (!ok) return false;
    }
    return true;
};

Func<string, bool> IsMonthFamily = anchorUdf =>
    anchorUdf.IndexOf("MonthId", StringComparison.OrdinalIgnoreCase) >= 0;

Func<bool, string> ShiftFunctionFor = isMonth =>
    isMonth ? "Local.TimeIntelligence.MonthShift" : "Local.TimeIntelligence.DayShift";

// ---- Preflight: validate config + detect collisions BEFORE deleting anything

var preflightBases   = new List<Measure>();
var preflightAnchors = new List<string>();
var preflightIsMonth = new List<bool>();
var errors           = new List<string>();

foreach (var baseMeasure in Model.AllMeasures.ToList())
{
    var anchor = baseMeasure.GetAnnotation(AnnotationAnchor);
    if (string.IsNullOrWhiteSpace(anchor)) continue;

    if (!IsAnchorValid(anchor))
    {
        errors.Add(string.Format(
            "[{0}].[{1}] annotation '{2}'='{3}' is not a bare UDF reference. Provide the function name without parentheses or whitespace (e.g. 'Local.FabricStorage.MaxDate').",
            baseMeasure.Table.Name, baseMeasure.Name, AnnotationAnchor, anchor));
        continue;
    }

    var isMonth  = IsMonthFamily(anchor);
    var suffixes = isMonth ? MonthSuffix : DaySuffix;

    // Family-level collision check.
    var collisions = new List<string>();
    for (int i = 0; i < suffixes.Length; i++)
    {
        var variantName = baseMeasure.Name + " " + suffixes[i];
        var existing = baseMeasure.Table.Measures.FirstOrDefault(x => x.Name == variantName);
        if (existing != null && existing.GetAnnotation(AnnotationGenerated) != "True")
        {
            collisions.Add(variantName);
        }
    }
    if (collisions.Count > 0)
    {
        errors.Add(string.Format(
            "[{0}].[{1}] cannot generate variant family — hand-written measure(s) already own these names: {2}. Delete the hand-written measure(s) so this script can own them, or remove the {3} annotation on the base.",
            baseMeasure.Table.Name, baseMeasure.Name, string.Join(", ", collisions), AnnotationAnchor));
        continue;
    }

    preflightBases.Add(baseMeasure);
    preflightAnchors.Add(anchor);
    preflightIsMonth.Add(isMonth);
}

if (errors.Count > 0)
{
    foreach (var e in errors) Error(e);
    throw new Exception(string.Format(
        "generateTimeIntelMeasures preflight failed with {0} error(s) — see above. No measures modified.",
        errors.Count));
}

// ---- Cleanup: drop every previously-generated variant -----------------------

int removed = 0;
foreach (var m in Model.AllMeasures.ToList())
{
    if (m.GetAnnotation(AnnotationGenerated) == "True")
    {
        m.Delete();
        removed++;
    }
}
Info(string.Format("generateTimeIntelMeasures: removed {0} previously-generated variants.", removed));

// ---- Generate the full variant family for each opted-in base measure --------

int created = 0;
for (int p = 0; p < preflightBases.Count; p++)
{
    var baseMeasure = preflightBases[p];
    var anchor      = preflightAnchors[p];
    var isMonth     = preflightIsMonth[p];

    var suffixes  = isMonth ? MonthSuffix  : DaySuffix;
    var descTpls  = isMonth ? MonthDescTpl : DayDescTpl;
    var kinds     = isMonth ? MonthKind    : DayKind;
    var shifts    = isMonth ? MonthShift   : DayShift;
    var priors    = isMonth ? MonthPrior   : DayPrior;

    for (int i = 0; i < suffixes.Length; i++)
    {
        var variantName = baseMeasure.Name + " " + suffixes[i];

        string expression;
        string formatString;
        switch (kinds[i])
        {
            case "Shift":
                expression   = string.Format("{0} ( [{1}], {2} ( ), {3} )",
                    ShiftFunctionFor(isMonth), baseMeasure.Name, anchor, shifts[i]);
                formatString = baseMeasure.FormatString;
                break;
            case "POP":
                expression   = string.Format("Local.TimeIntelligence.PeriodOverPeriod ( [{0}], [{1}] )",
                    baseMeasure.Name, baseMeasure.Name + " " + priors[i]);
                formatString = baseMeasure.FormatString;
                break;
            case "POPPercent":
                expression   = string.Format("Local.TimeIntelligence.PeriodOverPeriodPercent ( [{0}], [{1}] )",
                    baseMeasure.Name, baseMeasure.Name + " " + priors[i]);
                formatString = PercentFormat;
                break;
            default:
                throw new Exception("Unhandled variant kind: " + kinds[i]);
        }

        var description = string.Format(descTpls[i], baseMeasure.Name);

        var measure = baseMeasure.Table.AddMeasure(variantName, expression, DisplayFolderVariants);
        measure.FormatString = formatString;
        measure.Description = description;
        measure.IsHidden = baseMeasure.IsHidden;
        measure.SetAnnotation(AnnotationGenerated, "True");

        // Inherit BPA suppressions from the base — if the base is exempt
        // from a rule (e.g. UNNECESSARY_MEASURES on hidden shim measures),
        // its auto-generated variants must be too.
        var baseBpa = baseMeasure.GetAnnotation("BestPracticeAnalyzer_IgnoreRules");
        if (!string.IsNullOrWhiteSpace(baseBpa))
        {
            measure.SetAnnotation("BestPracticeAnalyzer_IgnoreRules", baseBpa);
        }

        // Inherit perspective membership from the base measure.
        foreach (var perspective in baseMeasure.Model.Perspectives)
        {
            if (baseMeasure.InPerspective[perspective])
            {
                measure.InPerspective[perspective] = true;
            }
        }

        measure.FormatDax();
        created++;
    }

    Info(string.Format("Generated {0} variants for [{1}].[{2}] ({3}-anchor)",
        suffixes.Length, baseMeasure.Table.Name, baseMeasure.Name, isMonth ? "Month" : "Day"));
}

Info(string.Format("generateTimeIntelMeasures: created {0} variants across {1} base measure(s).",
    created, preflightBases.Count));
