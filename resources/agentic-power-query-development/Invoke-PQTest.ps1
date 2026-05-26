# Invoke-PQTest.ps1
# Runs M against PQTest. Four input modes:
#
#   .\Invoke-PQTest.ps1 -QueryFile .\hello.pq
#   .\Invoke-PQTest.ps1 -PbipPath '.\Model.SemanticModel' -Target Users
#   .\Invoke-PQTest.ps1 -DataflowPath '.\Dataflow1.Dataflow' -Target DimUserGroup
#   .\Invoke-PQTest.ps1 -PqFolder .\queries -Target MostRecent
#
# The three composed modes read every named M expression from the source, wrap
# them as one let block ending in `in <Target>`, and pipe that to PQTest.
# Pass -ShowComposed to dump the let block next to the source for inspection.

param(
    [string] $QueryFile,
    [string] $PbipPath,
    [string] $DataflowPath,
    [string] $PqFolder,
    [string] $Target,
    [switch] $ShowComposed,
    [switch] $Raw
)

$pqtest = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\powerquery.vscode-powerquery-sdk-*\.nuget\Microsoft.PowerQuery.SdkTools.*\tools\PQTest.exe" |
          Sort-Object FullName -Descending |
          Select-Object -First 1 -ExpandProperty FullName
if (-not $pqtest) { throw "PQTest.exe not found. Install: code --install-extension PowerQuery.vscode-powerquery-sdk" }

function Read-PbipBindings([string] $root) {
    $bindings = [ordered]@{}
    $defDir = if (Test-Path (Join-Path $root 'definition')) { Join-Path $root 'definition' } else { $root }

    $expr = Join-Path $defDir 'expressions.tmdl'
    if (Test-Path $expr) {
        $lines = Get-Content $expr
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '^\s*expression\s+(\S+)\s*=\s*(.*)$') {
                $name = $matches[1]; $rest = $matches[2]
                if ($rest.TrimStart() -eq '```') {
                    $body = @()
                    $i++
                    while ($i -lt $lines.Count -and $lines[$i].TrimStart() -ne '```') {
                        $body += $lines[$i]; $i++
                    }
                    $bindings[$name] = ($body -join "`n")
                } else {
                    $bindings[$name] = $rest
                }
            }
        }
    }

    $tableDir = Join-Path $defDir 'tables'
    if (Test-Path $tableDir) {
        foreach ($f in Get-ChildItem $tableDir -Filter *.tmdl) {
            $lines = Get-Content $f.FullName
            $partName = $null
            for ($i = 0; $i -lt $lines.Count; $i++) {
                if ($lines[$i] -match '^\s*partition\s+(\S+)\s*=\s*m\s*$') { $partName = $matches[1] }
                elseif ($partName -and $lines[$i] -match '^\s*source\s*=\s*```\s*$') {
                    $body = @()
                    $i++
                    while ($i -lt $lines.Count -and $lines[$i].TrimEnd() -notmatch '^\s*```\s*$') {
                        $body += $lines[$i]; $i++
                    }
                    # Dedent: strip the common leading whitespace from all non-blank lines
                    $nonBlank = $body | Where-Object { $_ -match '\S' }
                    if ($nonBlank) {
                        $indents = $nonBlank | ForEach-Object { if ($_ -match '^(\s*)') { $matches[1].Length } else { 0 } }
                        $indent = ($indents | Measure-Object -Minimum).Minimum
                        if ($indent -gt 0) { $body = $body | ForEach-Object { if ($_.Length -ge $indent) { $_.Substring($indent) } else { $_ } } }
                    }
                    $bindings[$partName] = ($body -join "`n")
                    $partName = $null
                }
            }
        }
    }
    return $bindings
}

