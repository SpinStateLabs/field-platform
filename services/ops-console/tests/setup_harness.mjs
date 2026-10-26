// Behavioural harness for the ops-console Setup area: loads the real console.html in jsdom with a fake
// same-origin fetch (a stub estate), drives a scenario, prints one JSON result for pytest to assert on.
// usage: node setup_harness.mjs <jsdom-install-dir> <console.html> <scenario>
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";

const [, , jsdomDir, htmlPath, scenario] = process.argv;
const require = createRequire(path.join(jsdomDir, "noop.js"));
const { JSDOM, VirtualConsole } = require("jsdom");
const HTML = readFileSync(htmlPath, "utf-8");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const KEY = "SECRETKEY-abc123";

async function boot(opts = {}) {
  const calls = [];
  const errors = [];
  const ctx = { confirm: true, delay: 0, handler: null, ...opts };
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push(String(e && e.message)));
  const fetchStub = async (p, o = {}) => {
    const headers = {};
    for (const [k, v] of Object.entries(o.headers || {})) headers[k.toLowerCase()] = v;
    const call = { path: String(p), method: (o.method || "GET").toUpperCase(), headers, body: o.body || null };
    calls.push(call);
    if (ctx.delay) await sleep(ctx.delay);
    let out = ctx.handler ? ctx.handler(call, ctx) : undefined;
    if (!out) out = base(call, ctx);
    const body = typeof out.body === "string" || out.body instanceof Uint8Array ? out.body : JSON.stringify(out.body);
    return new Response(body, { status: out.status, headers: { "content-type": "application/json" } });
  };
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously", pretendToBeVisual: true, url: opts.url || "http://estate.test/#setup",
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = fetchStub; w.TextDecoder = TextDecoder; w.alert = () => {}; w.prompt = () => null;
      w.confirm = () => ctx.confirm;
    },
  });
  await sleep(60);
  const w = dom.window, d = w.document;
  const api = {
    w, d, calls, errors, ctx,
    $: (id) => d.getElementById(id),
    fill(id, v) { d.getElementById(id).value = v; d.getElementById(id).dispatchEvent(new w.Event("input", { bubbles: true })); },
    submit(id, btn) { d.getElementById(id).requestSubmit(btn); },
    async go(h) { w.location.hash = h; await sleep(40); },
    signIn(op, key) {
      d.getElementById("opid").value = op; d.getElementById("opkey").value = key; w.saveOperator();
      d.getElementById("opbar").dispatchEvent(new w.Event("click", { bubbles: true })); return sleep(10);
    },
    text: (id) => d.getElementById(id).textContent,
    cls: (id) => d.getElementById(id).className,
    posts: () => calls.filter((c) => c.method !== "GET" && !c.path.startsWith("/api/")),
  };
  return api;
}

const AGENT = { agent_id: "invoice-bot", name: "Invoice bot", owner: "don@example.com", domain: "finance", status: "active", manifest_ref: null };
const TOKEN = { token_id: "tok-1111-2222", agent_id: "invoice-bot", granted_by: "don", scope: ["draft invoice"], issued_at: "2026-10-25T00:00:00Z", expires_at: "2026-10-26T00:00:00Z", revoked: false };
function base(c, ctx) {
  const p = c.path.split("?")[0];
  if (p.startsWith("/api/")) return { status: 503, body: { detail: "stub" } };
  if (c.method === "GET" && p === "/registry/agents") return { status: 200, body: ctx.agents || [AGENT] };
  if (c.method === "POST" && p === "/registry/agents") return { status: 201, body: { ...AGENT, ...JSON.parse(c.body) } };
  if (c.method === "POST" && p === "/delegation/tokens") return { status: 201, body: TOKEN };
  if (c.method === "POST" && p.endsWith("/revoke")) return { status: 200, body: { ...TOKEN, revoked: true, revoked_at: "2026-10-25T01:00:00Z" } };
  if (p === "/sentinel/health") return { status: 200, body: { ok: true, mode: "enforce" } };
  if (p === "/sentinel/check") return { status: 200, body: { decision: "ALLOW", agent_id: "invoice-bot", action: "draft invoice", clause_id: null, reasons: [], context: {} } };
  if (p === "/ledger/health") return { status: 200, body: { ok: true, signing: "on", appendable: true, key_fingerprint: "ab12", require_signing: true } };
  if (p === "/attest/health") return { status: 200, body: { ok: true, signing: "on", signer: "estate", key_fingerprint: "cd34" } };
  if (p === "/lifecycle/findings") return { status: 200, body: { swept_at: "t", agents_scanned: 1, tokens_scanned: 1, expiring: [], reattestation_due: [], orphans: [], escalations_written: 0, witness: null, retention_policy: null } };
  return { status: 404, body: { detail: "Not Found" } };
}
const fillMint = (a) => { a.fill("su-mint-agent", "invoice-bot"); a.fill("su-mint-scope", "draft invoice"); };
const fillReg = (a) => { a.fill("su-reg-id", "invoice-bot"); a.fill("su-reg-name", "Invoice bot"); a.fill("su-reg-owner", "don@example.com"); };
const ROUTES = ["#setup", "#setup/register-agent", "#setup/mint-token", "#setup/sentinel-check", "#setup/attest-pack", "#setup/read-ledger", "#dashboard"];

