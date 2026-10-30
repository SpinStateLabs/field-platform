"""End to end over the real stdio transport with the installed SDK: the process lists 49 tools, calls one against the
stub, writes nothing to stdout but protocol lines, and the write entry point refuses to start in this build."""
import json
import os
import subprocess
import sys

from conftest import KEY, MARK, Stub

# the child must import the same field_mcp as the test (the mutation check points PYTHONPATH at a copy)
_PYPATH = {"PYTHONPATH": os.environ["PYTHONPATH"]} if "PYTHONPATH" in os.environ else {}


def run(stub, requests):
    env = {"PATH": os.environ.get("PATH", ""), **_PYPATH, "FFMCP_SEALED_LEDGER_URL": stub.base, "FFMCP_SEALED_LEDGER_KEY": KEY}
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"}, *requests]
    want = {m["id"] for m in msgs if "id" in m}
    proc = subprocess.Popen([sys.executable, "-c", "from field_mcp.server import main_read; main_read()"], env=env,
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


def _child(code, env):
    return subprocess.run([sys.executable, "-c", code], env={"PATH": os.environ.get("PATH", ""), **_PYPATH, **env},
                          capture_output=True, text=True, timeout=30)


def test_write_entry_point_refuses_without_the_flag_or_the_ledger():
    code = "from field_mcp.server import main_write; main_write()"
    p = _child(code, {})
    assert p.returncode == 2 and "FFMCP_ENABLE_WRITES" in p.stderr
    p = _child(code, {"FFMCP_ENABLE_WRITES": "1"})
    assert p.returncode == 2 and "FFMCP_SEALED_LEDGER_URL" in p.stderr


def test_write_process_over_stdio_lists_56_and_makes_an_audited_write(stub):
    ledger = Stub()
    ledger.routes[("POST", "/events")] = (201, {"event_id": 1}, {})
    stub.routes[("POST", "/agents")] = (201, {"agent_id": "agent-1"}, {})
    env = {"PATH": os.environ.get("PATH", ""), **_PYPATH, "FFMCP_ENABLE_WRITES": "1", "FFMCP_OPERATOR": "op-x",
           "FFMCP_OPERATOR_KEY": "opk-" + "A1b2" * 4, "FFMCP_AGENT_REGISTRY_URL": stub.base, "FFMCP_AGENT_REGISTRY_KEY": KEY,
           "FFMCP_SEALED_LEDGER_URL": ledger.base, "FFMCP_SEALED_LEDGER_KEY": KEY}
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe-client", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "agent_registry_create_agent", "arguments": {
            "body": {"agent_id": "agent-1", "name": "A", "owner": "o"}, "reason": "stdio test"}}}]
    proc = subprocess.Popen([sys.executable, "-c", "from field_mcp.server import main_write; main_write()"], env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    got, out = {}, ""
    try:
        for m in msgs:
            proc.stdin.write(json.dumps(m) + "\n")
            proc.stdin.flush()
        while {1, 2, 3} - set(got):
            line = proc.stdout.readline()
            if not line:
                break
            out += line
            got[json.loads(line).get("id")] = json.loads(line)
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    err = proc.stderr.read()
    tools = got[2]["result"]["tools"]
    assert len(tools) == 56
    ann = {t["name"]: t["annotations"]["readOnlyHint"] for t in tools}
    assert ann["agent_registry_create_agent"] is False and ann["sealed_ledger_verify"] is True
    res = json.loads(got[3]["result"]["content"][0]["text"])
    assert res["status"] == "ok" and res["audit"]["outcome"] == "recorded"
    intent = json.loads(ledger.requests[0]["body"])["payload"]
    assert intent["client_name"] == "probe-client" and intent["operator"] == "op-x"
    assert stub.requests[0]["headers"]["x-field-operator"] == "op-x"
    assert "opk-" not in out + err and KEY not in out + err
    ledger.close()
