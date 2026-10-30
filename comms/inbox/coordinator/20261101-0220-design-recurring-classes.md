# Design note: other classes reviewers found more than once (Lane 10)

Source: titles and lines grepped from comms/inbox/coordinator (376 files at the time); I read the matching lines, not every report. Confidence MEDIUM throughout; cite files before turning any item into a card.

## A. Network address spelling (private-host test)
Reports: 20261029-3400-reviewer-c197-pr96.md, 20261029-3700 and 3800 reviewer-c213-*.md (hex, octal, decimal and short IPv4 spellings; 0.0.0.0/8 treated as private; a single-label host with a space). Same shape as the bind checker: a list of spellings fixed one at a time.
Invariant: a host is "private" only if it is a literal IPv4 or IPv6 address in the RFC 1918/loopback ranges after ONE canonical parse (`ipaddress`), or a name in an explicit allow list; anything that does not parse is public. Fix: drop the hand-written spelling handling; refuse any host that `ipaddress.ip_address()` cannot parse, and any `0.0.0.0/8`; then names are refused unless allow-listed. Probe: the reports' own spellings.

## B. Environment proxy in a secret-carrying client
Reports: 20261028-1245-reviewer-c41-*.md, 20261028-1345-reviewer-c55-env-proxy-class-sweep.md, later c43/c64/c81. Pattern: every new httpx client re-creates the omission (C-187 F-C187-2 found it again on three more callers).
Invariant: any client that carries a credential sets `trust_env=False` and no proxy. Fix: one factory in field-core, and a test that greps for `httpx.Client(` / `AsyncClient(` outside the factory (class closed by construction, not by review).

## C. Error text echoes a body or a value
Reports: 20261028-1215-reviewer-c40-*.md (registry body in an error), 20261028-1600-reviewer-c64-c65 (the same in another service), 20261030-2200-reviewer-c376-pr223.md (a flag value echoed up to 40 characters), later c382 and c396.
Invariant: an error message names a fixed string and a status code, never the response body, the flag value or a header. Fix: one helper for building such messages, and a grep-based test over `raise ...(f"...{resp.text}...")` and `{os.environ.get(...)}`.

## D. Credential sent on reads as well as writes
Reports: 20261028-2330-reviewer-c91-*.md (a service's operator pair rides every request, "same class as C-41 finding 5"), plus the console (see the key note, channel 13).
Invariant: a credential is attached only to the request kinds that need it. Fix: the client takes a per-call `auth=` and the default is none; test: GET requests carry no operator header.

## E. "One step further out" (all lists)
The pattern in the reports for C-424, C-434 and C-441 is one cause. Rule for any new checker: derive the forbidden set from an invariant and prefer an allowlist; if a denylist is unavoidable, the card must include an enumeration probe (as probe1.py does) with every spelling named, before the fix.

## What I did NOT do
Did not open the reports' probes or rerun them. Did not rank these by severity. Did not verify that classes B and D are still open on main. Could not push.
