// Static audit of every HTML sink in the ops-console page (C-457, reviewer C-200 / design note channel 15;
// hardened after reviewer C-508 and the Lane 10 review of PR 314).
// usage: node innerhtml_audit.mjs <acorn-install-dir> <console.html>   -> one JSON line on stdout.
// A sink is `x.innerHTML = e`, `x.innerHTML += e`, `x.outerHTML = e`, `x.srcdoc = e` (also with a string-literal key
// `x["innerHTML"]`, in `Object.assign(x, {innerHTML: e})` and in `x.setAttribute("srcdoc", e)`), `x.insertAdjacentHTML(pos, e)`,
// `document.write(e)` / `writeln` (any `.write(` or `.writeln(`), `range.createContextualFragment(e)` and
// `new DOMParser().parseFromString(e, type)`. The value `e` must be built only from: literals; numbers and booleans; `esc(...)`; template
// literals and `+` whose parts are themselves safe; `a ? b : c` and `a || b` whose branches are safe; calls of the
// page's own functions whose every return is safe; `.map(cb).join()` where cb returns safe text. A parameter of a
// named function is as safe as every argument at every call site; an element of `list.map(cb)` is as safe as `list`.
// Everything else (a property of data such as `a.owner`, an unknown call, a global) is reported. The audit also
// checks that `esc` itself turns the five HTML specials into entities, that `esc` is bound exactly once (at the top
// level of a script) and never reassigned, that no function name is defined twice, and that no template expression
// lands inside an inline event handler (`on*="..."`) or at the start of a URL attribute (an HTML escape is not a
// JavaScript escape, and a URL can start with `javascript:`). Also reported, wherever they appear: `eval`, `Function(...)`,
// a string passed to `setTimeout` / `setInterval`, `setAttribute` with a computed name or a constant-only attribute
// (`on*`, `srcdoc`) given a non-constant value, a URL property (`href`, `src`, `action`, `formAction`) assigned
// something other than a literal, a `#` or `/` relative string, or `URL.createObjectURL(...)`, and a `.replace` whose
// replacement text re-introduces markup.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import path from "node:path";

const [, , acornDir, htmlPath] = process.argv;
const acorn = createRequire(path.join(acornDir, "noop.js"))("acorn");
const html = readFileSync(htmlPath, "utf-8");

const NUMERIC_CALLS = new Set(["Number", "parseInt", "parseFloat", "Boolean"]);
const BOOLEAN_METHODS = new Set(["toFixed", "includes", "startsWith", "endsWith", "test", "has", "some", "every", "indexOf"]);
const PASS_THROUGH_METHODS = new Set(["slice", "filter", "concat", "trim", "toUpperCase", "toLowerCase", "padStart", "padEnd", "sort", "reverse", "flat"]);
const ITER_METHODS = new Set(["map", "filter", "some", "every", "find", "forEach"]);
const HTML_SINK_PROPS = new Set(["innerHTML", "outerHTML", "srcdoc"]);
const URL_PROPS = new Set(["href", "src", "action", "formAction", "data", "poster", "codebase"]);
const URL_ATTRS = new Set(["href", "src", "action", "formaction", "xlink:href", "data", "poster", "codebase"]);
const CONSTANT_ONLY_ATTRS = (n) => /^on/i.test(n) || n.toLowerCase() === "srcdoc";

