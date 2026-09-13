# ssl-verify-token.ps1 - prove a renewed delegation token through the SAME shim
# the ssl skills dot-source (field-rest.ps1), before renew_token.py revokes the
# old token. It is renew_token.py's --verify-cmd for the ssl agents:
#
#   powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ssl-verify-token.ps1 `
#       -Agent ssl-invoicing-agent -TokensFile <renew_token.py's --json-file> `
#       -NewToken {new_token} -InScopeAction "read timesheets"
#
# -TokensFile names the file the renewal swapped. The verifier refuses (exit 1,
# no call made) when that file does not exist, before it loads the shim, and
# when the shim resolved its token file to any other path (compared exactly,
# case included). Without the check the shim could present a token from another
# file (a real one) to whatever FIELD_PROXY_URL names. The scheduled command
# always passes it; a hand run without it skips only this path check (check 1
# still compares the token value).
#
# Always -File, never -Command: -File exits with this script's own exit code;
# -Command reports 1 for any non-zero exit, and 0 when a statement follows the
# script. Use double quotes around an action with spaces: renew_token.py splits
# --verify-cmd on double quotes only.
#
# Exit 0: every check passed. Exit 1: a check failed, or this environment cannot
# verify (client posture not enforce, no shim, an unexpected error). Exit 2:
# -Agent or -NewToken is malformed. renew_token.py counts every non-zero exit as
# a failed verification: it restores the token file, revokes the new token and
# keeps the old one.
#
# Checks, each printed as one PASS or FAIL line, all run:
#   1. token file:   the shim's own Get-FieldToken returns exactly -NewToken for
#                    -Agent, so the swap is what a skill will present
#   2. heartbeat:    the shim prints killed=false
#   3. in scope:     -InScopeAction is ALLOW with no clause (not shadowed). Pick
#                    an action in the manifest's delegation.scope that is NOT an
#                    escalation trigger
#   4. out of scope: a never-granted probe is BLOCK D.scope, so the estate is
#                    enforcing and the token is scoped, not merely accepted
# Verdicts are read from the lines the shim prints, never from its return
# values. Side effects: 2 conformance ledger events for -Agent (checks 3 and 4).
# No spend, no kill. Token ids are printed as 8-character prefixes only; the
# shim reads the secret and redacts every line it prints.
param(
    [Parameter(Mandatory)][string]$Agent,
    [Parameter(Mandatory)][string]$NewToken,
    [Parameter(Mandatory)][string]$InScopeAction,
    [string]$ShimPath = '',
    [string]$TokensFile = ''
)
$ErrorActionPreference = 'Stop'
# The shim beside this script by default. Resolved here, not in param(): Windows
# PowerShell 5.1 has not set $PSScriptRoot yet when it evaluates param defaults.
if (-not $ShimPath) { $ShimPath = Join-Path $PSScriptRoot 'field-rest.ps1' }
# Read before the shim is dot-sourced into this scope, so nothing it defines can change the answer.
$script:PinTokensFile = $PSBoundParameters.ContainsKey('TokensFile')
$script:Fails = 0
$script:Probe = 'token renewal verification: out-of-scope probe'

function Write-Check([bool]$Ok, [string]$Line) {
    if ($Ok) { Write-Output "PASS  $Line" } else { Write-Output "FAIL  $Line"; $script:Fails++ }
}

function Get-FieldLine($Output) {
    # the one line a hook printed (it also returns a bool, which is ignored)
    foreach ($item in @($Output)) {
        if ($item -is [string] -and $item.StartsWith('FIELD ', [StringComparison]::Ordinal)) { return $item }
    }
    return '(the shim printed no FIELD line)'
}

function Get-Verdict([string]$Line, [string]$Prefix) {
    if ($Line.StartsWith($Prefix, [StringComparison]::Ordinal)) { return $Line.Substring($Prefix.Length).TrimEnd() }
    return $null
}

# -Agent is compared case-sensitively everywhere below, but Get-FieldToken's
# JSON member lookup is not: SSL-INVOICING-AGENT would read the real agent's token.
if ($Agent -cnotmatch '\A[a-z0-9][a-z0-9._-]*\z') {
    Write-Output 'FAIL  -Agent is not a registry agent id (lowercase letters, digits, . _ -)'
    exit 2
}
if ($NewToken -cnotmatch '\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z') {
    Write-Output 'FAIL  -NewToken is not a lowercase uuid (value not shown)'
    exit 2
}
try {
    if (-not (Test-Path -LiteralPath $ShimPath -PathType Leaf)) {
        Write-Output "FAIL  shim not found: $ShimPath"
        exit 1
    }
    if ($script:PinTokensFile -and -not ($TokensFile -and (Test-Path -LiteralPath $TokensFile -PathType Leaf))) {
        Write-Output "FAIL  -TokensFile '$TokensFile' is not an existing file: shim not loaded, no call made"
        exit 1
    }
    . $ShimPath
    if ($script:PinTokensFile -and -not ($script:FieldTokens -ceq $TokensFile)) {
        Write-Output "FAIL  the shim reads its token file from '$script:FieldTokens', not -TokensFile '$TokensFile': no call made"
        exit 1
    }
    if ($script:FieldPosture -ne 'enforce') {
        Write-Output "FAIL  client posture is '$script:FieldPosture', not enforce: the skills would not stop on a BLOCK"
        exit 1
    }
    $want = $NewToken.Substring(0, 8)

    # 1. the token file, read by the shim's own function
    $ctx = @{ Held = $null }
    try { $ctx.Held = Get-FieldToken $Agent } catch { $ctx.Held = $null }
    $seen = 'nothing'
    if ($ctx.Held -is [string] -and $ctx.Held.Length -ge 8) { $seen = $ctx.Held.Substring(0, 8) }
    elseif ($null -ne $ctx.Held) { $seen = 'a malformed value' }
    Write-Check (($ctx.Held -is [string]) -and ($ctx.Held -ceq $NewToken)) "token file $script:FieldTokens holds $seen for $Agent (want $want)"

    # 2. heartbeat
    $line = Get-FieldLine (Get-FieldHeartbeat -Agent $Agent)
    Write-Check ($line.StartsWith("FIELD heartbeat $Agent killed=false ", [StringComparison]::Ordinal)) "heartbeat: $line"

    # 3. an in-scope action is allowed, not shadowed
    $line = Get-FieldLine (Invoke-FieldCheck -Agent $Agent -Action $InScopeAction)
    Write-Check ((Get-Verdict $line "FIELD check $Agent '$InScopeAction' -> ") -ceq 'ALLOW') "in scope: $line"

    # 4. a never-granted action is blocked on scope
    $line = Get-FieldLine (Invoke-FieldCheck -Agent $Agent -Action $script:Probe)
    Write-Check ((Get-Verdict $line "FIELD check $Agent '$script:Probe' -> ") -ceq 'BLOCK D.scope') "out of scope: $line"
} catch {
    # the message goes through the shim's redactor when the shim loaded; it is never
    # held in a named variable (the shim's own Set-PSDebug discipline)
    if (Get-Command Protect-FieldText -ErrorAction SilentlyContinue) {
        Write-Output ("FAIL  unexpected error ($($_.Exception.GetType().Name)): " + (Protect-FieldText $_.Exception.Message))
    } else {
        Write-Output "FAIL  unexpected error ($($_.Exception.GetType().Name)) before the shim loaded"
    }
    exit 1
}

if ($script:Fails -eq 0) {
    Write-Output 'RESULT PASS: 4 of 4 checks'
    exit 0
}
Write-Output "RESULT FAIL: $script:Fails of 4 checks failed"
exit 1
