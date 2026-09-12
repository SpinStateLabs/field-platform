---
name: invoicing-agent
description: "Read Spin State Labs client timesheets, summarize hours for approval, and generate/update client invoices (docx + pdf) and their presentation emails. Use for System Accountants (weekly) and ProvenScale (monthly) invoicing, or any new client added to the Customers folder invoicing workflow. Runs under the Force Field Protocol: FIELD-governed as agent ssl-invoicing-agent on the GB10 estate (heartbeat, sentinel check before every governed action, actions-only spend metering) and FORCE preset audit at runtime (zero LLM arithmetic on money)."
---

# Invoicing Agent

Generates and updates Spin State Labs' client invoices from timesheets, following the conventions in `Customers\CLAUDE.md`. This skill assumes a "Customers" folder with structure `Customers → Client → Partner → Project`, where Client is the invoiced entity, Partner is the delivery firm (may collapse with Client), and Project is where hours are tracked.

This skill also creates a ZOHO Books invoices.

## Governance — Force Field Protocol (read this before the workflow)

This skill IS the FIELD-governed agent **`ssl-invoicing-agent`**. Manifest: `field-platform/manifests/ssl-invoicing-agent.yaml` (estate copy `/data/manifests/ssl-invoicing-agent.yaml`). Estate: GB10, `http://10.0.0.62:18080` (Caddy path-routed: `/sentinel`, `/killswitch`, `/governor`, `/ledger`), sentinel mode **enforce**. Operator provisioning (registration, cap, token) is `field-platform/tools/provision_ssl_agents.py` — never run it from inside this skill; agents do not self-authorize.

**How the hooks are called** (from a Cowork/Claude Code session on rog-command, the Windows PowerShell tool; the cloud shell cannot reach the estate):

```powershell
. "C:\Users\donal\My Drive\Spin State Labs\Projects\FORCE-FIELD\field-platform\tools\field-rest.ps1"
Get-FieldHeartbeat -Agent ssl-invoicing-agent                                  # hook 3a — FIRST: the halt gate
Send-FieldCheckin  -Agent ssl-invoicing-agent                                  # hook 3b — records last_seen
Invoke-FieldCheck  -Agent ssl-invoicing-agent -Action "read timesheets"        # hook 1 — before EACH governed action
Send-FieldSpend    -Agent ssl-invoicing-agent -Actions <n> -Note "<invoice #>" # hook 2 — at the end of the run
```

Hook 3 is **two calls, and both are required.** `Get-FieldHeartbeat` (GET) is
the halt gate: it works on every estate and returns `$false` when the agent is
killed or the kill-switch is unreachable. `Send-FieldCheckin` (POST) is the
only call in the shim that writes `last_seen`, and without it this agent is
invisible to `GET /killswitch/liveness` forever — it reads stale from the day
it is provisioned.

They are not interchangeable. On an estate that predates v1.2 the POST route
does not exist, and the helper reports `NOT SUPPORTED (404|405)` and does
**not** halt — a missing route is not a liveness verdict. Both GB10 and Fly
run pre-v1.2 images today, so on those estates the check-in records nothing
and halts on nothing: the GET is carrying hook 3 by itself. Dropping it would
leave this agent with no pre-work liveness gate at all.

Each call prints one `FIELD …` line. **Quote every one of those lines verbatim in the run report** (a section titled `FIELD ledger lines`). A run report with no FIELD lines means the run was ungoverned — say so in the report; do not omit the section.

**Governed actions — use these exact strings** (they must match the manifest `delegation.scope` and the minted token; a typo is a `D.scope` BLOCK):

| Workflow step | `-Action` string |
|---|---|
| 1 Read the timesheet | `read timesheets` |
| 4 Verify the rate / read Customers\CLAUDE.md | `read customer profile` |
| 5 Generate the invoice docx/pdf | `draft invoice document` |
| 7 Enter into Zoho Books | `create zoho invoice` — declared **escalation trigger**: the sentinel answers ESCALATE every time; proceed only on the user's explicit in-chat approval (see verdict handling) |
| 8 Draft the presentation email | `draft invoice email` |

**Never granted (deliberately absent from scope — refuse, do not attempt):** `send invoice email`, `mark invoice sent`, `apply payment`. If the user asks for any of these, decline and say the manifest does not grant it.

