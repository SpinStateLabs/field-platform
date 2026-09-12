# field-rest.ps1 — the three FIELD hooks over raw REST, for Claude skills that
# run on rog-command (Cowork / Claude Code) and cannot import the Python SDK.
#
#   . "C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform\tools\field-rest.ps1"
#   Get-FieldHeartbeat -Agent ssl-invoicing-agent                       # hook 3 LIVENESS (read)
#   Send-FieldCheckin  -Agent ssl-invoicing-agent                       # hook 3 LIVENESS (check-in)
#   Invoke-FieldCheck  -Agent ssl-invoicing-agent -Action "read timesheets"   # hook 1 ACTIONS
#   Send-FieldSpend    -Agent ssl-invoicing-agent -Actions 4 -Note "INV SSL-SA-2026-0906"  # hook 2 (actions-only)
#
# Every function prints ONE line beginning with "FIELD " that the skill quotes
# verbatim into its run report, and returns $true (proceed) / $false (stop).
#
# Posture (FIELD_CLIENT_POSTURE env, default enforce):
#   enforce  — the five rest-api.md rules: unreachable sentinel = BLOCK,
#              unreachable/non-200 heartbeat = killed, failed spend post =
#              unmetered = stop, killed=true for unknown agent = halt,
#              ESCALATE = a human has it (no retry).
#   log_only — same calls, same printed verdict, but always returns $true.
#              Only for a log_only estate; never pair log_only client with an
#              enforce estate.
#
# HONESTY: this is a cooperative perimeter. A skill run that skips these calls
# is not governed by them. Spend is metered as ACTIONS (cents=0) because no
# token count is observable from a Cowork session — dollar metering here would
# be an invented number.

$script:FieldProxy   = if ($env:FIELD_PROXY_URL) { $env:FIELD_PROXY_URL.TrimEnd('/') } else { 'http://10.0.0.62:18080' }
$script:FieldPosture = if ($env:FIELD_CLIENT_POSTURE) { $env:FIELD_CLIENT_POSTURE } else { 'enforce' }
$script:FieldTokens  = if ($env:FIELD_TOKENS_FILE) { $env:FIELD_TOKENS_FILE } else { Join-Path $HOME '.field-local\tokens-gb10.json' }
if (-not (Test-Path $script:FieldTokens) -and (Test-Path 'C:\Users\donal\.field-local\tokens-gb10.json')) {
    $script:FieldTokens = 'C:\Users\donal\.field-local\tokens-gb10.json'
}

function Get-FieldHeaders {
    $h = @{ 'content-type' = 'application/json' }
    if ($env:FIELD_SHARED_SECRET) { $h['x-field-auth'] = $env:FIELD_SHARED_SECRET }
    return $h
}

function Get-FieldToken([string]$Agent) {
    if (-not (Test-Path $script:FieldTokens)) { return $null }
    $t = Get-Content $script:FieldTokens -Raw | ConvertFrom-Json
    return $t.$Agent
}

function Get-FieldHeartbeat {
    param([Parameter(Mandatory)][string]$Agent)
    try {
        $r = Invoke-RestMethod -Uri "$script:FieldProxy/killswitch/heartbeat/$Agent" -Headers (Get-FieldHeaders) -TimeoutSec 8
        if ($r.killed) {
            Write-Output "FIELD heartbeat $Agent killed=true status=$($r.status) -> HALT"
            return ($script:FieldPosture -eq 'log_only')
        }
        Write-Output "FIELD heartbeat $Agent killed=false status=$($r.status) at=$($r.checked_at)"
        return $true
    } catch {
        Write-Output "FIELD heartbeat $Agent UNREACHABLE ($($_.Exception.Message)) -> liveness unknown = HALT"
        return ($script:FieldPosture -eq 'log_only')
    }
}

