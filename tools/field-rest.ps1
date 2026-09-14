# field-rest.ps1 — the three FIELD hooks over raw REST, for Claude skills that
# run on rog-command (Cowork / Claude Code) and cannot import the Python SDK.
#
#   . "C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform\tools\field-rest.ps1"
#   Get-FieldHeartbeat -Agent ssl-invoicing-agent                       # hook 3 LIVENESS (read)
#   Send-FieldCheckin  -Agent ssl-invoicing-agent                       # hook 3 LIVENESS (check-in)
#   Invoke-FieldCheck  -Agent ssl-invoicing-agent -Action "read timesheets"   # hook 1 ACTIONS
#   Send-FieldSpend    -Agent ssl-invoicing-agent -Cents 1250 -Note "INV SSL-SA-2026-0906"  # hook 2 (cents only)
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
# is not governed by them. ACTIONS are counted by the sentinel: since v1.2 D1
# every Invoke-FieldCheck ALLOW is metered to the governor as one action, so
# hook 2 posts CENTS ONLY (option B; -Actions defaults to 0) and is skipped when
# no real cents figure exists — no token count is observable from a Cowork
# session, and dollar metering here would be an invented number. -Actions N
# still posts N self-reported actions (a pre-D1 estate has no sentinel meter);
# on a D1 estate an unattributed self-reported count adds to the metered one.
# -Action NAME attributes the row to one action; it is sent only when set,
# because a pre-D1 governor refuses the key (422 -> FAILED -> STOP). A
# THROTTLED reply is a valid state (the spend was recorded; the rate window is
# the sentinel's gate, not this hook's): it prints retry_after and proceeds.
#
# SECRET (x-field-auth). $env:FIELD_SHARED_SECRET when it is set; otherwise the
# file C:\Users\donal\.field-local\gb10-estate-secret ($env:FIELD_SECRET_FILE
# overrides the path), trimmed. Read per request, so a secret placed later is
# honoured without re-loading the shim. A missing or empty file means no header
# (an open estate answers; a perimeter estate answers 401 = HALT). A value with
# whitespace, control or non-ASCII characters is refused, never sent: the shim
# loads with one "malformed" line that does not contain it. The value is never
# printed: each hook reads the secret state ONCE per request, builds its header
# from it, and passes EVERY line it prints (server-returned fields and error
# messages alike) through Protect-FieldText with that same state, so an upstream
# that reflects the header is redacted. The value and every server response are
# held only as hashtable members, never in a named variable, so
# Set-PSDebug -Trace 2 (which prints "! SET $name = value") does not print them.
# The secret is a perimeter, not an identity.
#
# TOKEN FILE ($script:FieldTokens, resolved once at load). When FIELD_TOKENS_FILE
# is set, that path and ONLY that path: a file that does not exist means no
# token (Invoke-FieldCheck prints NO TOKEN and blocks), never another file. A
# mistyped or test path used to be silently replaced by the real rog-command
# token file, whose token then went to whatever FIELD_PROXY_URL named. Only when
# FIELD_TOKENS_FILE is unset: the default under $HOME, and the rog-command path
# when that default does not exist.

$script:FieldProxy   = if ($env:FIELD_PROXY_URL) { $env:FIELD_PROXY_URL.TrimEnd('/') } else { 'http://10.0.0.62:18080' }
$script:FieldPosture = if ($env:FIELD_CLIENT_POSTURE) { $env:FIELD_CLIENT_POSTURE } else { 'enforce' }
if ($env:FIELD_TOKENS_FILE) {
    $script:FieldTokens = $env:FIELD_TOKENS_FILE
} else {
    $script:FieldTokens = Join-Path $HOME '.field-local\tokens-gb10.json'
    if (-not (Test-Path $script:FieldTokens) -and (Test-Path 'C:\Users\donal\.field-local\tokens-gb10.json')) {
        $script:FieldTokens = 'C:\Users\donal\.field-local\tokens-gb10.json'
    }
}

function Get-FieldSecretFilePath {
    if ($env:FIELD_SECRET_FILE) { return $env:FIELD_SECRET_FILE }
    return 'C:\Users\donal\.field-local\gb10-estate-secret'
}

function Test-FieldSecretValue([string]$Value) {
    # Printable ASCII with no space, start to end. \z, not $: in .NET regex $
    # also matches before a final newline, which would let "secret`n" through.
    return ($Value -cmatch '\A[\x21-\x7E]+\z')
}

