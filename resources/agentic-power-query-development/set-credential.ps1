# set-credential.ps1
# Registers an OAuth2 credential with PQTest for a Fabric warehouse / SQL source,
# using the token your current Az PowerShell session already has.
#
# Usage:
#   .\set-credential.ps1 -QueryFile .\warehouse-query.pq

param(
    [Parameter(Mandatory)] [string] $QueryFile,
    [string] $Resource = "https://database.windows.net"
)

Import-Module Az.Accounts -ErrorAction Stop

$ctx = Get-AzContext
if (-not $ctx) {
    Write-Host "No Az context found. Run Connect-AzAccount first." -ForegroundColor Yellow
    exit 1
}

$token = (Get-AzAccessToken -ResourceUrl $Resource).Token

$cred = @{
    AuthenticationKind       = "OAuth2"
    AuthenticationProperties = @{
        AccessToken  = $token
        Expires      = (Get-Date).AddHours(1).ToString("r")
        RefreshToken = ""
    }
    PrivacySetting           = "None"
    Permissions              = @()
} | ConvertTo-Json -Depth 5

$pqtest = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\powerquery.vscode-powerquery-sdk-*\.nuget\Microsoft.PowerQuery.SdkTools.*\tools\PQTest.exe" |
          Sort-Object FullName -Descending |
          Select-Object -First 1 -ExpandProperty FullName

if (-not $pqtest) {
    Write-Host "PQTest.exe not found. Install the SDK first:" -ForegroundColor Yellow
    Write-Host "  code --install-extension PowerQuery.vscode-powerquery-sdk"
    exit 1
}

Write-Host "PQTest: $pqtest"
$cred | & $pqtest set-credential -q $QueryFile
