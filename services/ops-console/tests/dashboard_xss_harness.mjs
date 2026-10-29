// C-220: the real console.html dashboard runs in jsdom against a stub estate in which EVERY string
// field the dashboard renders holds a hostile payload. The harness drives the drawer, the manifest
// tab, the payload toggle, the harness check, bulk kill, fleet halt, the ledger filter and the
// platform refresh, and scans the DOM after every step for markup that API text must never create:
// an img[src=x], an svg[onload], an on* attribute naming the payload, an extra <script>, or
// window.__pwn set. Last stdout line is JSON: {"maxhit": n, "rendered": [...]}: maxhit 0 = nothing
// was injected; rendered = the containers whose text held the payload at some step (C-268: a flow that
// renders nothing must not pass as "nothing injected", so the test asserts the expected containers).
//
// usage: node dashboard_xss_harness.mjs <jsdomdir> <console.html> <payloadIdx 0..6> <mode>
//   mode: ok | short | unavail | err | status
//     short   : timestamps and token ids too short to hold an attribute, so a slice(...) is exercised
//     unavail : every section answers unavailable with the payload as its error
//     err     : every follow-up call fails with the payload as its detail
//     status  : the drawer agent's status is the payload
// Ported from the C-200 reviewer's probe (xss_probe3.mjs); same stub estate.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";

const [, , jsdomDir, htmlPath, pidx, mode = "ok"] = process.argv;
const require = createRequire(path.join(jsdomDir, "noop.js"));
const { JSDOM, VirtualConsole } = require("jsdom");
const ORIGIN = "http://127.0.0.1:18080";
const PAY = [
  `"><img src=x onerror="window.__pwn=1">`,
  `'><img src=x onerror='window.__pwn=1'>`,
  `</td><svg onload="window.__pwn=1">`,
  `</pre><script>window.__pwn=1</script>`,
  `x" onmouseover="window.__pwn=1" a="`,
  `</option></select><img src=x onerror=window.__pwn=1>`,
  `</textarea><img src=x onerror=window.__pwn=1>`,
];
const P = PAY[Number(pidx || 0)];
const sec = (data) => ({ available: true, source: "s", error: null, data });
const bad = () => ({ available: false, source: P, error: P, data: null });
const SH = "<svg/onload=x()>aaaaaaaaaaaa";
const ts = mode === "short" ? SH : "2026-10-29T10:11:12+00:00";
const ev = { event_id: P, ts, event_type: P, agent_id: P, hash: P, prev_hash: P,
             payload: { clause_id: P, x: P } };
const agent = { agent_id: P, owner: P, domain: P, status: P, name: P, manifest_ref: P };
const tok = { token_id: (mode === "short" ? "<svg/onl" : P) + "0123456789", agent_id: P, scope: [P, P],
              expires_at: mode === "short" ? SH : "2099-01-01T00:00:00Z", revoked: false, granted_by: P };
const usage = { total_input_tokens: P, total_output_tokens: P, total_cost_display: P, open_rogue_flags: P,
                by_model: [{ model: P, allowed: false, priced: false }] };
const overview0 = {
  generated_at: ts,
  ledger_verify: sec({ ok: false, reason: P, length: P }),
  agents: sec([agent, { ...agent, status: "active" }, { ...agent, status: "retired" }]),
  tokens: sec([tok]),
  escalations: sec([{ escalation_id: P, agent_id: P, kind: P, spent: P, limit: P, pct: P, ts }]),
  token_usage: sec([{ agent_id: P, ...usage }]),
  recent_events: sec([ev]),
};
const detail0 = {
  agent: sec({ ...agent, status: mode === "status" ? P : "active" }), heartbeat: sec({ [P]: P }),
  tokens: sec([tok]), usage: sec(usage), events: sec([ev]),
};
const platform0 = {
  health: { [P]: { available: true, data: { version: P }, error: P }, b: { available: false, error: P } },
  lifecycle: sec({ no_sweep_yet: false, expiring: [1], reattestation_due: [], orphans: [], swept_at: P,
                   agents_scanned: P }),
  attest: sec({ signing: P, signer: P }),
  crosswalk: sec({ corpus_version: P, active: [1], last_check: P }),
  federation: sec([{ contract_id: P, counterparty_org: P, allowed_scopes: [P] }]),
};
const U = (o) => mode === "unavail"
  ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, (v && v.available !== undefined) ? bad() : v]))
  : o;