function Get-FieldSecretState {
    # @{ Value = the secret or $null; Source = env | file | none |
    #    env-malformed | file-malformed | file-unreadable }.
    # Silent by design: it is called inside -Headers (...), where any output
    # would corrupt the header table. It never writes the value anywhere.
    # The value lives ONLY in the returned hashtable's Value member: a named
    # variable holding it would be printed by Set-PSDebug -Trace 2.
    if ($env:FIELD_SHARED_SECRET) {
        if (Test-FieldSecretValue $env:FIELD_SHARED_SECRET) {
            return @{ Value = $env:FIELD_SHARED_SECRET; Source = 'env' }
        }
        return @{ Value = $null; Source = 'env-malformed' }
    }
    $path = Get-FieldSecretFilePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return @{ Value = $null; Source = 'none' }
    }
    $state = @{ Value = $null; Source = 'none' }
    try {
        # ReadAllText honours a UTF-8/UTF-16/UTF-32 BOM (UTF-8 otherwise) and
        # returns "" for an empty file. Never throw from here: this runs inside
        # every hook's try block.
        $state.Value = ([IO.File]::ReadAllText((Resolve-Path -LiteralPath $path -ErrorAction Stop).ProviderPath)).Trim()
    } catch {
        return @{ Value = $null; Source = 'file-unreadable' }
    }
    if (-not $state.Value) { return @{ Value = $null; Source = 'none' } }
    if (-not (Test-FieldSecretValue $state.Value)) {
        return @{ Value = $null; Source = 'file-malformed' }
    }
    $state.Source = 'file'
    return $state
}

function Protect-FieldText([string]$Text, $Auth = $null) {
    # Redacts the secret from a line about to be printed. Hooks pass the SAME
    # state they built their header from ($Auth), so nothing is re-read; with
    # no $Auth the state is read once here (for callers outside the hooks).
    if ($null -eq $Auth) { $Auth = Get-FieldSecretState }
    if ($Auth.Value -and $Text) { return $Text.Replace($Auth.Value, '<redacted>') }
    return $Text
}

function Write-FieldLine($Auth, [string]$Line) {
    # The ONLY way a hook prints: every line, including fields a server
    # returned and exception messages, is redacted with the request's state.
    Write-Output (Protect-FieldText $Line $Auth)
}

function Get-FieldHeaders([Parameter(Mandatory)]$Auth) {
    # $Auth = the request's Get-FieldSecretState result: the header and the
    # redaction of everything the request prints use the SAME value.
    $h = @{ 'content-type' = 'application/json' }
    if ($Auth.Value) { $h['x-field-auth'] = $Auth.Value }
    return $h
}

function Get-FieldToken([string]$Agent) {
    if (-not (Test-Path $script:FieldTokens)) { return $null }
    $t = Get-Content $script:FieldTokens -Raw | ConvertFrom-Json
    return $t.$Agent
}

function Get-FieldHeartbeat {
    param([Parameter(Mandatory)][string]$Agent)
    $ctx = @{ Auth = (Get-FieldSecretState) }
    try {
        $ctx.R = Invoke-RestMethod -Uri "$script:FieldProxy/killswitch/heartbeat/$Agent" -Headers (Get-FieldHeaders $ctx.Auth) -TimeoutSec 8
        if ($ctx.R.killed -isnot [bool]) {
            # a 200 that is not a heartbeat verdict (an HTML page, text, bad
            # JSON, a JSON body without a boolean `killed`) is NOT "alive"
            Write-FieldLine $ctx.Auth "FIELD heartbeat $Agent MALFORMED reply (no boolean killed) -> liveness unknown = HALT"
            return ($script:FieldPosture -eq 'log_only')
        }
        if ($ctx.R.killed) {
            Write-FieldLine $ctx.Auth "FIELD heartbeat $Agent killed=true status=$($ctx.R.status) -> HALT"
            return ($script:FieldPosture -eq 'log_only')
        }
        Write-FieldLine $ctx.Auth "FIELD heartbeat $Agent killed=false status=$($ctx.R.status) at=$($ctx.R.checked_at)"
        return $true
    } catch {
        Write-FieldLine $ctx.Auth "FIELD heartbeat $Agent UNREACHABLE ($($_.Exception.Message)) -> liveness unknown = HALT"
        return ($script:FieldPosture -eq 'log_only')
    }
}

function Send-FieldCheckin {
    # Same verdict as Get-FieldHeartbeat, but POST: the kill-switch records
    # last_seen, so this agent stops reading stale on GET /liveness. Nothing
    # else in this shim writes that row — a skill that only calls
    # Get-FieldHeartbeat is invisible to the liveness report forever.
    param([Parameter(Mandatory)][string]$Agent)
    $ctx = @{ Auth = (Get-FieldSecretState) }
    try {
        $ctx.R = Invoke-RestMethod -Uri "$script:FieldProxy/killswitch/heartbeat/$Agent" -Method Post -Headers (Get-FieldHeaders $ctx.Auth) -TimeoutSec 8
        if ($ctx.R.killed -isnot [bool]) {
            Write-FieldLine $ctx.Auth "FIELD checkin $Agent MALFORMED reply (no boolean killed) -> liveness unknown = HALT"
            return ($script:FieldPosture -eq 'log_only')
        }
        if ($ctx.R.killed) {
            Write-FieldLine $ctx.Auth "FIELD checkin $Agent killed=true status=$($ctx.R.status) -> HALT"
            return ($script:FieldPosture -eq 'log_only')
        }
        Write-FieldLine $ctx.Auth "FIELD checkin $Agent killed=false status=$($ctx.R.status) last_seen=$($ctx.R.last_seen)"
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
            Write-FieldLine $ctx.Auth "FIELD checkin $Agent NOT SUPPORTED ($code) -> estate predates v1.2 check-ins; liveness will read stale"
            return $true
        }
        Write-FieldLine $ctx.Auth "FIELD checkin $Agent UNREACHABLE ($($_.Exception.Message)) -> liveness unknown = HALT"
        return ($script:FieldPosture -eq 'log_only')
    }
}

