// Static audit of every HTML sink in the ops-console page (C-457, reviewer C-200 / design note channel 15).
// usage: node innerhtml_audit.mjs <acorn-install-dir> <console.html>   -> one JSON line on stdout.
// A sink is `x.innerHTML = e`, `x.innerHTML += e`, `x.outerHTML = e`, `x.insertAdjacentHTML(pos, e)` or
// `document.write(e)`. The value `e` must be built only from: literals; numbers and booleans; `esc(...)`; template
// literals and `+` whose parts are themselves safe; `a ? b : c` and `a || b` whose branches are safe; calls of the
// page's own functions whose every return is safe; `.map(cb).join()` where cb returns safe text. A parameter of a
// named function is as safe as every argument at every call site; an element of `list.map(cb)` is as safe as `list`.
// Everything else (a property of data such as `a.owner`, an unknown call, a global) is reported. The audit also
// checks that `esc` itself turns the five HTML specials into entities.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import path from "node:path";

const [, , acornDir, htmlPath] = process.argv;
const acorn = createRequire(path.join(acornDir, "noop.js"))("acorn");
const html = readFileSync(htmlPath, "utf-8");

const NUMERIC_CALLS = new Set(["Number", "parseInt", "parseFloat", "Boolean"]);
const BOOLEAN_METHODS = new Set(["toFixed", "includes", "startsWith", "endsWith", "test", "has", "some", "every", "indexOf"]);
const PASS_THROUGH_METHODS = new Set(["slice", "filter", "concat", "trim", "toUpperCase", "toLowerCase", "replace", "padStart", "padEnd", "sort", "reverse", "flat"]);
const ITER_METHODS = new Set(["map", "filter", "some", "every", "find", "forEach"]);

