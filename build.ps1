param([switch]$Installer, [string]$InnoCompiler = "ISCC.exe", [switch]$Qa)
$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
Set-Location $PSScriptRoot
function Invoke-Checked([scriptblock]$Command) { & $Command; if ($LASTEXITCODE -ne 0) { throw "Build step failed: $Command" } }
Push-Location still-ui
try {
  Invoke-Checked { npm ci }
  Invoke-Checked { node --test tests/suggestions.test.ts }
  Invoke-Checked { npm run lint }
  Invoke-Checked { npm run build }
} finally { Pop-Location }
$destination = if ($Qa) { 'artifacts/Still-QA' } else { 'artifacts/Still' }
$qaProperty = if ($Qa) { 'true' } else { 'false' }
$resolvedDestination = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $destination))
$artifactBoundary = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'artifacts')) + [IO.Path]::DirectorySeparatorChar
if (-not $resolvedDestination.StartsWith($artifactBoundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid artifact destination.' }
if (Test-Path -LiteralPath $resolvedDestination) { Remove-Item -LiteralPath $resolvedDestination -Recurse -Force }
Invoke-Checked { dotnet publish still/Still.csproj -c Release -r win-x64 --self-contained true "-p:StillQa=$qaProperty" -p:DebugType=None -o $destination }
Copy-Item still/Assets/still.ico "$destination/Assets/still.ico"
Copy-Item LICENSE,README.md,SECURITY.md,THIRD-PARTY-NOTICES.txt $destination
New-Item -ItemType Directory -Force "$destination/Licenses" | Out-Null
Copy-Item Licenses/* "$destination/Licenses" -Recurse -Force
if ($Installer) {
  if ($Qa) { throw 'Automation builds cannot be packaged for distribution.' }
  New-Item -ItemType Directory -Force tools | Out-Null
  $bootstrapper = Join-Path $PSScriptRoot 'tools/MicrosoftEdgeWebview2Setup.exe'
  Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrapper
  $signature = Get-AuthenticodeSignature -LiteralPath $bootstrapper
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Microsoft Corporation,') { throw 'Microsoft bootstrapper signature verification failed.' }
  $appSource = Join-Path $PSScriptRoot $destination
  $outputRoot = Join-Path $PSScriptRoot 'artifacts'
  Invoke-Checked { & $InnoCompiler "/DAppExe=$(Join-Path $appSource 'Still.exe')" "/DOutputRoot=$outputRoot" "/DBootstrapper=$bootstrapper" installer/Still.iss }
}