function Read-DataflowBindings([string] $root) {
    $mashup = if (Test-Path $root -PathType Container) { Join-Path $root 'mashup.pq' } else { $root }
    $text = Get-Content $mashup -Raw
    # Drop optional StagingDefinition header and the section line
    $text = $text -replace '(?ms)\A\s*\[[^\]]*\]\s*', ''
    $text = $text -replace '(?m)^\s*section\s+\w+\s*;\s*', ''
    $bindings = [ordered]@{}
    # Split on lines beginning with `shared `; trailing `;` ends each binding
    $parts = [regex]::Split($text, '(?m)^shared\s+')
    foreach ($p in $parts) {
        if ($p -match '^\s*$') { continue }
        # Name is either #"quoted with spaces" or a bare identifier
        if ($p -match '^(?s)(#"[^"]+"|\S+?)\s*=\s*(.*?);\s*$') {
            $bindings[$matches[1]] = $matches[2]
        }
    }
    return $bindings
}

function Read-PqFolderBindings([string] $folder) {
    $bindings = [ordered]@{}
    foreach ($f in Get-ChildItem $folder -Filter *.pq) {
        $bindings[$f.BaseName] = (Get-Content $f.FullName -Raw)
    }
    return $bindings
}

function Compose-Let($bindings, $target) {
    if (-not $bindings.Contains($target)) {
        throw "Target '$target' not found. Available: $($bindings.Keys -join ', ')"
    }
    $body = @()
    foreach ($k in $bindings.Keys) { $body += "    $k = $($bindings[$k])" }
    "let`n" + ($body -join ",`n") + "`nin`n    $target"
}

# Resolve the runnable .pq file path
$runFile = $null
$sidecar = $null
if ($QueryFile) {
    $runFile = (Resolve-Path $QueryFile).Path
} else {
    if (-not $Target) { throw "-Target is required when composing from a source artifact." }
    $bindings = $null; $sourceLeaf = $null
    if ($PbipPath)         { $bindings = Read-PbipBindings     (Resolve-Path $PbipPath).Path;     $sourceLeaf = (Get-Item $PbipPath).Name }
    elseif ($DataflowPath) { $bindings = Read-DataflowBindings (Resolve-Path $DataflowPath).Path; $sourceLeaf = (Get-Item $DataflowPath).Name }
    elseif ($PqFolder)     { $bindings = Read-PqFolderBindings (Resolve-Path $PqFolder).Path;     $sourceLeaf = (Get-Item $PqFolder).Name }
    else { throw "Specify one of -QueryFile, -PbipPath, -DataflowPath, -PqFolder." }

    $composed = Compose-Let $bindings $Target
    $runFile = [IO.Path]::Combine([IO.Path]::GetTempPath(), "pqtest-$([guid]::NewGuid().ToString('N')).pq")
    $composed | Set-Content $runFile -Encoding UTF8
    if ($ShowComposed) {
        $sidecar = Join-Path (Get-Location) "$sourceLeaf.$Target.composed.pq"
        $composed | Set-Content $sidecar -Encoding UTF8
        Write-Host "Wrote $sidecar" -ForegroundColor DarkGray
    }
}

try {
    $json = (& $pqtest run-test -q $runFile --prettyPrint) -join "`n"
    if ($Raw) { $json; return }
    $result = $json | ConvertFrom-Json -ErrorAction Stop

    foreach ($r in $result) {
        if ($r.Status -eq 'Passed') {
            Write-Host "PASS  $(if ($Target) { $Target } else { $r.Name })  ($($r.RowCount) rows)" -ForegroundColor Green
            $r.Output | Select-Object -First 5 | Format-Table -AutoSize -Wrap
        } else {
            Write-Host "FAIL  $(if ($Target) { $Target } else { $r.Name })" -ForegroundColor Red
            Write-Host "  Message: $($r.Error.Message)"
            if ($r.Error.Details) { $r.Error.Details | ConvertTo-Json -Depth 5 | Write-Host }
        }
    }
    $result
}
finally {
    if (-not $QueryFile -and (Test-Path $runFile)) { Remove-Item $runFile -ErrorAction SilentlyContinue }
}
