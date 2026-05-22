# Invoke-PQTest.ps1
# Locates PQTest.exe, runs a .pq file, and returns the parsed result.
# Status output goes to the host so the parsed object can be piped cleanly.
#
# Usage:
#   .\Invoke-PQTest.ps1 -QueryFile .\hello.pq
#   .\Invoke-PQTest.ps1 -QueryFile .\hello.pq -Raw   # raw JSON

param(
    [Parameter(Mandatory)] [string] $QueryFile,
    [switch] $Raw
)

$pqtest = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\powerquery.vscode-powerquery-sdk-*\.nuget\Microsoft.PowerQuery.SdkTools.*\tools\PQTest.exe" |
          Sort-Object FullName -Descending |
          Select-Object -First 1 -ExpandProperty FullName

if (-not $pqtest) {
    Write-Host "PQTest.exe not found. Install the SDK first:" -ForegroundColor Yellow
    Write-Host "  code --install-extension PowerQuery.vscode-powerquery-sdk"
    exit 1
}

$raw = & $pqtest run-test -q $QueryFile -p 2>&1 | Out-String
if ($Raw) { $raw; return }

try { $result = $raw | ConvertFrom-Json }
catch {
    Write-Host "Could not parse PQTest output as JSON:" -ForegroundColor Red
    Write-Host $raw
    exit 1
}

foreach ($r in $result) {
    if ($r.Status -eq "Passed") {
        Write-Host "PASS  $($r.Name)  ($($r.RowCount) rows)" -ForegroundColor Green
        $r.Output | Select-Object -First 5 | Format-Table -AutoSize -Wrap
    } else {
        Write-Host "FAIL  $($r.Name)" -ForegroundColor Red
        Write-Host "  Message: $($r.Error.Message)"
        if ($r.Error.Details) {
            Write-Host "  Details:"
            $r.Error.Details | ConvertTo-Json -Depth 5 | Write-Host
        }
    }
}

$result