const S = {
  async double_mint() {
    const a = await boot({ delay: 80 });
    await a.signIn("don", KEY); await a.go("#setup/mint-token"); fillMint(a);
    a.submit("su-mint"); a.submit("su-mint"); await sleep(10); a.submit("su-mint");
    const disabledInFlight = a.d.querySelector("#su-mint button.primary").disabled;
    await sleep(250);
    return { mints: a.calls.filter((c) => c.method === "POST" && c.path === "/delegation/tokens").length, disabledInFlight,
      disabledAfter: a.d.querySelector("#su-mint button.primary").disabled, result: a.text("su-mint-result") };
  },
  async double_register() {
    const a = await boot({ delay: 80, handler: (c, x) => (c.method === "POST" && c.path === "/registry/agents" ? (x.n = (x.n || 0) + 1, x.n === 1 ? undefined : { status: 409, body: { detail: "already registered" } }) : undefined) });
    await a.signIn("don", KEY); await a.go("#setup/register-agent"); fillReg(a);
    a.submit("su-register"); a.submit("su-register"); await sleep(250);
    return { posts: a.calls.filter((c) => c.method === "POST").length, cls: a.cls("su-reg-result"), result: a.text("su-reg-result") };
  },
  async double_revoke() {
    const a = await boot({ delay: 80 });
    await a.signIn("don", KEY); await a.go("#setup/mint-token"); a.fill("su-revoke-id", "tok-1");
    a.submit("su-revoke"); a.submit("su-revoke"); await sleep(250);
    return { revokes: a.calls.filter((c) => c.path.endsWith("/revoke")).length };
  },
  async double_check() {
    const a = await boot({ delay: 80 });
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "invoice-bot"); a.fill("su-check-action", "x");
    a.submit("su-check"); a.submit("su-check"); await sleep(250);
    return { checks: a.calls.filter((c) => c.path === "/sentinel/check").length };
  },
  async shadow_allow() {
    const a = await boot({ handler: (c) => (c.path === "/sentinel/check" ? { status: 200, body: { decision: "ALLOW", agent_id: "invoice-bot", action: "x", clause_id: null, reasons: [], context: { shadowed: true, would_be: { decision: "BLOCK", clause_id: "D.scope" } } } } : undefined) });
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "invoice-bot"); a.fill("su-check-action", "x");
    a.submit("su-check"); await sleep(80);
    return { cls: a.cls("su-check-result"), text: a.text("su-check-result") };
  },
  async plain_allow() {
    const a = await boot();
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "invoice-bot"); a.fill("su-check-action", "x");
    a.submit("su-check"); await sleep(80);
    return { cls: a.cls("su-check-result") };
  },
  async findings_witness() {
    const body = { swept_at: "t", agents_scanned: 1, tokens_scanned: 1, expiring: [], reattestation_due: [], orphans: [], escalations_written: 0, witness: { status: "stale", estate_watched: "fly" }, retention_policy: { status: "violation" } };
    const a = await boot({ handler: (c) => (c.path === "/lifecycle/findings" ? { status: 200, body } : undefined) });
    await a.go("#setup/read-ledger"); await sleep(80);
    return { cls: a.cls("su-findings-result"), text: a.text("su-findings-result") };
  },
  async findings_clean() {
    const a = await boot(); await a.go("#setup/read-ledger"); await sleep(80);
    return { cls: a.cls("su-findings-result") };
  },
  async findings_404() {
    const a = await boot({ handler: (c) => (c.path === "/lifecycle/findings" ? { status: 404, body: { detail: "Not Found" } } : undefined) });
    await a.go("#setup/read-ledger"); await sleep(80);
    const text1 = a.text("su-findings-result");
    a.ctx.handler = (c) => (c.path === "/lifecycle/findings" ? { status: 404, body: { detail: { message: "no sweep recorded yet", last_tick: null } } } : undefined);
    a.$("su-ledger-refresh").click(); await sleep(80);
    return { absent: text1, sweepless: a.text("su-findings-result") };
  },
  async read_headers() {
    const a = await boot();
    await a.signIn("don", KEY);
    for (const r of ROUTES) await a.go(r);
    await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
    await a.go("#setup/mint-token"); fillMint(a); a.fill("su-mint-by", "don"); a.submit("su-mint"); await sleep(60);
    a.submit("su-revoke"); await sleep(60);
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "invoice-bot"); a.fill("su-check-action", "x"); a.submit("su-check"); await sleep(60);
    const hasOp = (c) => Object.keys(c.headers).some((k) => k.startsWith("x-field-operator"));
    const setup = a.calls.filter((c) => !c.path.startsWith("/api/"));
    return { readWithOp: setup.filter((c) => c.method === "GET" && hasOp(c)).map((c) => c.path),
      guardedWithOp: setup.filter((c) => ["/registry/agents", "/delegation/tokens"].includes(c.path) && c.method === "POST").every(hasOp),
      revokeWithOp: setup.filter((c) => c.path.endsWith("/revoke")).every(hasOp),
      sentinelPostWithOp: setup.filter((c) => c.path === "/sentinel/check").some(hasOp),
      nGuarded: setup.filter((c) => c.method === "POST").length };
  },
  async proto_routes() {
    const a = await boot();
    const out = [];
    for (const h of ["__proto__", "constructor", "toString", "hasOwnProperty", "valueOf"]) {
      await a.go("#setup/" + h);
      out.push({ hash: h, setupShown: !a.$("setup-view").hidden, overviewShown: !a.$("step-overview").hidden, blank: a.d.querySelectorAll(".setup-step:not([hidden])").length });
    }
    return { out, errors: a.errors };
  },
  async xss() {
    const evil = '<img src=x onerror="window.__pwn=1"><script>window.__pwn=2</script>';
    const agents = [{ ...AGENT, agent_id: "a-b", name: evil, owner: evil, domain: evil, manifest_ref: evil }];
    const a = await boot({ agents, handler: (c) => {
      if (c.path === "/sentinel/check") return { status: 200, body: { decision: "BLOCK", agent_id: evil, action: evil, clause_id: evil, reasons: [evil], context: {} } };
      if (c.method === "POST" && c.path === "/registry/agents") return { status: 201, body: { ...AGENT, agent_id: "invoice-bot", name: evil, owner: evil, domain: evil } };
      if (c.method === "POST" && c.path === "/delegation/tokens") return { status: 201, body: { ...TOKEN, token_id: evil, agent_id: evil, scope: [evil] } };
      if (c.path === "/ledger/health") return { status: 200, body: { signing: evil, appendable: true, key_fingerprint: evil, seal_algorithm: evil } };
      if (c.path === "/lifecycle/findings") return { status: 200, body: { swept_at: evil, expiring: [], reattestation_due: [], orphans: [], witness: { status: evil } } };
      return undefined; } });
    await a.signIn("don", KEY);
    await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
    await a.go("#setup/mint-token"); fillMint(a); a.fill("su-mint-by", "don"); a.submit("su-mint"); await sleep(60);
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "x"); a.fill("su-check-action", "x"); a.submit("su-check"); await sleep(60);
    await a.go("#setup/read-ledger"); await sleep(100);
    a.ctx.handler = (c) => (c.method === "POST" ? { status: 422, body: { detail: { clause_id: "D.scope", message: evil } } } : undefined);
    await a.go("#setup/register-agent"); a.fill("su-reg-id", "zz"); a.submit("su-register"); await sleep(60);
    const v = a.$("setup-view");
    return { nodes: v.querySelectorAll("img, script, [onerror], iframe, svg").length, pwn: a.w.__pwn || null,
      shownText: v.textContent.includes("<img src=x") };
  },
  async no_autosubmit() {
    const a = await boot();
    await a.signIn("don", KEY);
    await a.go("#setup/register-agent"); fillReg(a);
    await a.go("#setup/mint-token"); fillMint(a); a.fill("su-mint-by", "don");
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "invoice-bot"); a.fill("su-check-action", "x");
    for (let i = 0; i < 2; i++) for (const r of ROUTES) await a.go(r);
    await a.go("#setup/read-ledger"); a.$("su-ledger-refresh").click(); await sleep(80);
    return { posts: a.posts().map((c) => c.method + " " + c.path) };
  },
  async key_leak() {
    const a = await boot();
    await a.signIn("don", KEY);
    await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
    await a.go("#setup/mint-token"); fillMint(a); a.fill("su-mint-by", "don"); a.submit("su-mint"); await sleep(60);
    a.submit("su-revoke"); await sleep(60);
    await a.go("#setup/sentinel-check"); a.fill("su-check-agent", "invoice-bot"); a.fill("su-check-action", "x"); a.submit("su-check"); await sleep(60);
    await a.go("#setup/read-ledger"); await sleep(100); await a.go("#setup");
    const html = a.d.documentElement.outerHTML;
    const valuesLeak = Array.from(a.d.querySelectorAll("input, textarea")).some((e) => String(e.value).includes(KEY));
    return { inDom: html.includes(KEY), inValues: valuesLeak, inText: a.d.body.textContent.includes(KEY),
      inUrls: a.calls.some((c) => c.path.includes(KEY)) || a.w.location.href.includes(KEY),
      inBodies: a.calls.some((c) => c.body && c.body.includes(KEY)), stored: a.w.sessionStorage.getItem("field-operator-key") === KEY };
  },
  async scrub() {
    const a = await boot({ handler: (c) => (c.method === "POST" && c.path === "/registry/agents" ? { status: 409, body: { detail: "failed at http://ledger.internal:8002/events via fly-abc.flycast:80 and svc.internal" } } : undefined) });
    await a.signIn("don", KEY); await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
    return { text: a.text("su-reg-result") };
  },
  async register_failures() {
    const out = {};
    for (const [st, body] of [[409, { detail: "dup" }], [422, { detail: "bad ref" }], [401, { detail: "operator credentials required" }], [403, { detail: "operator not authorised" }], [502, { detail: "x" }]]) {
      const a = await boot({ handler: (c) => (c.method === "POST" && c.path === "/registry/agents" ? { status: st, body } : undefined) });
      await a.signIn("don", KEY); await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
      out[st] = { cls: a.cls("su-reg-result"), text: a.text("su-reg-result") };
    }
    return out;
  },
  async revoke_confirm() {
    const a = await boot({ confirm: false });
    await a.signIn("don", KEY); await a.go("#setup/mint-token"); a.fill("su-revoke-id", "tok-1"); a.submit("su-revoke"); await sleep(60);
    const declined = a.calls.filter((c) => c.path.endsWith("/revoke")).length;
    a.ctx.confirm = true; a.submit("su-revoke"); await sleep(60);
    return { declined, accepted: a.calls.filter((c) => c.path.endsWith("/revoke")).length - declined, btnEnabled: !a.d.querySelector("#su-revoke button").disabled };
  },
  async period_case() {
    const a = await boot();
    await a.go("#setup/attest-pack"); await sleep(40);
    a.fill("su-attest-period", "2026-q4"); a.submit("su-attest"); await sleep(40);
    const lower = a.calls.filter((c) => c.path.startsWith("/attest/pack")).length;
    return { lower, cls: a.cls("su-attest-result") };
  },
  async scope_preview() {
    const a = await boot();
    await a.go("#setup/mint-token"); a.fill("su-mint-scope", " a b ,c\n\n d,a ");
    return { preview: a.text("su-mint-scope-preview") };
  },
  async focus_heading() {
    const a = await boot();
    await a.go("#setup/mint-token");
    const ae = a.d.activeElement;
    return { tag: ae && ae.tagName, cls: ae && ae.className, inMint: !!(ae && a.$("step-mint-token").contains(ae)) };
  },
  // ---- C-19: the halt banners report per-agent errors (dashboard, not Setup) ----
  async halt_banner() {
    const evil = '<img src=x onerror="window.__pwn=1">';
    const resp = { operator: "CISO", domains: ["finance", "support"], all_ok: false, agent_errors: 3, domains_failed: 2, results: [
      { domain: "finance", ok: false, status: 200, counts: { killed: 0, already_killed: 0, skipped_retired: 0, error: 2 },
        errors: [{ agent_id: "invoicing-agent", error: "502: registry unreachable" }, { agent_id: evil, error: evil }],
        result: { domain: "finance", killed: [], already_killed: [], skipped_retired: [], results: [] } },
      { domain: "support", ok: false, status: 502, counts: { killed: 0, already_killed: 0, skipped_retired: 0, error: 1 },
        errors: [{ agent_id: "support-agent", error: "502: registry unreachable" }], error: { detail: { results: [] } } }] };
    const a = await boot({ url: "http://estate.test/", handler: (c) => (c.path === "/api/fleet/halt" ? { status: 200, body: resp } : undefined) });
    a.fill("halt-op", "CISO"); a.fill("halt-reason", "incident"); a.fill("halt-confirm", "HALT");
    await a.w.fleetHalt(); await sleep(20);
    const el = a.$("halt-result");
    return { text: el.textContent.replace(/\s+/g, " "), headCls: (el.querySelector("b") || {}).className || "",
      okLines: el.querySelectorAll("div.ok").length, nodes: el.querySelectorAll("img, script, [onerror]").length,
      pwn: a.w.__pwn || null };
  },
  async halt_banner_clean() {
    const resp = { operator: "CISO", domains: ["finance"], all_ok: true, agent_errors: 0, domains_failed: 0, results: [
      { domain: "finance", ok: true, status: 200, counts: { killed: 2, already_killed: 1, skipped_retired: 0, error: 0 }, errors: [],
        result: { domain: "finance", killed: ["a", "b"], already_killed: ["c"], skipped_retired: [], results: [] } }] };
    const a = await boot({ url: "http://estate.test/", handler: (c) => (c.path === "/api/fleet/halt" ? { status: 200, body: resp } : undefined) });
    a.fill("halt-op", "CISO"); a.fill("halt-reason", "incident"); a.fill("halt-confirm", "HALT");
    await a.w.fleetHalt(); await sleep(20);
    const el = a.$("halt-result");
    return { text: el.textContent.replace(/\s+/g, " "), headCls: (el.querySelector("b") || {}).className || "", okLines: el.querySelectorAll("div.ok").length };
  },
  async bulk_drill_banner() {
    const resp = { action: "drill", operator: "Don", all_ok: false, error_count: 1, results: [
      { agent_id: "invoicing-agent", ok: false, status: 200, result: { restored: false, restored_status: "<restore failed>" },
        error: "drill did not restore the agent (restored=False, restored_status=<restore failed>)" }] };
    const a = await boot({ url: "http://estate.test/", handler: (c) => (c.path === "/api/agents/bulk" ? { status: 200, body: resp } : undefined) });
    a.w.prompt = () => "Don";
    a.w.toggleSel({ checked: true, dataset: { id: "invoicing-agent" } });
    await a.w.bulk("drill"); await sleep(20);
    const el = a.$("bulk-result");
    return { text: el.textContent.replace(/\s+/g, " "), headCls: (el.querySelector("b") || {}).className || "" };
  },
  async drill_alert() {
    const report = { agent_id: "invoicing-agent", kill_confirmed_ms: 3.2, heartbeat_confirmed_ms: 4.1, endpoint_confirmed_ms: null,
      restored: false, restored_status: "<restore failed>", total_ms: 9.9 };
    const a = await boot({ url: "http://estate.test/", handler: (c) => (c.path === "/api/agents/invoicing-agent/drill" ? { status: 200, body: report } : undefined) });
    const alerts = [];
    a.w.alert = (m) => alerts.push(String(m)); a.w.prompt = () => "Don";
    a.w.eval('drillAgent("invoicing-agent")'); await sleep(80);
    report.restored = true; report.restored_status = "active";
    a.w.eval('drillAgent("invoicing-agent")'); await sleep(80);
    return { alerts };
  },
  async drill_alert_500() {
    // C-19: the kill-switch answers a drill whose restore failed with 500 and the report as the detail;
    // the console's proxy nests it: {"detail": {"detail": report}} (pinned in test_halt_banner_counts_c19.py).
    const report = { agent_id: "invoicing-agent", kill_confirmed_ms: 3.2, heartbeat_confirmed_ms: 4.1, endpoint_confirmed_ms: null,
      restored: false, restored_status: "<restore failed>", total_ms: 9.9 };
    let answer = { status: 500, body: { detail: { detail: report } } };
    const a = await boot({ url: "http://estate.test/", handler: (c) => (c.path === "/api/agents/invoicing-agent/drill" ? answer : undefined) });
    const alerts = [];
    a.w.alert = (m) => alerts.push(String(m)); a.w.prompt = () => "Don";
    a.w.eval('drillAgent("invoicing-agent")'); await sleep(80);
    answer = { status: 403, body: { detail: { detail: "operator not authorised" } } };   // a real refusal stays "Refused"
    a.w.eval('drillAgent("invoicing-agent")'); await sleep(80);
    return { alerts };
  },
};

if (!S[scenario]) { console.error("unknown scenario " + scenario); process.exit(2); }
const res = await S[scenario]();
console.log(JSON.stringify(res));
process.exit(0);