const overview = U(overview0), detail = U(detail0), platform = U(platform0);
const counts = { killed: P, already_killed: P, skipped_retired: P, error: P };
const bulk = { all_ok: false, results: [{ ok: false, agent_id: P, status: P, error: P }] };
const halt = { all_ok: false, agent_errors: P, results: [
  { ok: false, domain: "d", status: 500, error: { detail: P } },
  { ok: true, domain: P, status: P, error: P, counts, errors: [] },
  { ok: false, domain: P, status: P, error: P, counts, errors: [{ agent_id: P, error: P }] }] };
const routes = (p) => {
  if (p === "/api/overview") return overview;
  if (p === "/api/platform") return platform;
  if (p.endsWith("/manifest")) return { validation: P, ref: P, reason: P, raw: P };
  if (p === "/api/agents/bulk") return bulk;       // before the /api/agents/ prefix below
  if (p.startsWith("/api/agents/")) return detail;
  if (p === "/api/events") return [ev];
  if (p === "/api/check") return { decision: P, clause_id: P, reasons: [P] };
  if (p === "/api/fleet/halt") return halt;
  return {};
};
const vc = new VirtualConsole();
vc.on("jsdomError", () => {});
const dom = new JSDOM(readFileSync(htmlPath, "utf8"), {
  url: ORIGIN + "/", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
  beforeParse(w) {
    w.__pwn = 0;
    w.fetch = async (u) => {
      const p = new URL(String(u), ORIGIN).pathname;
      if (p === "/api/stream") return { status: 404, ok: false, body: null, headers: new Map() };
      if (mode === "err" && p !== "/api/overview" && p !== "/api/platform") {
        return { status: 400, ok: false, headers: { get: () => null }, json: async () => ({ detail: P }),
                 text: async () => P };
      }
      const j = routes(p);
      return { status: 200, ok: true, headers: { get: () => null }, json: async () => j,
               text: async () => JSON.stringify(j) };
    };
    w.alert = () => {}; w.prompt = () => "op"; w.confirm = () => true;
    Object.defineProperty(w, "isSecureContext", { value: true });
    w.HTMLDialogElement.prototype.showModal = function () {};
    w.HTMLDialogElement.prototype.close = function () {};
  },
});
const w = dom.window;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(400);
const baseScripts = w.document.querySelectorAll("script").length;  // the page's own, before any step
let MAXHIT = 0;
const CONTAINERS = ["agents", "escalations", "events", "d-details", "d-manifest", "bulk-result",
                    "halt-result", "verdict", "platform"];
const RENDERED = new Set();  // every payload carries __pwn, which survives esc() and JSON.stringify
const scan = () => {
  const d = w.document;
  for (const id of CONTAINERS) {
    const e = d.getElementById(id);
    if (e && e.textContent.includes("__pwn")) RENDERED.add(id);
  }
  const onattr = [...d.querySelectorAll("*")].filter(
    (e) => [...e.attributes].some((a) => /^on/.test(a.name) && /__pwn|x\(\)/.test(a.value))).length;
  const hit = d.querySelectorAll("img[src='x'], svg[onload]").length + onattr
    + Math.max(0, d.querySelectorAll("script").length - baseScripts) + (w.__pwn ? 1 : 0);
  MAXHIT = Math.max(MAXHIT, hit);
};
const click = (sel) => { const e = w.document.querySelector(sel); if (e) e.click(); return !!e; };
w.eval("openDrawer(" + JSON.stringify(P) + ")"); scan(); await sleep(300);
w.eval("showTab('manifest')"); scan(); await sleep(300);
click("tr.ev"); scan(); await sleep(100);
w.document.getElementById("h-agent").value = "x";
await w.eval("runCheck({preventDefault(){}})"); scan(); await sleep(100);
w.eval("SELECTED.add('x')"); await w.eval("bulk('kill')"); scan(); await sleep(200);
w.document.getElementById("halt-op").value = "a";
w.document.getElementById("halt-reason").value = "b";
w.document.getElementById("halt-confirm").value = "HALT";
await w.eval("fleetHalt()"); scan(); await sleep(200);
w.document.getElementById("f-type").value = "x";
await w.eval("applyFilter()"); scan(); await sleep(200);
await w.eval("refreshPlatform()"); scan(); await sleep(200);
scan();
console.log(JSON.stringify({ maxhit: MAXHIT, rendered: CONTAINERS.filter((id) => RENDERED.has(id)) }));
w.close();