function Invoke-FieldCheck {
    param([Parameter(Mandatory)][string]$Agent,
          [Parameter(Mandatory)][string]$Action)
    $ctx = @{ Auth = (Get-FieldSecretState) }
    $tok = Get-FieldToken $Agent
    if (-not $tok) {
        Write-FieldLine $ctx.Auth "FIELD check $Agent '$Action' NO TOKEN ($script:FieldTokens) -> BLOCK (run tools/provision_ssl_agents.py)"
        return ($script:FieldPosture -eq 'log_only')
    }
    $body = @{ agent_id = $Agent; action = $Action; token_id = $tok } | ConvertTo-Json -Compress
    try {
        $ctx.V = Invoke-RestMethod -Uri "$script:FieldProxy/sentinel/check" -Method Post -Headers (Get-FieldHeaders $ctx.Auth) -Body $body -TimeoutSec 15
    } catch {
        Write-FieldLine $ctx.Auth "FIELD check $Agent '$Action' UNREACHABLE ($($_.Exception.Message)) -> BLOCK (fail-closed)"
        return ($script:FieldPosture -eq 'log_only')
    }
    $ctx.Clause = $ctx.V.clause_id
    if (-not $ctx.Clause -and $ctx.V.context -and $ctx.V.context.would_be) { $ctx.Clause = "shadow:" + $ctx.V.context.would_be.clause_id }
    Write-FieldLine $ctx.Auth "FIELD check $Agent '$Action' -> $($ctx.V.decision) $($ctx.Clause)"
    switch ($ctx.V.decision) {
        'ALLOW'    { return $true }
        'ESCALATE' { return ($script:FieldPosture -eq 'log_only') }   # a human has it; do not retry
        default    { return ($script:FieldPosture -eq 'log_only') }   # BLOCK
    }
}

function Send-FieldSpend {
    param([Parameter(Mandatory)][string]$Agent,
          [int]$Actions = 0,
          [int]$Cents = 0,
          [string]$Note = '',
          [string]$Action = '')
    $ctx = @{ Auth = (Get-FieldSecretState) }
    $payload = @{ agent_id = $Agent; cents = $Cents; tokens = 0; actions = $Actions; note = $Note }
    if ($Action) { $payload['action'] = $Action }   # only when set: a pre-D1 governor 422s the key
    $body = $payload | ConvertTo-Json -Compress
    try {
        $ctx.S = Invoke-RestMethod -Uri "$script:FieldProxy/governor/spend" -Method Post -Headers (Get-FieldHeaders $ctx.Auth) -Body $body -TimeoutSec 10
        if (@('OK', 'ESCALATE', 'THROTTLED', 'BLOCK') -cnotcontains $ctx.S.state) {
            Write-FieldLine $ctx.Auth "FIELD spend $Agent MALFORMED reply (no OK/ESCALATE/BLOCK state) -> unmetered = STOP"
            return ($script:FieldPosture -eq 'log_only')
        }
        $ctx.Tail = if ($ctx.S.state -ceq 'THROTTLED') { " retry_after=$($ctx.S.retry_after_seconds)" } else { '' }
        $ctx.Named = if ($Action) { " action='$Action'" } else { '' }
        Write-FieldLine $ctx.Auth "FIELD spend $Agent actions=$Actions cents=$Cents$($ctx.Named) -> $($ctx.S.state) spent=$($ctx.S.spent_cents)c of $($ctx.S.limit_cents)c $($ctx.S.detail)$($ctx.Tail)"
        return ($ctx.S.state -ne 'BLOCK') -or ($script:FieldPosture -eq 'log_only')
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 404) {
            Write-FieldLine $ctx.Auth "FIELD spend $Agent NO CAP (404) -> unmetered = STOP (operator: governor set-cap)"
        } else {
            Write-FieldLine $ctx.Auth "FIELD spend $Agent FAILED ($($_.Exception.Message)) -> unmetered = STOP"
        }
        return ($script:FieldPosture -eq 'log_only')
    }
}

$script:FieldAuth = (Get-FieldSecretState).Source
switch ($script:FieldAuth) {
    'env-malformed'   { Write-Output "FIELD shim FIELD_SHARED_SECRET is malformed (whitespace, control or non-ASCII characters) -> no x-field-auth header will be sent (value not shown)" }
    'file-malformed'  { Write-Output "FIELD shim secret file $(Get-FieldSecretFilePath) is malformed (whitespace, control or non-ASCII characters) -> no x-field-auth header will be sent (value not shown)" }
    'file-unreadable' { Write-Output "FIELD shim secret file $(Get-FieldSecretFilePath) is unreadable -> no x-field-auth header will be sent" }
}
Write-Output "FIELD shim loaded: estate=$script:FieldProxy posture=$script:FieldPosture tokens=$script:FieldTokens auth=$script:FieldAuth"
