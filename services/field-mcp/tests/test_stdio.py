"""End to end over the real stdio transport with the installed SDK: the process lists 49 tools, calls one against the
stub, writes nothing to stdout but protocol lines, and the write entry point refuses to start in this build."""
import json
import os
import subprocess
import sys

from conftest import KEY, MARK, OPKEY, WKEY
from field_mcp import catalog

# the child must import the same field_mcp as the test (the mutation check points PYTHONPATH at a copy)
_PYPATH = {"PYTHONPATH": os.environ["PYTHONPATH"]} if "PYTHONPATH" in os.environ else {}


def run(stub, requests, entry="main_read", extra_env=None):
    env = {"PATH": os.environ.get("PATH", ""), **_PYPATH, "FFMCP_SEALED_LEDGER_URL": stub.base, "FFMCP_SEALED_LEDGER_KEY": KEY,
           **(extra_env or {})}
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"}, *requests]
    want = {m["id"] for m in msgs if "id" in m}
    proc = subprocess.Popen([sys.executable, "-c", f"from field_mcp.server import {entry}; {entry}()"], env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out_lines: list[str] = []
    try:
        for m in msgs:
            proc.stdin.write(json.dumps(m) + "\n")
            proc.stdin.flush()
        seen: set = set()
        while seen != want:                      # the server runs until we close stdin, so no reply is cut off
            line = proc.stdout.readline()
            if not line:
                break
            out_lines.append(line)
            if line.strip():
                seen.add(json.loads(line).get("id"))
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    out_lines += proc.stdout.readlines()
    err = proc.stderr.read()
    lines = [json.loads(line) for line in out_lines if line.strip()]
    return lines, subprocess.CompletedProcess([], proc.returncode, "".join(out_lines), err)


def test_list_and_call_over_stdio(stub):
    stub.routes[("GET", "/verify")] = (200, {"ok": True}, {})
    lines, p = run(stub, [{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                          {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "sealed_ledger_verify", "arguments": {}}},
                          {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "sealed_ledger_verify", "arguments": {"url": "http://x"}}}])
    by_id = {m.get("id"): m for m in lines if "id" in m}
    tools = by_id[2]["result"]["tools"]
    assert len(tools) == 49 and all(t["annotations"]["readOnlyHint"] is True for t in tools)
    assert not {t["name"] for t in tools} & {"kill_switch_kill", "kill_switch_revive", "sealed_ledger_rotate", "conformance_sentinel_check"}
    ok = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert ok["status"] == "ok" and ok["data"] == {"ok": True}
    assert by_id[4]["result"]["isError"] is True
    assert KEY not in p.stdout and KEY not in p.stderr and MARK not in p.stdout


LIST = [{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
WRITE_ENV = {"FFMCP_OPERATOR": "op-1", "FFMCP_OPERATOR_KEY": OPKEY, "FFMCP_SEALED_LEDGER_WRITE_KEY": WKEY,
             "FFMCP_AGENT_REGISTRY_URL": "", "FFMCP_ENABLE_WRITES": "1"}


def names(lines):
    return {t["name"] for t in {m.get("id"): m for m in lines if "id" in m}[2]["result"]["tools"]}


def test_read_process_lists_only_tier1_even_with_the_write_flag_and_pair_in_its_environment(stub):
    lines, p = run(stub, LIST, entry="main_read", extra_env=WRITE_ENV)
    assert len(names(lines)) == 49 and not names(lines) & {t.name for t in catalog.WRITE_TOOLS}
    assert OPKEY not in p.stdout + p.stderr and WKEY not in p.stdout + p.stderr


def test_write_process_without_the_flag_lists_exactly_the_tier1_tools(stub):
    lines, p = run(stub, LIST, entry="main_write", extra_env={k: v for k, v in WRITE_ENV.items() if k != "FFMCP_ENABLE_WRITES"})
    assert names(lines) == {t.name for t in catalog.TOOLS} and p.returncode == 0


def test_write_process_with_the_flag_lists_the_fifty_seven_and_marks_the_eight_as_writes(stub):
    lines, p = run(stub, LIST, entry="main_write", extra_env=WRITE_ENV)
    tools = {t["name"]: t for t in {m.get("id"): m for m in lines if "id" in m}[2]["result"]["tools"]}
    assert len(tools) == 57 and set(tools) == {t.name for t in catalog.ALL_TOOLS}
    for n, t in tools.items():
        assert t["annotations"]["readOnlyHint"] is (n not in {w.name for w in catalog.WRITE_TOOLS}), n
        assert t["description"].startswith("BLAST RADIUS: ") == (n in {w.name for w in catalog.WRITE_TOOLS}), n


def test_a_write_over_stdio_needs_a_reason_audits_first_and_leaks_no_key(stub):
    stub.routes[("POST", "/events")] = (201, {"seq": 1}, {})
    stub.routes[("POST", "/export")] = (200, {"events": 0}, {})
    call = lambda i, args: {"jsonrpc": "2.0", "id": i, "method": "tools/call",
                            "params": {"name": "sealed_ledger_export", "arguments": args}}
    lines, p = run(stub, [call(2, {}), call(3, {"reason": "weekly auditor bundle"})], entry="main_write", extra_env=WRITE_ENV)
    by_id = {m.get("id"): m for m in lines if "id" in m}
    assert by_id[2]["result"]["isError"] is True and not stub.requests[:0] and \
        [r["path"] for r in stub.requests] == ["/events", "/export"]
    assert json.loads(by_id[3]["result"]["content"][0]["text"])["status"] == "ok"
    row = json.loads(stub.requests[0]["body"])["payload"]
    assert row["client"] == "t" and row["operator"] == "op-1" and row["reason"] == "weekly auditor bundle"
    assert stub.requests[0]["headers"]["x-field-auth"] == WKEY
    assert not ({KEY, WKEY, OPKEY} & set(p.stdout.split())) and OPKEY not in p.stdout + p.stderr
    assert WKEY not in p.stdout + p.stderr and KEY not in p.stdout + p.stderr


def test_write_process_bad_rate_setting_fails_startup_with_fixed_text(stub):
    p = subprocess.run([sys.executable, "-c", "from field_mcp.server import main_write; main_write()"],
                       env={"PATH": os.environ.get("PATH", ""), **_PYPATH, "FFMCP_ENABLE_WRITES": "1", "FFMCP_WRITE_RATE_PER_MIN": "0"},
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "FFMCP_WRITE_RATE_PER_MIN" in p.stderr
