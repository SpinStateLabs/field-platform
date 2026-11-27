// The real console.html in jsdom with a switchable document.visibilityState: which requests the dashboard makes while
// the page is hidden and visible, and what the integrity tile shows for each shape of the ledger_verify section.
// The page's intervals are captured and run by hand. Last stdout line is JSON.
//
// usage: node verify_pacing_harness.mjs <jsdomdir> <console.html>
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";

const [, , jsdomDir, htmlPath] = process.argv;
const require = createRequire(path.join(jsdomDir, "noop.js"));
const { JSDOM, VirtualConsole } = require("jsdom");
const ORIGIN = "http://127.0.0.1:18080";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const none = () => ({ available: false, source: "s", error: "x", data: null });
const overview = { generated_at: "2026-01-01T10:11:12+00:00", agents: none(), tokens: none(), escalations: none(),
                   ledger_verify: none(), recent_events: none(), token_usage: none() };
// the page reads /api/platform as it loads and takes its shape for granted
const platform = { health: {}, lifecycle: none(), attest: none(), crosswalk: none(), federation: none() };

async function page(initial) {
  const state = { visibility: initial, all: 0, overview: 0, platform: 0, streams: [], intervals: [] };
  const vc = new VirtualConsole();
  vc.on("jsdomError", () => {});
  const dom = new JSDOM(readFileSync(htmlPath, "utf8"), {
    url: ORIGIN + "/", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      Object.defineProperty(w.document, "visibilityState", { configurable: true, get: () => state.visibility });
      w.TextDecoder = TextDecoder;
      w.setInterval = (fn) => { state.intervals.push(fn); return state.intervals.length; };
      w.fetch = async (u, opts) => {
        const p = new URL(String(u), ORIGIN).pathname;
        state.all += 1;               // every request the page makes
        if (p === "/api/stream") {
          const signal = opts.signal;
          state.streams.push(signal);
          const read = () => new Promise((_, reject) =>
            signal.addEventListener("abort", () => reject(new Error("aborted"))));
          return { status: 200, ok: true, body: { getReader: () => ({ read }) }, headers: { get: () => null } };
        }
        if (p === "/api/overview") state.overview += 1;
        if (p === "/api/platform") state.platform += 1;
        const j = p === "/api/overview" ? overview : p === "/api/platform" ? platform : {};
        return { status: 200, ok: true, headers: { get: () => null }, json: async () => j,
                 text: async () => JSON.stringify(j) };
      };
      w.alert = () => {}; w.prompt = () => null; w.confirm = () => false;
      Object.defineProperty(w, "isSecureContext", { value: true });
      w.HTMLDialogElement.prototype.showModal = function () {};
      w.HTMLDialogElement.prototype.close = function () {};
    },
  });
  await sleep(300);
  const w = dom.window;
  const seen = () => ({ overview: state.overview, platform: state.platform, streams: state.streams.length,
                        open: state.streams.filter((s) => !s.aborted).length });
  const requests = () => state.all;
  const tick = async () => { for (const fn of state.intervals) fn(); await sleep(100); };
  const turn = async (v) => { state.visibility = v; w.document.dispatchEvent(new w.Event("visibilitychange"));
                              await sleep(100); };
  return { w, seen, requests, tick, turn };
}

const out = {};
const a = await page("hidden");
out.hiddenAtLoad = a.seen();
await a.tick();
out.hiddenAfterPoll = a.seen();
out.hiddenRequests = a.requests();
await a.turn("visible");
out.shown = a.seen();
await a.turn("hidden");
const before = a.requests();
await a.tick();
await a.tick();
out.hiddenAgain = a.seen();
out.askedWhileHiddenAgain = a.requests() - before;
await a.turn("visible");
out.shownAgain = a.seen();

const b = await page("visible");
out.visibleAtLoad = b.seen();
await b.tick();
out.visibleAfterPoll = b.seen();
const tile = (sec) => { b.w.renderIntegrity(sec); const el = b.w.document.getElementById("integrity");
                        return { text: el.textContent, cls: el.className }; };
const busy = (data) => ({ available: false, source: "GET /verify", error: "busy, retrying", data });
out.tiles = {
  busy: tile(busy(null)),
  busyAfterIntact: tile(busy({ ok: true, length: 7 })),
  busyAfterBroken: tile(busy({ ok: false, reason: "hash mismatch", length: 7 })),
  error: tile({ available: false, source: "GET /verify", error: "status 500: upstream error", data: null }),
  intact: tile({ available: true, source: "GET /verify", error: null, data: { ok: true, length: 9 } }),
};
console.log(JSON.stringify(out));
process.exit(0);
