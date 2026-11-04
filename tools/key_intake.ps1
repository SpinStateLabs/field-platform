# key_intake.ps1 - move a Console-made Anthropic key from the clipboard into an owner-only file,
# without the key ever appearing in chat, a terminal, a transcript or a command line.
#
# Run by Claude (never pasted by Don). Don's only acts are two clicks in the Console: Create key, Copy.
#
#   .\key_intake.ps1 -Name anthropic-ws-force-field -Kind workspace
#   .\key_intake.ps1 -Name anthropic-admin -Kind admin -Replace
#
# What it does, in order (fails closed at each step; nothing is printed that contains the key):
#   1. records the clipboard's current fingerprint, so a key already on the clipboard is not taken;
#   2. polls up to -TimeoutSec for a NEW clipboard value that matches the key shape for -Kind;
#   3. creates the destination file empty, sets an owner-only ACL, THEN writes the key (UTF-8, no BOM);
#   4. clears the clipboard (Windows clipboard history, if enabled, may still hold it: see NOTES);
#   5. verifies the key with one read-only API call and prints status, fingerprint (first 8 hex of
#      SHA-256) and file path only.
# Refuses to overwrite a non-empty file unless -Replace (the old file is kept as <name>.key.prev).
#
# NOTES: the secret is never an argument, never in an environment variable of a child process, never
# logged. Fingerprint is a hash prefix, not reversible. Windows "clipboard history" (Win+V) can retain
# the entry: -Name runs warn if it is enabled; turning it off is the user's setting, not changed here.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9._-]{1,64}$')][string]$Name,
    [Parameter(Mandatory)][ValidateSet('workspace', 'admin', 'environment')][string]$Kind,
    [string]$EnvironmentId,   # with -Kind environment: verify the key against this environment's work queue
    [string]$KeyDir = (Join-Path $env:USERPROFILE '.field-local\keys'),
    [int]$TimeoutSec = 300,
    [switch]$Replace,
    [switch]$AcceptCurrent,   # take a key already on the clipboard (the Copy click happened before the run)
    [switch]$SkipVerify
)
$ErrorActionPreference = 'Stop'

# Console keys seen: sk-ant-api03-..., sk-ant-usr-... (user-linked), sk-ant-admin... ; a workspace key is any
# sk-ant- key that is not an admin key.
$shape = if ($Kind -eq 'admin') { '^sk-ant-admin[A-Za-z0-9_\-]{20,}$' }
         elseif ($Kind -eq 'environment') { '^sk-ant-oat[A-Za-z0-9_\-]{20,}$' }
         else { '^sk-ant-(?!admin|oat)[A-Za-z0-9_\-]{20,}$' }

function Get-Fp([string]$s) {
    if ([string]::IsNullOrEmpty($s)) { return '' }
    $b = [Text.Encoding]::UTF8.GetBytes($s)
    $h = [Security.Cryptography.SHA256]::Create().ComputeHash($b)
    -join ($h[0..3] | ForEach-Object { $_.ToString('x2') })
}

New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
$dest = Join-Path $KeyDir "$Name.key"
if ((Test-Path $dest) -and ((Get-Item $dest).Length -gt 0) -and -not $Replace) {
    throw "refused: $dest is not empty; pass -Replace to rotate (old file kept as .prev). Nothing changed."
}

$baseline = Get-Fp ((Get-Clipboard -Raw) -as [string])
Write-Output "waiting up to $TimeoutSec s for a new $Kind key on the clipboard (click Create key, then Copy in the Console)"
$key = $null
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
    $clip = ((Get-Clipboard -Raw) -as [string])
    if ($clip) {
        $t = $clip.Trim()
        if ($t -match $shape -and ($AcceptCurrent -or (Get-Fp $t) -ne $baseline)) { $key = $t; break }
    }
    Start-Sleep -Milliseconds 400
}
if (-not $key) { throw "timed out: no new $Kind-shaped key reached the clipboard. Nothing written." }

# destination: empty file, owner-only ACL first, then the secret
if (Test-Path $dest) { Copy-Item $dest "$dest.prev" -Force }
Set-Content -Path $dest -Value '' -NoNewline
& icacls.exe $dest /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
if ($LASTEXITCODE -ne 0) { Remove-Item $dest -Force; throw 'icacls failed; file removed, nothing stored.' }
[IO.File]::WriteAllText($dest, $key, (New-Object Text.UTF8Encoding($false)))

Set-Clipboard -Value ' '
$fp = Get-Fp $key
$len = (Get-Item $dest).Length

$status = 'not verified (-SkipVerify)'
if (-not $SkipVerify) {
    $h = @{ 'x-api-key' = $key; 'anthropic-version' = '2023-06-01' }
    $uri = 'https://api.anthropic.com/v1/organizations/users?limit=1'
    if ($Kind -eq 'workspace') { $uri = 'https://api.anthropic.com/v1/agents?limit=1'; $h['anthropic-beta'] = 'managed-agents-2026-04-01' }
    if ($Kind -eq 'environment') {
        # an environment key is a queue credential: Bearer on /work/stats (x-api-key is rejected)
        $h = @{ 'Authorization' = "Bearer $key"; 'anthropic-version' = '2023-06-01'; 'anthropic-beta' = 'managed-agents-2026-04-01' }
        $uri = "https://api.anthropic.com/v1/environments/$EnvironmentId/work/stats"
        if (-not $EnvironmentId) { $uri = $null }
    }
    if (-not $uri) { $status = 'not verified (no -EnvironmentId)'; $SkipVerify = $true }
    try { Invoke-RestMethod -Uri $uri -Headers $h -Method Get | Out-Null; $status = 'verified: read-only call HTTP 200' }
    catch { $status = "VERIFY FAILED: HTTP $([int]$_.Exception.Response.StatusCode)" }
}
$key = $null
$ch = (Get-ItemProperty 'HKCU:\Software\Microsoft\Clipboard' -ErrorAction SilentlyContinue).EnableClipboardHistory
if ($ch -eq 1) { Write-Warning 'Windows clipboard history is ON: the key may remain in Win+V history until it is cleared.' }
Write-Output "stored: $dest ($len bytes, owner-only ACL); fingerprint $fp; $status; clipboard cleared"