function audit(script) {
  const { code, line0 } = script;
  const program = acorn.parse(code, { ecmaVersion: 2022, locations: true });
  const functions = new Map();   // name -> function node
  const refs = new Map();        // name -> [Identifier nodes referencing it, excluding declarations]
  const sinks = [];
  (function walk(node, parent) {
    node.parent = parent;
    if (node.type === "FunctionDeclaration" && node.id) functions.set(node.id.name, node);
    if (node.type === "VariableDeclarator" && node.id.type === "Identifier" && node.init
        && /^(Arrow)?FunctionExpression$/.test(node.init.type)) functions.set(node.id.name, node.init);
    if (node.type === "Identifier" && !(parent.type === "FunctionDeclaration" && parent.id === node)
        && !(parent.type === "VariableDeclarator" && parent.id === node)
        && !(parent.type === "MemberExpression" && parent.property === node && !parent.computed)
        && !(parent.type === "Property" && parent.key === node && !parent.computed)) {
      (refs.get(node.name) || refs.set(node.name, []).get(node.name)).push(node);
    }
    if (node.type === "AssignmentExpression" && node.left.type === "MemberExpression" && !node.left.computed
        && ["innerHTML", "outerHTML"].includes(node.left.property.name)) sinks.push({ node, value: node.right });
    if (node.type === "CallExpression" && node.callee.type === "MemberExpression" && !node.callee.computed) {
      const n = node.callee.property.name;
      if (n === "insertAdjacentHTML") sinks.push({ node, value: node.arguments[1] });
      if (n === "write" && node.callee.object.type === "Identifier" && node.callee.object.name === "document") sinks.push({ node, value: node.arguments[0] });
    }
    for (const k of Object.keys(node)) {
      if (k === "parent") continue;
      const v = node[k];
      if (Array.isArray(v)) v.forEach((c) => c && typeof c.type === "string" && walk(c, node));
      else if (v && typeof v.type === "string") walk(v, node);
    }
  })(program, null);

  const lineOf = (n) => line0 + n.loc.start.line;
  const snip = (n) => code.slice(n.start, n.end).replace(/\s+/g, " ").slice(0, 80);
  const problem = (n, why) => [{ line: lineOf(n), text: snip(n), why }];
  const isFn = (n) => n && /^(Arrow)?FunctionExpression$|^FunctionDeclaration$/.test(n.type);
  const enclosingFn = (n) => { for (let p = n.parent; p; p = p.parent) if (isFn(p)) return p; return null; };
  const fnName = (f) => f.type === "FunctionDeclaration" ? f.id.name
    : (f.parent.type === "VariableDeclarator" && f.parent.id.type === "Identifier" ? f.parent.id.name : null);
  const paramIndex = (f, name) => f.params.findIndex((p) => (p.type === "AssignmentPattern" ? p.left : p).type === "Identifier"
    && (p.type === "AssignmentPattern" ? p.left : p).name === name);

  function returnsOf(f) {
    if (f.body.type !== "BlockStatement") return [f.body];
    const out = [];
    (function w(n) {
      if (n !== f && isFn(n)) return;
      if (n.type === "ReturnStatement" && n.argument) out.push(n.argument);
      for (const k of Object.keys(n)) {
        if (k === "parent") continue;
        const v = n[k];
        if (Array.isArray(v)) v.forEach((c) => c && typeof c.type === "string" && w(c));
        else if (v && typeof v.type === "string") w(v);
      }
    })(f.body);
    return out;
  }

  function assignmentsTo(scope, name) {   // declarations and assignments of `name` inside scope (any depth)
    const out = [];
    (function w(n) {
      if (n.type === "VariableDeclarator" && n.id.type === "Identifier" && n.id.name === name && n.init) out.push(n.init);
      if (n.type === "AssignmentExpression" && n.left.type === "Identifier" && n.left.name === name) {
        out.push(n.operator === "=" ? n.right : n.right);   // `+=` adds n.right too
      }
      for (const k of Object.keys(n)) {
        if (k === "parent") continue;
        const v = n[k];
        if (Array.isArray(v)) v.forEach((c) => c && typeof c.type === "string" && w(c));
        else if (v && typeof v.type === "string") w(v);
      }
    })(scope);
    return out;
  }
  const declaredIn = (scope, name) => {
    let found = false;
    (function w(n) {
      if (found) return;
      if (n !== scope && isFn(n)) return;
      if (n.type === "VariableDeclarator" && n.id.type === "Identifier" && n.id.name === name) found = true;
      for (const k of Object.keys(n)) {
        if (k === "parent") continue;
        const v = n[k];
        if (Array.isArray(v)) v.forEach((c) => c && typeof c.type === "string" && w(c));
        else if (v && typeof v.type === "string") w(v);
      }
    })(scope);
    return found;
  };

  function resolveParam(f, idx, name, seen) {
    const first = f.body.type === "BlockStatement" ? f.body.body[0] : null;
    if (first && first.type === "ExpressionStatement" && first.expression.type === "AssignmentExpression"
        && first.expression.operator === "=" && first.expression.left.type === "Identifier" && first.expression.left.name === name
        && first.expression.right.type === "LogicalExpression" && first.expression.right.left.type === "CallExpression"
        && first.expression.right.left.callee.type === "Identifier" && NUMERIC_CALLS.has(first.expression.right.left.callee.name)) return [];
    const par = f.parent;
    if (par && par.type === "CallExpression" && par.arguments.includes(f) && par.callee.type === "MemberExpression"
        && !par.callee.computed && ITER_METHODS.has(par.callee.property.name)) {
      return idx === 0 ? bad(par.callee.object, seen) : [];   // an element of the receiver; an index is a number
    }
    const fname = fnName(f);
    if (!fname) return [{ line: lineOf(f), text: name, why: `parameter ${name} of an anonymous function` }];
    const uses = (refs.get(fname) || []).filter((r) => r.parent !== f && !(r.parent.type === "VariableDeclarator" && r.parent.id === r));
    if (!uses.length) return [{ line: lineOf(f), text: name, why: `${fname} has no call site` }];
    const out = [];
    for (const u of uses) {
      if (!(u.parent.type === "CallExpression" && u.parent.callee === u)) return [{ line: lineOf(u), text: fname, why: `${fname} is used as a value, its arguments are unknown` }];
      const arg = u.parent.arguments[idx];
      if (arg) out.push(...bad(arg, seen));
    }
    return out;
  }

  function resolveIdent(id, seen) {
    const name = id.name;
    if (name === "undefined") return [];
    for (let f = enclosingFn(id); ; f = enclosingFn(f)) {
      if (f) {
        const idx = paramIndex(f, name);
        if (idx >= 0) return resolveParam(f, idx, name, seen);
      }
      const scope = f || program;
      if (declaredIn(scope, name)) return assignmentsTo(scope, name).flatMap((v) => bad(v, seen));
      if (!f) break;
    }
    return problem(id, `${name} is not a known-safe variable`);
  }

  function bad(node, seen = new Set()) {
    if (!node) return [];
    if (seen.has(node)) return [];
    seen = new Set(seen).add(node);
    switch (node.type) {
      case "Literal": return [];
      case "TemplateLiteral": return node.expressions.flatMap((e) => bad(e, seen));
      case "Identifier": return resolveIdent(node, seen);
      case "ConditionalExpression": return [...bad(node.consequent, seen), ...bad(node.alternate, seen)];
      case "LogicalExpression": return [...bad(node.left, seen), ...bad(node.right, seen)];
      case "BinaryExpression": return node.operator === "+" ? [...bad(node.left, seen), ...bad(node.right, seen)] : [];
      case "UnaryExpression": return [];
      case "SequenceExpression": return bad(node.expressions[node.expressions.length - 1], seen);
      case "ArrayExpression": return node.elements.flatMap((e) => (e ? bad(e.type === "SpreadElement" ? e.argument : e, seen) : []));
      case "MemberExpression":
        return !node.computed && ["length", "size"].includes(node.property.name) ? [] : problem(node, "a property of data is not escaped");
      case "ChainExpression": return bad(node.expression, seen);
      case "CallExpression": return badCall(node, seen);
      default: return problem(node, `${node.type} is not known to be safe`);
    }
  }

  function badCall(node, seen) {
    const c = node.callee;
    if (c.type === "Identifier") {
      if (c.name === "esc") return [];
      if (NUMERIC_CALLS.has(c.name)) return [];
      if (c.name === "String") return node.arguments.flatMap((a) => bad(a, seen));
      const fn = functions.get(c.name);
      if (fn) return returnsOf(fn).flatMap((r) => bad(r, seen));
      return problem(node, `${c.name}() is not known to return safe text`);
    }
    if (c.type === "MemberExpression" && !c.computed) {
      const m = c.property.name;
      if (m === "map") {
        const cb = node.arguments[0];
        return isFn(cb) ? returnsOf(cb).flatMap((r) => bad(r, seen)) : problem(node, "map callback is not inline");
      }
      if (m === "join") return [...bad(c.object, seen), ...node.arguments.flatMap((a) => bad(a, seen))];
      if (BOOLEAN_METHODS.has(m)) return [];
      if (c.object.type === "Identifier" && c.object.name === "Math") return [];
      if (PASS_THROUGH_METHODS.has(m)) return [...bad(c.object, seen), ...node.arguments.flatMap((a) => bad(a, seen))];
      return problem(node, `.${m}() is not known to return safe text`);
    }
    return problem(node, "a call that is not known to return safe text");
  }

  const results = sinks.map((s) => ({ line: lineOf(s.node), problems: bad(s.value) }));

  // esc itself: the five specials must come out as entities
  let escCheck = { found: false };
  const escFn = functions.get("esc");
  if (escFn) {
    const src = escFn.type === "FunctionDeclaration" ? code.slice(escFn.start, escFn.end) : `(${code.slice(escFn.start, escFn.end)})`;
    const fn = vm.runInNewContext(escFn.type === "FunctionDeclaration" ? `(${src})` : src);
    const out = String(fn(`<img src=x onerror="a">'&`));
    escCheck = { found: true, out, clean: !/[<>"']/.test(out) && !/&(?![#\w]+;)/.test(out) };
  }
  return { sinks: results, escCheck };
}

const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
  .filter((m) => !/\bsrc\s*=/.test(m[1]) && !/\btype\s*=\s*["']?(?!module|text\/javascript)/i.test(m[1]))
  .map((m) => ({ code: m[2], line0: html.slice(0, m.index + m[0].indexOf(">") + 1).split("\n").length - 1 }));
const all = scripts.map(audit);
console.log(JSON.stringify({
  scripts: scripts.length,
  sinks: all.flatMap((a) => a.sinks),
  escChecks: all.map((a) => a.escCheck).filter((e) => e.found),
}));
