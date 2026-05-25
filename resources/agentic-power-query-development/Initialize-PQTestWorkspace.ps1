# Initialize-PQTestWorkspace.ps1
# One-time setup for a folder you want to iterate on Power Query in with an LLM.
#
# What it does:
#   1. Verifies the Power Query SDK extension is installed (installs it if not).
#   2. Resolves the PQTest.exe path and writes it to $env:PQTEST_PATH for the session.
#   3. Drops an AGENTS.md into the current folder so any agent that reads the
#      AGENTS.md / copilot-instructions.md convention (Copilot CLI, Claude Code,
#      Cursor, Continue, etc.) picks up the loop instructions automatically.
#
# Usage (from the folder you want to work in):
#   .\Initialize-PQTestWorkspace.ps1
#   .\Initialize-PQTestWorkspace.ps1 -Force   # overwrite an existing AGENTS.md

param(
    [switch] $Force
)

$ErrorActionPreference = "Stop"

# 1. SDK extension
$extensionId = "PowerQuery.vscode-powerquery-sdk"
$installed   = (& code --list-extensions) -contains $extensionId
if (-not $installed) {
    Write-Host "Installing $extensionId ..." -ForegroundColor Cyan
    & code --install-extension $extensionId | Out-Null
} else {
    Write-Host "$extensionId already installed." -ForegroundColor DarkGray
}

# 2. PQTest path
$pqtest = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\powerquery.vscode-powerquery-sdk-*\.nuget\Microsoft.PowerQuery.SdkTools.*\tools\PQTest.exe" |
          Sort-Object FullName -Descending |
          Select-Object -First 1 -ExpandProperty FullName

if (-not $pqtest) {
    Write-Host "Could not find PQTest.exe even after install. Restart VS Code once and re-run." -ForegroundColor Yellow
    exit 1
}

$env:PQTEST_PATH = $pqtest
Write-Host "PQTEST_PATH = $pqtest" -ForegroundColor Green

# 3. AGENTS.md
$agentsPath = Join-Path (Get-Location) "AGENTS.md"
if ((Test-Path $agentsPath) -and -not $Force) {
    Write-Host "AGENTS.md already exists. Use -Force to overwrite." -ForegroundColor DarkGray
} else {
    @'
# Iterating on Power Query with PQTest

This folder is set up to evaluate Power Query M headlessly with PQTest so changes
can be tested without touching a PBIX, dataflow, or semantic model.

## The loop

When the user asks you to write or change a Power Query M expression:

1. Write the proposed M to a `.pq` file in this folder (default: `./test.pq`).
2. Run PQTest against it:

   ```powershell
   & $env:PQTEST_PATH run-test -q .\test.pq -p
   ```

   If `$env:PQTEST_PATH` is not set, re-run `.\Initialize-PQTestWorkspace.ps1`.
3. Parse the JSON output.
   - If `Status == "Passed"`, inspect the first rows of `Output` and the column
     names and types. Confirm the shape matches the user's intent.
   - If `Status == "Failed"`, read `Error.Message` and `Error.Details`, propose
     a fix, explain what the previous attempt got wrong, and re-run.
4. Show a diff of what changed between iterations.

## Things to watch for

- Power Query returns `null` silently for missing column references. If the
  user's expected output has unexpected nulls, treat that as a failure even if
  `Status == "Passed"`.
- Cap at 10 iterations. If you have not passed by then, stop and ask the user
  for guidance.
- When the error includes the available alternatives (e.g. for a missing
  table or key), use those to inform the next attempt rather than guessing.

## Credentials

If the query hits a remote source (SQL, Fabric warehouse, etc.) the user needs
to register a credential first. The included `set-credential.ps1` will pull an
OAuth2 token from the current Az PowerShell session and register it for a given
query file. Do not try to register credentials silently on the user's behalf.
'@ | Set-Content -Path $agentsPath -Encoding UTF8
    Write-Host "Wrote AGENTS.md" -ForegroundColor Green
}

Write-Host ""
Write-Host "Ready. Try:" -ForegroundColor Cyan
Write-Host "  .\Invoke-PQTest.ps1 -QueryFile .\hello.pq"
