// ============================================================================
// Preprocessing: Augment measure descriptions for self-scoping time metrics
// ============================================================================
// Runs after generateTimeIntelMeasures.csx and before setup_askadia_framework.
// Adds a short description note to base measures that default to the latest
// available period with data, so _INFO_MEASURES / DiscoverMeasures expose the
// metric-specific behavior without hardcoding the note in source TMDL.
// ============================================================================

using System;
using System.Collections.Generic;
using System.Linq;

const string Note = "Defaults to the latest available period with data when no Calendar filter is supplied.";
const string AnchorAnnotation = "TimeIntel_Anchor";
const string GeneratedAnnotation = "Auto_TimeIntel";

var VariantSuffixes = new string[]
{
    "WoW %",
    "MoM %",
    "YoY %",
    "PW",
    "PM",
    "PY",
    "WoW",
    "MoM",
    "YoY"
};

var SelfScopeTokens = new string[]
{
    "MaxDate",
    "MaxMonth",
    "MaxMonthId",
    "SetDateAnchor",
    "CalendarWindow",
    "MonthWindow",
    "MonthToDate"
};

Func<Measure, string> MeasureKey = null;
MeasureKey = m => (m.Table.Name ?? "") + "\t" + (m.Name ?? "");

Func<char, bool> IsIdentifierChar = null;
IsIdentifierChar = c =>
{
    return char.IsLetterOrDigit(c) || c == '_' || c == '.';
};

Func<string, string, bool> ContainsIdentifierRef = null;
ContainsIdentifierRef = delegate(string text, string identifier)
{
    if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(identifier)) return false;

    var start = 0;
    while (start <= text.Length - identifier.Length)
    {
        var idx = text.IndexOf(identifier, start, StringComparison.Ordinal);
        if (idx < 0) return false;

        var beforeOk = idx == 0 || !IsIdentifierChar(text[idx - 1]);
        var afterIdx = idx + identifier.Length;
        var afterOk = afterIdx >= text.Length || !IsIdentifierChar(text[afterIdx]);
        if (beforeOk && afterOk) return true;

        start = idx + 1;
    }

    return false;
};

Func<string, bool> ContainsSelfScopeToken = null;
ContainsSelfScopeToken = text =>
{
    if (string.IsNullOrEmpty(text)) return false;
    for (int i = 0; i < SelfScopeTokens.Length; i++)
    {
        if (text.IndexOf(SelfScopeTokens[i], StringComparison.OrdinalIgnoreCase) >= 0)
        {
            return true;
        }
    }
    return false;
};

var allMeasures = Model.AllMeasures.ToList();
var measureKeys = new HashSet<string>();
foreach (var measure in allMeasures)
{
    measureKeys.Add(MeasureKey(measure));
}

var variantMeasureKeys = new HashSet<string>();
var baseMeasureKeysWithVariants = new HashSet<string>();

foreach (var measure in allMeasures)
{
    var measureName = measure.Name ?? "";
    for (int i = 0; i < VariantSuffixes.Length; i++)
    {
        var suffixToken = " " + VariantSuffixes[i];
        if (!measureName.EndsWith(suffixToken, StringComparison.Ordinal)) continue;

        var baseName = measureName.Substring(0, measureName.Length - suffixToken.Length);
        var baseKey = (measure.Table.Name ?? "") + "\t" + baseName;
        if (!measureKeys.Contains(baseKey)) continue;

        variantMeasureKeys.Add(MeasureKey(measure));
        baseMeasureKeysWithVariants.Add(baseKey);
        break;
    }
}

var functionExpressions = new Dictionary<string, string>();
foreach (var f in Model.Functions)
{
    functionExpressions[f.Name] = f.Expression ?? "";
}

var selfScopingFunctions = new HashSet<string>();
foreach (var kvp in functionExpressions)
{
    if (ContainsSelfScopeToken(kvp.Value))
    {
        selfScopingFunctions.Add(kvp.Key);
    }
}

var changed = true;
while (changed)
{
    changed = false;
    foreach (var kvp in functionExpressions)
    {
        if (selfScopingFunctions.Contains(kvp.Key)) continue;

        foreach (var functionName in selfScopingFunctions.ToList())
        {
            if (!ContainsIdentifierRef(kvp.Value, functionName)) continue;

            selfScopingFunctions.Add(kvp.Key);
            changed = true;
            break;
        }
    }
}

Func<Measure, bool> IsGeneratedVariant = null;
IsGeneratedVariant = m => string.Equals(m.GetAnnotation(GeneratedAnnotation), "True", StringComparison.OrdinalIgnoreCase);

Func<Measure, bool> ReferencesSelfScopingFunction = null;
ReferencesSelfScopingFunction = measure =>
{
    var expression = measure.Expression ?? "";
    foreach (var functionName in selfScopingFunctions)
    {
        if (ContainsIdentifierRef(expression, functionName))
        {
            return true;
        }
    }
    return false;
};

Func<Measure, bool> ShouldAugment = null;
ShouldAugment = measure =>
{
    var key = MeasureKey(measure);
    if (IsGeneratedVariant(measure)) return false;
    if (variantMeasureKeys.Contains(key)) return false;
    if (!string.IsNullOrWhiteSpace(measure.GetAnnotation(AnchorAnnotation))) return true;
    if (baseMeasureKeysWithVariants.Contains(key)) return true;
    if (ContainsSelfScopeToken(measure.Expression ?? "")) return true;
    if (ReferencesSelfScopingFunction(measure)) return true;
    return false;
};

var updated = 0;
var alreadyHadNote = 0;
var skippedGeneratedVariants = 0;
var skippedSourceVariants = 0;

foreach (var measure in allMeasures)
{
    var key = MeasureKey(measure);
    if (IsGeneratedVariant(measure))
    {
        skippedGeneratedVariants++;
        continue;
    }
    if (variantMeasureKeys.Contains(key))
    {
        skippedSourceVariants++;
        continue;
    }
    if (!ShouldAugment(measure)) continue;

    var description = measure.Description ?? "";
    if (description.IndexOf(Note, StringComparison.Ordinal) >= 0)
    {
        alreadyHadNote++;
        continue;
    }

    measure.Description = string.IsNullOrWhiteSpace(description)
        ? Note
        : description.TrimEnd() + " " + Note;
    updated++;
}

Info(
    "augmentMeasureDescriptions: updated " + updated +
    " measure description(s); " + alreadyHadNote +
    " already had the note; skipped " + skippedGeneratedVariants +
    " generated variant(s), " + skippedSourceVariants +
    " source-controlled variant(s); detected " + selfScopingFunctions.Count +
    " self-scoping function(s)."
);
