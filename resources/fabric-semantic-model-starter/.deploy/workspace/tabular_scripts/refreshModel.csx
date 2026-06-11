#r "Microsoft.AnalysisServices.Core.dll"
using System;
using ToM = Microsoft.AnalysisServices.Tabular;

// Get refresh type from environment variable (default to Calculate)
var refreshTypeStr = Environment.GetEnvironmentVariable("RefreshType") ?? "Calculate";

// Parse to enum
ToM.RefreshType refreshType;
if (!Enum.TryParse(refreshTypeStr, true, out refreshType))
{
    throw new ArgumentException(string.Format("Invalid RefreshType: {0}. Valid values: Full, Calculate, DataOnly, Automatic", refreshTypeStr));
}

Model.Database.TOMDatabase.Model.RequestRefresh(refreshType);
Model.Database.TOMDatabase.Model.SaveChanges();
