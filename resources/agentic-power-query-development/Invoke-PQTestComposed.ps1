# Invoke-PQTestComposed.ps1
# Composes a query .pq with shared fragments, then runs PQTest on the result.
#
# How it works:
#   Inside any .pq file, a comment of the form
#       // #include path/to/fragment.pq
#   on its own line is replaced with the contents of that file before PQTest
#   ever sees it. Includes are resolved recursively (a fragment can include
#   other fragments). Paths are relative to the file doing the including.
#
# Why:
#   PQTest evaluates one M expression per file. Real Power Query projects
#   have parameters, UDFs, and many cross-referencing queries. This wrapper
#   lets you keep them in separate files and stitch them into the single
#   `let` block PQTest needs at evaluation time.
#
# Usage:
#   .\Invoke-PQTestComposed.ps1 -QueryFile .\query-users.pq
#   .\Invoke-PQTestComposed.ps1 -QueryFile .\query-users.pq -Raw       # raw JSON
#   .\Invoke-PQTestComposed.ps1 -QueryFile .\query-users.pq -ShowComposed
#       # writes the composed file alongside the source as <name>.composed.pq
#       # (useful when debugging include resolution)

param(
    [Parameter(Mandatory)] [string] $QueryFile,
    [switch] $Raw,
    [switch] $ShowComposed
)

$ErrorActionPreference = "Stop"

function Resolve-Includes {
    param([string] $Path, [System.Collections.Generic.HashSet[string]] $Stack)
    $full = (Resolve-Path $Path).Path
    if (-not $Stack.Add($full)) { throw "Include cycle detected at: $full" }
    try {
        $text = Get-Content $full -Raw
        $dir  = Split-Path -Parent $full
        return [regex]::Replace(
            $text,
            '(?m)^\s*//\s*#include\s+(\S+)\s*$',
            {
                param($m)
                $inc = Join-Path $dir $m.Groups[1].Value
                if (-not (Test-Path $inc)) { throw "Include not found: $inc (referenced from $full)" }
                (Resolve-Includes -Path $inc -Stack $Stack).TrimEnd()
            }
        )
    } finally {
        [void] $Stack.Remove($full)
    }
}

$composed = Resolve-Includes -Path $QueryFile -Stack ([System.Collections.Generic.HashSet[string]]::new())

if ($ShowComposed) {
    $sidecar = [IO.Path]::ChangeExtension((Resolve-Path $QueryFile).Path, ".composed.pq")
    $composed | Set-Content -Path $sidecar -Encoding UTF8
    Write-Host "Composed file: $sidecar" -ForegroundColor DarkGray
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("pqtest-" + [guid]::NewGuid().ToString("N").Substring(0,8) + ".pq")
$composed | Set-Content -Path $tmp -Encoding UTF8

$pqtest = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\powerquery.vscode-powerquery-sdk-*\.nuget\Microsoft.PowerQuery.SdkTools.*\tools\PQTest.exe" |
          Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName

if (-not $pqtest) {
    Write-Host "PQTest.exe not found. Install the SDK first:" -ForegroundColor Yellow
    Write-Host "  code --install-extension PowerQuery.vscode-powerquery-sdk"
    exit 1
}

try {
    $json = (& $pqtest run-test -q $tmp --prettyPrint) -join "`n"
    if ($Raw) { $json; return }

    try { $result = $json | ConvertFrom-Json }
    catch {
        Write-Host "Could not parse PQTest output as JSON:" -ForegroundColor Red
        Write-Host $json
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
} finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}
