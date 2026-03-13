// Generates Time Intelligence measures for base measures annotated with GenerateTimeIntelligence = true.

using System.Linq;

var dateColumn = "'Date'[Date]";
var folder = "Time Intelligence";

// Delete all existing TI measures, then regenerate
foreach(var m in Model.AllMeasures.Where(m => m.DisplayFolder == folder).ToList())
    m.Delete();

var baseMeasures = Model.AllMeasures.Where(m => m.GetAnnotation("GenerateTimeIntelligence") == "true").ToList();

foreach(var m in baseMeasures)
{
    m.Table.AddMeasure(m.Name + " YTD",
        "TOTALYTD(" + m.DaxObjectName + ", " + dateColumn + ")", folder).FormatString = m.FormatString;

    m.Table.AddMeasure(m.Name + " PY",
        "CALCULATE(" + m.DaxObjectName + ", SAMEPERIODLASTYEAR(" + dateColumn + "))", folder).FormatString = m.FormatString;

    m.Table.AddMeasure(m.Name + " YoY",
        m.DaxObjectName + " - [" + m.Name + " PY]", folder).FormatString = m.FormatString;

    m.Table.AddMeasure(m.Name + " YoY%",
        "DIVIDE([" + m.Name + " YoY], [" + m.Name + " PY])", folder).FormatString = "0.0%";

    m.Table.AddMeasure(m.Name + " QTD",
        "TOTALQTD(" + m.DaxObjectName + ", " + dateColumn + ")", folder).FormatString = m.FormatString;

    m.Table.AddMeasure(m.Name + " MTD",
        "TOTALMTD(" + m.DaxObjectName + ", " + dateColumn + ")", folder).FormatString = m.FormatString;
}
