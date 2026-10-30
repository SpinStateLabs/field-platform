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
    const call = { path: String(p), method: (o.method || "GET").toUpperCase(), headers, body: o.body || null, redirect: o.redirect || null };
    calls.push(call);
    if (ctx.delay) await sleep(ctx.delay);
    let out = ctx.handler ? ctx.handler(call, ctx) : undefined;
    if (!out) out = base(call, ctx);
    const body = typeof out.body === "string" || out.body instanceof Uint8Array ? out.body : JSON.stringify(out.body);
    return new Response(body, { status: out.status, headers: { "content-type": "application/json" } });
  };
  const url = opts.url || "https://estate.test/#setup";
  // jsdom has no window.isSecureContext: emulate the browser rule (Secure Contexts: https, or a loopback
  // host 127.0.0.0/8, [::1], localhost, *.localhost). opts.secure overrides it, e.g. a browser flag that
  // marks a LAN http origin secure, or a page framed by an insecure parent.
  const u = new URL(url), h = u.hostname;
  ctx.secure = opts.secure !== undefined ? opts.secure
    : u.protocol === "https:" || /^127\./.test(h) || h === "[::1]" || h === "localhost" || h.endsWith(".localhost");
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously", pretendToBeVisual: true, url,
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = fetchStub; w.TextDecoder = TextDecoder; w.alert = () => {}; w.prompt = () => null;
      w.confirm = () => ctx.confirm;
      Object.defineProperty(w, "isSecureContext", { configurable: true, get: () => ctx.secure });
      for (const [k, v] of Object.entries(opts.seed || {})) w.sessionStorage.setItem(k, v);
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
const hasOp = (c) => Object.keys(c.headers).some((k) => k.startsWith("x-field-operator"));
// C-20: type a key into the bar, run a guarded register and a dashboard refresh, report what was stored and sent.
async function keyTransport(opts) {
  const a = await boot(opts);
  await a.signIn("don", KEY);
  const keyField = a.$("opkey").value;
  await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
  await a.w.refresh(); await sleep(20);
  const guarded = a.calls.filter((c) => c.method === "POST" && c.path === "/registry/agents");
  return { storedKey: a.w.sessionStorage.getItem("field-operator-key"), storedId: a.w.sessionStorage.getItem("field-operator"),
    keyField, keyDisabled: a.$("opkey").disabled, opstate: a.text("opstate"), banner: a.text("setup-opstate"),
    nGuarded: guarded.length, guardedWithOp: guarded.length > 0 && guarded.every(hasOp),
    guardedKey: guarded.length ? guarded[0].headers["x-field-operator-key"] === KEY : false,
    sentOp: a.calls.filter(hasOp).map((c) => c.method + " " + c.path), nCalls: a.calls.length,
    keyInDom: a.d.documentElement.outerHTML.includes(KEY) };
}
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
      setupGuardedRedirectError: setup.filter((c) => c.method === "POST" && c.path !== "/sentinel/check").every((c) => c.redirect === "error"),
      sentinelPostWithOp: setup.filter((c) => c.path === "/sentinel/check").some(hasOp),
      nGuarded: setup.filter((c) => c.method === "POST").length };
  },
  // C-221: with a key stored on a secure origin, a dashboard read, the stream, the manifest read, the export and the
  // dry-run check carry the perimeter secret alone; only the guarded writes carry the operator pair.
  async dashboard_headers() {
    const a = await boot({ seed: { "field-secret": "PERIMETER-s3" } });
    await a.signIn("don", KEY);
    a.w.prompt = () => "don";
    a.ctx.n0 = a.calls.length;
    await a.w.refresh(); await a.w.startStream(); await a.w.loadManifest("invoice-bot");
    await a.w.exportEvents("csv"); await a.w.exportEvents("json");
    a.fill("h-agent", "invoice-bot"); a.fill("h-action", "x");
    await a.w.runCheck({ preventDefault() {} });
    for (const f of ["killAgent", "reviveAgent", "drillAgent", "revokeTok", "resolveEsc"]) await a.w.eval(f + '("invoice-bot")');
    a.w.eval('SELECTED.add("invoice-bot")'); await a.w.bulk("kill");
    a.fill("halt-op", "don"); a.fill("halt-reason", "drill"); a.fill("halt-confirm", "HALT"); await a.w.fleetHalt();
    await sleep(40);
    const api = a.calls.filter((c) => c.path.startsWith("/api/"));
    const guardedPath = (c) => c.method === "POST" && c.path !== "/api/check";
    // C-451: hdrs() sends the pair only for the boolean true (a truthy "yes" or 1 must not), and no window global
    // holds the key (strings, and plain objects through JSON).
    const w = a.w, h = (v) => Object.keys(w.hdrs(v)).filter((k) => k.startsWith("x-field-operator")).length;
    const leaks = [];
    for (const name of Object.getOwnPropertyNames(w)) {
      let v; try { v = w[name]; } catch (e) { continue; }
      try {
        if (typeof v === "string" && v.includes(KEY)) leaks.push(name);
        else if (v && typeof v === "object" && v !== w && !(v instanceof w.Node) && JSON.stringify(v).includes(KEY)) leaks.push(name);
      } catch (e) { /* circular or host object: not a plain holder of the key */ }
    }
    return { reads: api.filter((c) => !guardedPath(c)).map((c) => c.method + " " + c.path.split("?")[0]),
      readsWithOp: api.filter((c) => !guardedPath(c) && hasOp(c)).map((c) => c.method + " " + c.path.split("?")[0]),
      nGuarded: api.filter(guardedPath).length,
      guardedPaths: api.filter(guardedPath).map((c) => c.path),
      guardedRedirectError: api.filter(guardedPath).every((c) => c.redirect === "error"),
      hdrsPair: { yes: h("yes"), one: h(1), obj: h({}), nul: h(null), none: h(), tru: h(true) },
      keyGlobals: leaks.filter((n) => n !== "sessionStorage" && n !== "_sessionStorage"),
      guardedWithPair: api.filter(guardedPath).every((c) => c.headers["x-field-operator"] === "don" && c.headers["x-field-operator-key"] === KEY),
      withoutSecret: api.filter((c) => c.headers["x-field-auth"] !== "PERIMETER-s3").map((c) => c.path.split("?")[0]) };
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
  // ---- C-20: the operator key is stored and sent only from a secure context ----
  async key_insecure_lan() { return keyTransport({ url: "http://192.0.2.10:18080/#setup" }); },
  async key_flagged_lan() { return keyTransport({ url: "http://192.0.2.10:18080/#setup", secure: true }); },
  async key_not_secure_context() { return keyTransport({ url: "https://192.0.2.10:18443/#setup", secure: false }); },
  async key_https() { return keyTransport({ url: "https://192.0.2.10:18443/#setup" }); },
  async key_loopback() {
    const out = {};
    for (const host of ["127.0.0.1", "[::1]", "localhost"]) out[host] = await keyTransport({ url: "http://" + host + ":18080/#setup" });
    return out;
  },
  async key_leftover() {
    // an earlier console version stored a key in this tab on the plain-http LAN page
    const a = await boot({ url: "http://192.0.2.10:18080/#setup", seed: { "field-operator": "don", "field-operator-key": KEY } });
    await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
    await a.go("#setup/mint-token"); fillMint(a); a.fill("su-mint-by", "don"); a.submit("su-mint"); await sleep(60);
    await a.w.refresh(); await sleep(20);
    return { storedKey: a.w.sessionStorage.getItem("field-operator-key"), storedId: a.w.sessionStorage.getItem("field-operator"),
      sentOp: a.calls.filter(hasOp).map((c) => c.method + " " + c.path), nCalls: a.calls.length,
      nGuarded: a.calls.filter((c) => c.method === "POST" && !c.path.startsWith("/api/")).length,
      opstate: a.text("opstate"), keyInDom: a.d.documentElement.outerHTML.includes(KEY) };
  },
  async key_send_gate() {
    // a key stored while the page was secure is not sent once the page is no longer a secure context
    const a = await boot({ url: "https://192.0.2.10:18443/#setup" });
    await a.signIn("don", KEY);
    a.ctx.secure = false; const from = a.calls.length;
    await a.go("#setup/register-agent"); fillReg(a); a.submit("su-register"); await sleep(60);
    await a.w.refresh(); await sleep(20);
    const after = a.calls.slice(from);
    return { sentOp: after.filter(hasOp).map((c) => c.method + " " + c.path), nAfter: after.length,
      nGuarded: after.filter((c) => c.method === "POST" && !c.path.startsWith("/api/")).length };
  },
  async key_wording() {
    const out = {};
    for (const [name, url] of [["https", "https://192.0.2.10:18443/#setup"], ["lan", "http://192.0.2.10:18080/#setup"]]) {
      const a = await boot({ url });
      const texts = [];
      const grab = () => texts.push(a.text("opstate"), a.text("setup-opstate"), a.text("su-mint-by-hint"));
      await a.go("#setup/mint-token"); grab();
      await a.signIn("don", KEY); await a.go("#setup/register-agent"); await a.go("#setup/mint-token"); grab();
      out[name] = { texts, opstate: a.text("opstate"), banner: a.text("setup-opstate") };
    }
    return out;
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

S.dashboard_headers_writes = S.dashboard_headers;
S.dashboard_headers_truthy = S.dashboard_headers;
S.dashboard_key_global = S.dashboard_headers;
S.dashboard_redirect = S.dashboard_headers;
S.setup_redirect = S.read_headers;
if (!S[scenario]) { console.error("unknown scenario " + scenario); process.exit(2); }
const res = await S[scenario]();
console.log(JSON.stringify(res));
process.exit(0);