function audit(script) {
  const { code, line0 } = script;
  const program = acorn.parse(code, { ecmaVersion: 2022, locations: true });
  const lineOf = (n) => line0 + n.loc.start.line;
  function patternNames(p) {
    if (!p) return [];
    switch (p.type) {
      case "Identifier": return [p.name];
      case "ObjectPattern": return p.properties.flatMap((q) => patternNames(q.type === "RestElement" ? q.argument : q.value));
      case "ArrayPattern": return p.elements.flatMap((q) => patternNames(q));
      case "AssignmentPattern": return patternNames(p.left);
      case "RestElement": return patternNames(p.argument);
      case "MemberExpression": return [];
      default: return [];
    }
  }
  const functions = new Map();   // name -> function node
  const structure = [];          // findings that are not about one sink value
  const escBindings = [];        // every binding or assignment of the name esc
  const refs = new Map();        // name -> [Identifier nodes referencing it, excluding declarations]
  const sinks = [];
  const pending = [];            // [node, why] findings recorded during the walk
  const keyName = (n, computed) => !computed && n.type === "Identifier" ? n.name
    : n.type === "Literal" && typeof n.value === "string" ? n.value
    : n.type === "TemplateLiteral" && n.expressions.length === 0 ? n.quasis[0].value.cooked : null;
  (function walk(node, parent) {
    node.parent = parent;
    const defineFn = (name, fn) => {
      if (functions.has(name)) structure.push({ line: lineOf(fn), text: name, why: `function ${name} is defined more than once (the audit keys functions by name)` });
      functions.set(name, fn);
    };
    if (node.type === "FunctionDeclaration" && node.id) defineFn(node.id.name, node);
    if (node.type === "VariableDeclarator" && node.id.type === "Identifier" && node.init
        && /^(Arrow)?FunctionExpression$/.test(node.init.type)) defineFn(node.id.name, node.init);
    // every place the name `esc` is bound or assigned
    if (node.type === "VariableDeclarator" && patternNames(node.id).includes("esc")) escBindings.push({ node, top: parent.parent === program });
    if (node.type === "FunctionDeclaration" && node.id && node.id.name === "esc") escBindings.push({ node, top: parent === program });
    if (/^(Arrow)?FunctionExpression$|^FunctionDeclaration$/.test(node.type) && node.params.some((q) => patternNames(q).includes("esc"))) escBindings.push({ node, top: false });
    if (node.type === "CatchClause" && node.param && patternNames(node.param).includes("esc")) escBindings.push({ node, top: false });
    if (node.type === "ClassDeclaration" && node.id && node.id.name === "esc") escBindings.push({ node, top: false });
    if (node.type === "AssignmentExpression" && patternNames(node.left).includes("esc")) escBindings.push({ node, top: false });
    if (node.type === "UpdateExpression" && node.argument.type === "Identifier" && node.argument.name === "esc") escBindings.push({ node, top: false });
    if (node.type === "Identifier" && !(parent.type === "FunctionDeclaration" && parent.id === node)
        && !(parent.type === "VariableDeclarator" && parent.id === node)
        && !(parent.type === "MemberExpression" && parent.property === node && !parent.computed)
        && !(parent.type === "Property" && parent.key === node && !parent.computed)) {
      (refs.get(node.name) || refs.set(node.name, []).get(node.name)).push(node);
    }
    if (node.type === "AssignmentExpression") {
      const l = node.left;
      if (l.type === "MemberExpression") {
        const n = keyName(l.property, l.computed);
        if (n && HTML_SINK_PROPS.has(n)) sinks.push({ node, value: node.right, kind: "html" });
        else if (n && URL_PROPS.has(n)) sinks.push({ node, value: node.right, kind: "url" });
      } else if (l.type === "ObjectPattern" || l.type === "ArrayPattern") {
        (function members(p) {
          if (!p) return;
          if (p.type === "MemberExpression") {
            const n = keyName(p.property, p.computed);
            if (n === null || HTML_SINK_PROPS.has(n) || URL_PROPS.has(n)) pending.push([p, "a destructuring assignment into a possible HTML or URL sink is not followed"]);
          }
          else if (p.type === "ObjectPattern") p.properties.forEach((q) => members(q.type === "RestElement" ? q.argument : q.value));
          else if (p.type === "ArrayPattern") p.elements.forEach(members);
          else if (p.type === "AssignmentPattern") members(p.left);
          else if (p.type === "RestElement") members(p.argument);
        })(l);
      }
    }
    if (node.type === "NewExpression" && node.callee.type === "Identifier" && node.callee.name === "Function") pending.push([node, "new Function() runs a string as code"]);
    if (node.type === "CallExpression") {
      const c = node.callee;
      if (c.type === "Identifier" && (c.name === "eval" || c.name === "Function")) pending.push([node, `${c.name}() runs a string as code`]);
      const tname = c.type === "Identifier" ? c.name : (c.type === "MemberExpression" && !c.computed && c.object.type === "Identifier" && ["window", "self", "globalThis"].includes(c.object.name) ? c.property.name : null);
      if ((tname === "setTimeout" || tname === "setInterval") && node.arguments[0]
          && ["Literal", "TemplateLiteral", "BinaryExpression"].includes(node.arguments[0].type)) pending.push([node, `${tname}() with a string runs it as code`]);
      if (c.type === "MemberExpression") {
        const n = keyName(c.property, c.computed);
        if (n === null && c.computed) pending.push([node, "a call through a computed member name is not followed"]);
        if (n === "insertAdjacentHTML") sinks.push({ node, value: node.arguments[1], kind: "html" });
        if (n === "write" || n === "writeln") node.arguments.forEach((a) => sinks.push({ node, value: a, kind: "html" }));
        if (n === "createContextualFragment" || n === "parseFromString") sinks.push({ node, value: node.arguments[0], kind: "html" });
        if (n === "setAttribute") {
          const a0 = node.arguments[0];
          const an = a0 && (a0.type === "Literal" || a0.type === "TemplateLiteral") ? keyName(a0, false) : null;
          if (an === null || an === undefined) pending.push([node, "setAttribute with a name that is not a literal"]);
          else if (CONSTANT_ONLY_ATTRS(an)) sinks.push({ node, value: node.arguments[1], kind: "const" });
          else if (URL_ATTRS.has(an.toLowerCase())) sinks.push({ node, value: node.arguments[1], kind: "url" });
        }
        if (c.object.type === "Identifier" && c.object.name === "Object" && n === "assign") {
          const target = node.arguments[0];
          node.arguments.slice(1).forEach((a) => {
            if (a.type === "ObjectExpression") {
              a.properties.forEach((q) => {
                if (q.type === "SpreadElement") { if (!target || target.type !== "ObjectExpression") pending.push([q, "Object.assign of a spread onto a possible element"]); return; }
                const pn = keyName(q.key, q.computed);
                if (pn === null) pending.push([q, "Object.assign with a computed key onto a possible element"]);
                else if (HTML_SINK_PROPS.has(pn)) sinks.push({ node: q, value: q.value, kind: "html" });
                else if (URL_PROPS.has(pn)) sinks.push({ node: q, value: q.value, kind: "url" });
              });
            } else if (!target || target.type !== "ObjectExpression") pending.push([a, "Object.assign from a value that is not an object literal onto a possible element"]);
          });
        }
      }
    }
    for (const k of Object.keys(node)) {
      if (k === "parent") continue;
      const v = node[k];
      if (Array.isArray(v)) v.forEach((c) => c && typeof c.type === "string" && walk(c, node));
      else if (v && typeof v.type === "string") walk(v, node);
    }
  })(program, null);

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

  // Every way `name` gets a value inside `scope`: declarations (not crossing nested functions), and assignments
  // (at any depth). for...of binds an element of the iterated value; for...in a key; a catch parameter is an error.
  function bindingInfo(scope, name) {
    const sources = [];
    let declared = false;
    (function w(n, crossed) {
      if (n !== scope && isFn(n)) crossed = true;
      if (!crossed) {
        if (n.type === "VariableDeclarator" && patternNames(n.id).includes(name)) {
          declared = true;
          const loop = n.parent && n.parent.parent;
          if (loop && (loop.type === "ForOfStatement" || loop.type === "ForInStatement") && loop.left === n.parent) {
            sources.push(loop.type === "ForOfStatement" ? { elementOf: loop.right } : { at: n, why: `${name} is a key of an object (for...in)` });
          } else if (n.init) sources.push({ node: n.init });
        }
        if (n.type === "CatchClause" && n.param && patternNames(n.param).includes(name)) {
          declared = true;
          sources.push({ at: n, why: `${name} is a caught error` });
        }
      }
      if ((n.type === "ForOfStatement" || n.type === "ForInStatement") && n.left.type === "Identifier" && n.left.name === name) {
        sources.push(n.type === "ForOfStatement" ? { elementOf: n.right } : { at: n, why: `${name} is a key of an object (for...in)` });
      }
      // an array filled in place: name.push(e), name.unshift(e), name.splice(i, n, e), name.fill(e), name[i] = e
      if (n.type === "CallExpression" && n.callee.type === "MemberExpression" && !n.callee.computed && n.callee.object.type === "Identifier"
          && n.callee.object.name === name && ["push", "unshift", "splice", "fill"].includes(n.callee.property.name)) {
        n.arguments.forEach((a) => sources.push({ node: a.type === "SpreadElement" ? a.argument : a }));
      }
      if (n.type === "AssignmentExpression" && n.left.type === "MemberExpression" && n.left.computed
          && n.left.object.type === "Identifier" && n.left.object.name === name) sources.push({ node: n.right });
      if (n.type === "AssignmentExpression" && n.left.type === "Identifier" && n.left.name === name) sources.push({ node: n.right });
      else if (n.type === "AssignmentExpression" && patternNames(n.left).includes(name)) sources.push({ node: n.right });
      for (const k of Object.keys(n)) {
        if (k === "parent") continue;
        const v = n[k];
        if (Array.isArray(v)) v.forEach((c) => c && typeof c.type === "string" && w(c, crossed));
        else if (v && typeof v.type === "string") w(v, crossed);
      }
    })(scope, false);
    return { declared, sources };
  }

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
      const info = bindingInfo(scope, name);
      if (info.declared) {
        return info.sources.flatMap((src) => src.at ? problem(src.at, src.why) : bad(src.elementOf || src.node, seen));
      }
      if (!f) break;
    }
    return problem(id, `${name} is not a known-safe variable`);
  }

  // Text and expression parts of a string built with a template literal and `+`.
  function flatten(node) {
    if (node.type === "Literal") return [{ text: String(node.value) }];
    if (node.type === "TemplateLiteral") {
      const out = [];
      node.quasis.forEach((q, i) => { out.push({ text: q.value.cooked ?? q.value.raw }); if (node.expressions[i]) out.push({ expr: node.expressions[i] }); });
      return out;
    }
    if (node.type === "BinaryExpression" && node.operator === "+") return [...flatten(node.left), ...flatten(node.right)];
    return [{ expr: node }];
  }
  const EVENT_ATTR_OPEN = /\son[a-z]+\s*=\s*(?:"[^"]*|'[^']*|[^\s"'>]*)$/i;
  const URL_ATTR_START = /\s(?:href|src|action|formaction|xlink:href|data|poster)\s*=\s*["']?$/i;
  const JS_URL_OPEN = /javascript:[^"']*$/i;
  function tagContext(acc) {
    const lt = acc.lastIndexOf("<");
    if (lt === -1 || acc.lastIndexOf(">") > lt) return null;   // not inside a tag
    const tag = acc.slice(lt);
    if (EVENT_ATTR_OPEN.test(tag)) return "a template expression inside an inline event handler (esc() is an HTML escape, not a JavaScript escape)";
    if (URL_ATTR_START.test(tag)) return "a template expression at the start of a URL attribute (it could be a javascript: URL)";
    if (JS_URL_OPEN.test(tag)) return "a template expression after javascript: in an attribute";
    return null;
  }
  function contextProblems(node) {
    let acc = "";
    const out = [];
    for (const part of flatten(node)) {
      if ("text" in part) { acc += part.text; continue; }
      const why = tagContext(acc);
      if (why) out.push(...problem(part.expr, why));
      acc += "\u0000";
    }
    return out;
  }

  function urlProblems(n, seen = new Set()) {
    if (!n || seen.has(n)) return [];
    seen = new Set(seen).add(n);
    const bare = (t) => /^\s*(javascript|data|vbscript):/i.test(t);
    if (n.type === "Literal") return bare(String(n.value)) ? problem(n, "a javascript: or data: URL") : [];
    if (n.type === "TemplateLiteral" && n.expressions.length === 0) return bare(n.quasis[0].value.cooked) ? problem(n, "a javascript: or data: URL") : [];
    if (n.type === "CallExpression" && n.callee.type === "MemberExpression" && !n.callee.computed
        && n.callee.object.type === "Identifier" && n.callee.object.name === "URL" && n.callee.property.name === "createObjectURL") return [];
    if (n.type === "BinaryExpression" && n.operator === "+") {
      const first = flatten(n)[0];
      if (first && "text" in first && /^(#|\/(?!\/))/.test(first.text)) return [];
    }
    if (n.type === "ConditionalExpression") return [...urlProblems(n.consequent, seen), ...urlProblems(n.alternate, seen)];
    if (n.type === "Identifier") {
      for (let f = enclosingFn(n); ; f = enclosingFn(f)) {
        if (f && paramIndex(f, n.name) >= 0) break;
        const info = bindingInfo(f || program, n.name);
        if (info.declared) return info.sources.flatMap((src) => src.node ? urlProblems(src.node, seen) : problem(n, "a URL taken from a loop or error variable"));
        if (!f) break;
      }
    }
    return problem(n, "a URL that is not a literal, a #fragment, a relative path or URL.createObjectURL(...)");
  }

  function bad(node, seen = new Set()) {
    if (!node) return [];
    if (seen.has(node)) return [];
    seen = new Set(seen).add(node);
    switch (node.type) {
      case "Literal": return [];
      case "TemplateLiteral": return [...contextProblems(node), ...node.expressions.flatMap((e) => bad(e, seen))];
      case "Identifier": return resolveIdent(node, seen);
      case "ConditionalExpression": return [...bad(node.consequent, seen), ...bad(node.alternate, seen)];
      case "LogicalExpression": return [...bad(node.left, seen), ...bad(node.right, seen)];
      case "BinaryExpression": return node.operator === "+" ? [...contextProblems(node), ...bad(node.left, seen), ...bad(node.right, seen)] : [];
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
      if (m === "replace" || m === "replaceAll") {
        const rp = node.arguments[1];
        const bring = rp && rp.type === "Literal" && /[<>"'&]/.test(String(rp.value)) ? problem(rp, "a replacement that re-introduces markup characters after escaping") : (rp && rp.type !== "Literal" ? bad(rp, seen) : []);
        return [...bad(c.object, seen), ...(node.arguments[0] ? bad(node.arguments[0], seen) : []), ...bring];
      }
      if (PASS_THROUGH_METHODS.has(m)) return [...bad(c.object, seen), ...node.arguments.flatMap((a) => bad(a, seen))];
      return problem(node, `.${m}() is not known to return safe text`);
    }
    return problem(node, "a call that is not known to return safe text");
  }

  const results = sinks.map((sk) => ({
    line: lineOf(sk.node),
    kind: sk.kind,
    problems: sk.kind === "const"
      ? (sk.value && sk.value.type === "Literal" ? [] : problem(sk.value || sk.node, "an event-handler or srcdoc attribute must be given a constant"))
      : sk.kind === "url" ? urlProblems(sk.value) : bad(sk.value),
  }));
  for (const [n, why] of pending) structure.push(...problem(n, why));

  // esc: exactly one binding, at the top level of the script, never reassigned, and it must entity-encode
  const topEsc = escBindings.filter((b) => b.top);
  for (const b of escBindings.filter((x) => !x.top)) {
    structure.push(...problem(b.node, "esc is bound or assigned again, or a parameter, catch or loop variable is named esc: only the one top-level esc is trusted"));
  }
  if (topEsc.length > 1) structure.push(...problem(topEsc[1].node, "esc is declared more than once at the top level"));
  let escCheck = { found: false };
  if (topEsc.length) {
    const b = topEsc[0].node;
    const fnNode = b.type === "FunctionDeclaration" ? b : b.init;
    const isDecl = b.type === "FunctionDeclaration";
    const src = isDecl ? `(${code.slice(fnNode.start, fnNode.end)})` : `(${code.slice(fnNode.start, fnNode.end)})`;
    const fn = vm.runInNewContext(src);
    const out = String(fn(`<img src=x onerror="a">'&`));
    escCheck = { found: true, out, clean: !/[<>"']/.test(out) && !/&(?![#\w]+;)/.test(out) };
  }
  return { sinks: results, structure, escCheck, escTop: topEsc.length };
}

const JS_TYPES = new Set(["", "module", "text/javascript", "application/javascript", "application/x-javascript",
  "application/ecmascript", "application/x-ecmascript", "text/ecmascript", "text/x-ecmascript", "text/x-javascript",
  "text/jscript", "text/livescript", "text/javascript1.0", "text/javascript1.1", "text/javascript1.2",
  "text/javascript1.3", "text/javascript1.4", "text/javascript1.5"]);
function attrValue(attrs, name) {
  const m = new RegExp(`(?:^|\\s)${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s"'>]+))`, "i").exec(attrs);
  return m ? (m[1] ?? m[2] ?? m[3] ?? "") : null;
}
const scripts = [], skipped = [];
for (const m of html.matchAll(/<script\b((?:"[^"]*"|'[^']*'|[^>])*)>([\s\S]*?)<\/script>/gi)) {
  const type = attrValue(m[1], "type");
  const src = attrValue(m[1], "src");
  const t = (type ?? "").trim().toLowerCase();
  if (src !== null) skipped.push({ type: t, why: "external script (src), not audited" });
  else if (!JS_TYPES.has(t)) skipped.push({ type: t, why: "not a JavaScript type" });
  else scripts.push({ code: m[2], line0: html.slice(0, m.index + m[0].indexOf(">") + 1).split("\n").length - 1 });
}
const all = scripts.map(audit);
console.log(JSON.stringify({
  scripts: scripts.length,
  skipped,
  sinks: all.flatMap((a) => a.sinks),
  structure: [...all.flatMap((a) => a.structure),
    ...(all.filter((a) => a.escTop > 0).length > 1 ? [{ line: 0, text: "esc", why: "esc is declared at the top level of more than one script" }] : [])],
  escChecks: all.map((a) => a.escCheck).filter((e) => e.found),
}));