function Send-FieldCheckin {
    # Same verdict as Get-FieldHeartbeat, but POST: the kill-switch records
    # last_seen, so this agent stops reading stale on GET /liveness. Nothing
    # else in this shim writes that row — a skill that only calls
    # Get-FieldHeartbeat is invisible to the liveness report forever.
    param([Parameter(Mandatory)][string]$Agent)
    try {
        $r = Invoke-RestMethod -Uri "$script:FieldProxy/killswitch/heartbeat/$Agent" -Method Post -Headers (Get-FieldHeaders) -TimeoutSec 8
        if ($r.killed) {
            Write-Output "FIELD checkin $Agent killed=true status=$($r.status) -> HALT"
            return ($script:FieldPosture -eq 'log_only')
        }
        Write-Output "FIELD checkin $Agent killed=false status=$($r.status) last_seen=$($r.last_seen)"
        return $true
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 404 -or $code -eq 405) {
            # Pre-v1.2 estate: the route does not exist yet. That is NOT a
            # liveness verdict, so it must not halt the skill. This is exactly
            # why both ssl SKILL.md files call Get-FieldHeartbeat (hook 3a)
            # AND this (hook 3b): on today's estates the POST records nothing
            # and halts on nothing, so the GET is carrying hook 3 alone. Do
            # not "simplify" the skills down to this call.
            Write-Output "FIELD checkin $Agent NOT SUPPORTED ($code) -> estate predates v1.2 check-ins; liveness will read stale"
            return $true
        }
        Write-Output "FIELD checkin $Agent UNREACHABLE ($($_.Exception.Message)) -> liveness unknown = HALT"
        return ($script:FieldPosture -eq 'log_only')
    }
}

function Invoke-FieldCheck {
    param([Parameter(Mandatory)][string]$Agent,
          [Parameter(Mandatory)][string]$Action)
    $tok = Get-FieldToken $Agent
    if (-not $tok) {
        Write-Output "FIELD check $Agent '$Action' NO TOKEN ($script:FieldTokens) -> BLOCK (run tools/provision_ssl_agents.py)"
        return ($script:FieldPosture -eq 'log_only')
    }
    $body = @{ agent_id = $Agent; action = $Action; token_id = $tok } | ConvertTo-Json -Compress
    try {
        $v = Invoke-RestMethod -Uri "$script:FieldProxy/sentinel/check" -Method Post -Headers (Get-FieldHeaders) -Body $body -TimeoutSec 15
    } catch {
        Write-Output "FIELD check $Agent '$Action' UNREACHABLE ($($_.Exception.Message)) -> BLOCK (fail-closed)"
        return ($script:FieldPosture -eq 'log_only')
    }
    $clause = $v.clause_id
    if (-not $clause -and $v.context -and $v.context.would_be) { $clause = "shadow:" + $v.context.would_be.clause_id }
    Write-Output "FIELD check $Agent '$Action' -> $($v.decision) $clause"
    switch ($v.decision) {
        'ALLOW'    { return $true }
        'ESCALATE' { return ($script:FieldPosture -eq 'log_only') }   # a human has it; do not retry
        default    { return ($script:FieldPosture -eq 'log_only') }   # BLOCK
    }
}

function Send-FieldSpend {
    param([Parameter(Mandatory)][string]$Agent,
          [int]$Actions = 1,
          [int]$Cents = 0,
          [string]$Note = '')
    $body = @{ agent_id = $Agent; cents = $Cents; tokens = 0; actions = $Actions; note = $Note } | ConvertTo-Json -Compress
    try {
        $s = Invoke-RestMethod -Uri "$script:FieldProxy/governor/spend" -Method Post -Headers (Get-FieldHeaders) -Body $body -TimeoutSec 10
        Write-Output "FIELD spend $Agent actions=$Actions cents=$Cents -> $($s.state) spent=$($s.spent_cents)c of $($s.limit_cents)c $($s.detail)"
        return ($s.state -ne 'BLOCK') -or ($script:FieldPosture -eq 'log_only')
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 404) {
            Write-Output "FIELD spend $Agent NO CAP (404) -> unmetered = STOP (operator: governor set-cap)"
        } else {
            Write-Output "FIELD spend $Agent FAILED ($($_.Exception.Message)) -> unmetered = STOP"
        }
        return ($script:FieldPosture -eq 'log_only')
    }
}

Write-Output "FIELD shim loaded: estate=$script:FieldProxy posture=$script:FieldPosture tokens=$script:FieldTokens"
