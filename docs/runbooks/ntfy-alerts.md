# ntfy push alerts (K10)

Alert channel K10 is ntfy (Don's decision P36 item 3). What exists on main
today is the library (`field_core.alerts`,
`packages/field-core/src/field_core/alerts.py`) and one sender, the command
`field alert-test` (`packages/field-core/src/field_core/cli.py:150-166`). The
platform does NOT yet send alerts for key-rotation failures, overdue rotations,
break-glass use or Phase G stage transitions: the six production classes below
are defined (`alerts.py:127-160`) and have no caller outside the tests, and no
service merges `health_fields()` into its `GET /health` for them (a
repository-wide search of the Python sources on main finds the senders and the
merge only in the library, the CLI and the tests). The senders are deferred
until the key-rotation work (PR 57) is reworked (card C-760). The tests are
`packages/field-core/tests/test_alerts_ntfy.py`.

P36 makes stage gates automatic, with one condition: alerts are live and a test
alert has been proven to reach Don BEFORE the first automatic arming. The
end-to-end test in design section 5.3 (the rotator forced to fail on the GB10)
is a separate check, and this runbook does not replace it.

## 1. BOOTSTRAP (the one human step)

Do this once. It is the only step that needs a person. Everything after it is
automatic.

1. The controller writes a new, unguessable topic on Don's PC. The topic is
   never printed:

   ```
   field alert-topic-init --out <home>/.field-local/ntfy-topic.txt
   ```

   The topic is `field-` plus 192 random bits (url-safe, 38 characters). The
   command refuses to overwrite an existing file unless `--force` is given.
   Replacing the topic means Don subscribes again.
2. **Don installs the ntfy app.** Android: Google Play, F-Droid, or the GitHub
   APKs. iPhone: the App Store.
3. **Don subscribes to the topic.** Open
   `<home>/.field-local/ntfy-topic.txt` on the PC, then add that topic
   in the app on the default server `ntfy.sh` (or the self-hosted server, if
   one is used). On Android, the link `ntfy://ntfy.sh/<topic>` opens the app
   and subscribes. On Android, turn on "instant delivery" for the
   subscription. Without it, delivery through Firebase can be minutes or hours
   late.
4. Each sending host gets a copy of the same file and points
   `FIELD_NTFY_TOPIC_FILE` at it. The controller runs
   `field alert-test --estate <name>` on that host (`--estate gb10`,
   `--estate fly`). Always pass `--estate`: the default is the host name, and
   a Docker container ID or a Fly machine ID is hex, which the content check
   withholds. The step is done when the TEST alert shows up on Don's phone.
   Until then, the P36 automatic-arming condition is NOT met.

Do not paste the topic into chat, a ticket, a commit, a ledger row or a
command line. Anyone who has the topic can read and send alerts on it, unless
a token-protected (reserved) topic is used (section 4).

## 2. Configuration (sending hosts)

| Variable | Meaning |
|---|---|
| `FIELD_NTFY_TOPIC_FILE` | Path to a file holding a bare topic or a full topic URL (`https://ntfy.sh/<topic>`, or self-hosted `https://ntfy.example.org[/prefix]/<topic>`). When set, it is the ONLY source. If the file cannot be used, the env value below is NOT used as a fallback. |
| `FIELD_NTFY_TOPIC` | The same content inline. Used only when no file is set. |
| `FIELD_NTFY_BASE_URL` | The server for a bare topic. Default `https://ntfy.sh`. Ignored when the content is a full URL. |
| `FIELD_NTFY_TOKEN_FILE` / `FIELD_NTFY_TOKEN` | Optional ntfy access token, sent as `Authorization: Bearer <token>`. The file wins over the env value. |

Blank values count as unset. Only `https` is accepted, except plain `http` to
a loopback host. User info, query strings and fragments are refused, and so is
a topic outside `[A-Za-z0-9_-]{1,64}`. Without a token, a topic shorter than 20
characters is refused as guessable (`topic_guessable`). The topic is never
taken from a command line, and it never appears in a log, a result, `/health`
or a ledger row. The module writes no ledger rows. Redirects are never
followed.

## 3. Alert classes, delivery and failure reporting

| Class | ntfy priority | Tags | Sent by |
|---|---|---|---|
| `rotation_failed` | 5 (max) | rotating_light, key, field | planned: rotator (`keyrotation.failed`); no sender on main (C-760) |
| `rotation_overdue` | 4 (high) | warning, hourglass, field | planned: dead-man check (design 5.3); no sender on main (C-760) |
| `breakglass_used` | 5 (max) | sos, rotating_light, field | planned: break-glass observer (use or attempt); no sender on main (C-760) |
| `stage_transition` | 4 (high) | arrow_right, field | planned: Phase G stage controller (one per step, P36); no sender on main (C-760) |
| `stage_aborted` | 5 (max) | rotating_light, rewind, field | planned: Phase G stage controller, a stage aborted and rolled back (P36: automatic rollback on any abort condition); no sender on main (C-760) |
| `rotation_halted` | 5 (max) | sos, key, field | planned: rotator, stopped after repeated faults, will not retry by itself, key may near expiry (reviewer C-22, D-5); no sender on main (C-760) |
| `test` | 3 (default) | test_tube, test, field | `field alert-test` |

The test alert's title is `FIELD TEST ALERT - no action needed`. Its body
starts with `This is a TEST alert`, and it carries a 6-hex test id so a
receipt can be matched to one run.

**Content.** Each alert is a fixed per-class template plus a few caller
fields: `estate`, `subject`, `detail`. A field is replaced by
`(withheld: failed content check)` and counted (`alerts_content_withheld`)
when any of these hold:

- it falls outside its charset;
- it contains `fok_` or `tk_`;
- it contains a run of 12 or more hex digits (a hash or a 16-hex
  fingerprint);
- it contains a 32-character or longer opaque token run;
- it contains a PEM header;
- it contains the configured topic or token.

The alert is still sent with the field withheld. The rendered title, body and
tags are checked once more before sending. The test
`test_content_carries_no_secret_key_token_hash_or_topic` proves the rule. One
side effect: a 12-digit or longer decimal number counts as a hex run and is
withheld.

**Delivery.** One `POST` to the topic URL with `Title`, `Priority` and `Tags`
headers. Each attempt has a wall-clock deadline (default 5 s, capped at 30 s)
that covers the name lookup, the connection, TLS and the response status
line; the response body is never read. A server that trickles bytes cannot
stretch an attempt past its deadline. Delivery
makes at most 3 attempts by default (capped at 5), with 1 s and then 2 s of
back-off between them. Retries happen on a timeout, a network error, 429 or
5xx, and on no other status.

**Failures are never silent.** Each failure:

- is counted per process: `alerts_failed`, `alerts_last_failure_reason`,
  `alerts_last_failure_class`, `alerts_last_failure_at`;
- is logged as one ERROR line naming the class and a fixed reason
  (`not_configured`, `topic_invalid`, `url_invalid`, `timeout`, `network`,
  `http_<status>`, `error`, ...).

A long-lived caller is meant to merge `field_core.alerts.health_fields()` into
its `GET /health` (`alerts.py:235`); no service does so on main yet. A script caller checks the returned `AlertResult` and exits
non-zero. `field alert-test` exits 0 when the alert was delivered, 1 when it
was not, and 2 when the configuration is missing or unusable (no topic, an
unreadable file, an invalid or guessable topic, an invalid URL or token);
exit 2 means nothing was sent.

## 4. Recommendations

- **Unguessable topic (default).** Use `field alert-topic-init`. ntfy's docs
  say that, with no sign-up, "the topic is essentially a password". Messages
  should therefore be content-free, which the content rule enforces.
- **Access token (optional, stronger).** If Don has an ntfy.sh account and a
  reserved topic, create an access token for publishing. Place it on each
  sending host as `FIELD_NTFY_TOKEN_FILE`, and log in to the app on the phone
  so it can subscribe. A short readable topic is then allowed. See section 5
  for what is unverified here.
- **Self-hosted.** Set `FIELD_NTFY_BASE_URL` (or put a full URL in the topic
  file) and use ACLs with a token. iPhone delivery from a self-hosted server
  is not covered by the pages cited below (UNVERIFIED).

## 5. Verified against ntfy's official docs, and not

Read on 2026-10-28:

- Publish by HTTP PUT/POST to the topic URL, with the message as the body:
  <https://docs.ntfy.sh/publish/#publishing>. VERIFIED (docs).
- Title header `X-Title` (alias `Title`): <https://docs.ntfy.sh/publish/#message-title>.
  VERIFIED (docs).
- Priority header `X-Priority` (alias `Priority`). The values are 1 min,
  2 low, 3 default, 4 high and 5 max/urgent, and 4 and 5 give a pop-over
  notification: <https://docs.ntfy.sh/publish/#message-priority>.
  VERIFIED (docs).
- Tags header `X-Tags` (alias `Tags`), comma-separated, with emoji short codes
  shown as emoji: <https://docs.ntfy.sh/publish/#tags-emojis>.
  VERIFIED (docs). That `arrow_right`, `test_tube`, `hourglass`, `sos`, `key`
  and `rotating_light` are in ntfy's emoji list is UNVERIFIED. An unknown short
  code is shown as a plain text tag.
- Topic names allow letters, numbers, underscores and dashes, up to 64
  characters, and "the topic is essentially a password":
  <https://docs.ntfy.sh/publish/#picking-a-topic>. VERIFIED (docs).
- "all topics on ntfy.sh are public": <https://docs.ntfy.sh/publish/#public-topics>.
  VERIFIED (docs).
- Access tokens are sent as `Authorization: Bearer tk_...`. They are created
  with `ntfy token` or in the web app's "Account" section when logged in:
  <https://docs.ntfy.sh/publish/#access-tokens>. VERIFIED (docs). Whether a
  free ntfy.sh account can reserve a topic so that only token holders may
  publish or read is UNVERIFIED: the pricing and plan pages were not checked.
- Limits: messages up to 4,096 bytes; a burst of 60 requests per visitor, then
  one request every 5 s; on ntfy.sh, 250 messages a day on the free tier:
  <https://docs.ntfy.sh/publish/#limitations>. VERIFIED (docs). FIELD bodies
  are capped at 1,024 bytes.
- Server logs "do contain topic names and IP addresses", and messages are also
  sent to Firebase Cloud Messaging:
  <https://docs.ntfy.sh/faq/#will-you-know-what-topics-exist-can-you-spy-on-me>
  and <https://docs.ntfy.sh/faq/#is-firebase-used>. VERIFIED (docs). This is
  why alert content is kept free of secrets.
- Apps: Android from Google Play, F-Droid or GitHub; iOS from the App Store.
  `ntfy://<host>/<topic>` links open the Android app and subscribe. Instant
  delivery avoids Firebase delays: <https://docs.ntfy.sh/subscribe/phone/>.
  VERIFIED (docs). An iOS equivalent of `ntfy://` links is UNVERIFIED.
- NOT verified anywhere: a real delivery to ntfy.sh or to Don's phone. No test
  touches the network; every test uses a local fake ntfy server. The first
  real delivery is BOOTSTRAP step 4.