**Verdict handling (posture `enforce`, matching the estate):** heartbeat `killed=true` or unreachable → stop before any work. `BLOCK` or sentinel unreachable → do not perform that action; report the clause; continue only with actions that were ALLOWed. `ESCALATE E.escalation_trigger` on `create zoho invoice` is the **expected** verdict (it is the declared trigger; the sentinel escalates every time, there is no approval token): stop, show the user the exact action about to be taken, proceed only after an explicit "yes" in chat, and record both the FIELD line and that approval in the run report. Any other `ESCALATE` (`E.spend_threshold`, `D.semantic`) → skip the action, tell the user a human must resolve it (`GET /governor/escalations`), never loop. Spend post `404`/failed → the run is unmetered; say so in the report.

**Honesty line (cooperative perimeter):** governance coverage equals instruction-following. A tool call made without a preceding `Invoke-FieldCheck` is not governed by FIELD; the estate's backstop is that a killed agent's next `/check` is BLOCK and tokens can be revoked. Spend is metered as **actions only** (`cents=0`) because a Cowork session exposes no token counts — dollar metering here would be an invented number. Enforced-vs-Declared table: `field-platform/agents/README.md`.

## FORCE runtime protocol (preset: audit — F, R, C, E always; O at decision points)

- **F** — No pleasantries. If the user states a rate, period, currency or client that contradicts the customer file, correct it in the first line.
- **O** — At each decision point (rate mismatch, open period requested, subtotal mismatch, unusual entry, new client with no profile) state the strongest objection before proceeding, then ask or proceed as the workflow says.
- **R** — Every figure cites its source: timesheet file + row/block, customer profile, spot-rate source and date. If a fact is not in those sources, write "not in source" — never infer a rate, address or contact.
- **C / zero LLM arithmetic** — Hours totals, line amounts, FX conversions, rounding and the invoice total are computed by a Python step (openpyxl / decimal) whose printed output you quote character-for-character. Never total hours or multiply hours × rate in prose. Show ASSUMPTIONS / REASONING / CONCLUSION for the period selection and the summary table.
- **E** — Tag non-trivial claims HIGH / MEDIUM / LOW. Financial figures on an invoice are HIGH only when quoted from the Python step and the post-write re-read (step 6); anything else is not put on an invoice.

Always re-read `Customers\CLAUDE.md` at the start of a session if available — it is the source of truth for folder paths and per-client rules and may have been updated since this skill was written. This skill's per-customer details below are a snapshot; CLAUDE.md wins on conflict.

## Core workflow (always follow this order)

1. **Read the timesheet.** FIELD: `Invoke-FieldCheck -Action "read timesheets"` first. Each client's hours live in a `Timesheet_SSL_<Partner>_YYYY-MMDD.xlsx` file (date = period end), one row per worked day, in blocks separated by a subtotal row (a row with two blank cells and a numeric subtotal in the Hours column). Use the per-row entries, not just the subtotal, to build invoice line items — but cross-check your sum against each block's subtotal row as a built-in consistency check.

2. **Determine the invoicing period** from the client's cadence (weekly or monthly — see per-customer section below). Only invoice *closed* periods (a week that has fully elapsed, or a month that has ended) unless the user explicitly asks to include the current/open period.

3. **Summarize before writing anything.** Present a table or list of period(s), dates worked, hours, and amount, and flag any anomalies (missing days, subtotal mismatches, unusually large entries) before generating invoice files. Wait for confirmation before proceeding if there is any ambiguity (which weeks to bill, whether to include the open week, currency assumptions). If the request is unambiguous and simply says "invoice X", it's fine to proceed straight through summary → invoice → email in one pass, but still show the summary in your final response.

4. (FIELD: `Invoke-FieldCheck -Action "read customer profile"` first.) **Verify the rate against the customer's own contract/profile, not against whatever figure the user states in the request.** Users mix up client rates between customers. If the user states a rate that doesn't match the customer's file, correct them before proceeding and use the correct contract rate.

5. **Generate the invoice** (FIELD: `Invoke-FieldCheck -Action "draft invoice document"` first) (docx, and pdf if requested — see "Producing the PDF" below) by cloning the most recent invoice for that same client as a template (preserves formatting, payment terms, and any currency-conversion note structure) and mutating: invoice number, invoice date, line items (date/hours/rate/amount), total, and any FX note. Do not build a new document from scratch if a prior invoice for that client exists — copy and mutate it.

6. **Verify.** After writing, re-open the generated file and print its extracted text to confirm the invoice number, dates, line items, total, total hours and payment terms are all correct. Never report an invoice as done without this verification step.

7. **Enter into Zoho books.** Using the verified text from step 6 (invoice number, dates, line items, total, payment terms), create or update the Zoho Invoice. Never report a Zoho invoice as done without that verification step. FIELD: `Invoke-FieldCheck -Action "create zoho invoice"` first — this is the declared escalation trigger — ESCALATE is expected; proceed only after the user's explicit in-chat approval of this exact invoice, and record it.

