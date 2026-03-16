// refreshModel.csx
// Refreshes the model using the specified refresh type.
//
// Environment Variables:
//   RefreshType - Refresh type to use (default: Calculate)
//                 Valid values: Full, Calculate, DataOnly, Automatic

#r "Microsoft.AnalysisServices.Core.dll"
using System;
using ToM = Microsoft.AnalysisServices.Tabular;

var refreshTypeStr = Environment.GetEnvironmentVariable("RefreshType") ?? "Calculate";

ToM.RefreshType refreshType;
if (!Enum.TryParse(refreshTypeStr, true, out refreshType))
{
    throw new ArgumentException(
        string.Format("Invalid RefreshType: {0}. Valid values: Full, Calculate, DataOnly, Automatic", refreshTypeStr)
    );
}

Model.Database.TOMDatabase.Model.RequestRefresh(refreshType);
Model.Database.TOMDatabase.Model.SaveChanges();