8 .**Draft the presentation email as plain text in the chat response** (FIELD: `Invoke-FieldCheck -Action "draft invoice email"` first; then `Send-FieldSpend` with the count of governed actions this run) (see "Email drafting" below) — do not create a Gmail (or other) draft unless the user explicitly asks for that.

## Numbering & filenames

- Customer codes: Spin State Labs = `SSL`. Each invoiced client gets its own short code (e.g. ProvenScale = `PS`, SystemsAccountants = `SA`). When onboarding a new client, ask for or assign a code and record it.
- Invoice number: `SSL-<CODE>-YYYY-MMDD` (date = period end).
- Filename: `Invoice_SSL-<CODE>_YYYY-MMDD.docx` / `.pdf`.
- Timesheet filename: `Timesheet_SSL_<Partner>_YYYY-MMDD.xlsx` (date = period end).

## Payment terms (standard block for all invoices, all clients, unless a client requires something different)

```
Interac e-Transfer to don@spinstatelabs.ca.
Bank transfer (EFT): Equitable Bank (EQ Bank), Institution No. 623, Transit No. 80003, Account No. 400155542. Beneficiary: Spin State Labs Inc.
```

Never include a personal gmail address on an invoice's payment line — only the spinstatelabs.ca address.

## Per-customer invoicing profiles

Keep one dedicated fact block per customer (in this skill, and/or in memory) covering: contract rate, invoicing currency, cadence, billing address, and billing contact/email. Known customers as of this writing:

**ProvenScale** — contract rate USD 120.00/hour (never changes). **Always invoiced in CAD** — this is a standing customer preference, not a one-off. Convert line amounts and the total/Amount-due from USD to CAD at the current USD/CAD spot rate at time of invoicing (look it up; don't reuse a stale rate). Do NOT convert the Rate column — it stays USD 120.00. Round each line to the cent; the total is the sum of the rounded lines (not a straight recompute from the USD total, to avoid rounding drift). Add a `**` footnote at the bottom of the invoice stating the spot rate, its date, and the calculation. Cadence: monthly, invoice dated at period end. Billing contact: kevin@provenscale.com. Billing address: ProvenScale, 125 Half Mile Rd, Suite 200, Red Bank, NJ 07701.

**SystemsAccountants** (partner: Sikich) — contract rate USD 110.00/hour. **Always invoiced in USD** — no currency conversion, unlike ProvenScale. Do not cross-apply ProvenScale's CAD conversion habit here. Cadence: weekly (Mon–Sun), invoice dated at period-end Sunday, one line per worked day. Billing address: SystemsAccountants, Inc., 159 N. Sangamon Street, Suite 200 & 300, Chicago, IL 60607. Contracts/notices contact: contractsadministration@systemsaccountants.com.

When a new client is added, add its own profile block here (or in memory) with the same fields: rate, currency rule, cadence, address, contact. Never assume a new client follows either existing pattern by default — ask if unclear.

## Producing the PDF

If Microsoft Word is available on the machine (check via COM automation, e.g. `New-Object -ComObject Word.Application` in PowerShell), generate the PDF by opening the finished docx and using `SaveAs` with the PDF format (format code 17), then closing Word. This produces a clean, accurately-formatted PDF from the real document rather than a re-implementation. Only fall back to other PDF-generation approaches if Word/COM automation is unavailable.

## Email drafting

Default to giving the user the email as plain text in the chat response (subject + body), so they can copy it into whatever client they use. Only call an email-draft-creation tool (e.g. Gmail's create_draft) if the user explicitly asks you to create/save a draft — this was previously a point of friction where drafts were created unprompted.

Standard structure for an invoicing email: greeting, one line naming the engagement/period, a short summary block (invoice #, period, hours, rate, amount due — including the FX note detail if applicable), the payment terms block, a mention that the itemized timesheet is attached, and a sign-off. Match the recipient found in the client's contract/notices clause, not a guess.

## Common mistakes to avoid

- Don't mix up rates between customers (110 vs 120) — always check the specific customer's contract rate.
- Don't apply one customer's currency-conversion habit to another customer.
- Don't invoice an open/in-progress period unless asked.
- Don't skip the post-write verification re-read.
- Don't create email drafts in an email client unless explicitly asked — default to plain text in chat.
- Don't build invoices from scratch when a prior invoice for the same client can be cloned and mutated — this preserves formatting and reduces errors.
- Don't run any governed action without its `Invoke-FieldCheck`, and don't omit the `FIELD ledger lines` section from the run report.
- Don't do money arithmetic in prose — quote the Python step.