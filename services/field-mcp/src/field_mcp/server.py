"""stdio entry points. ``ffmcp-read`` is the default deployment: Tier 1 tools only, no operator identity, no write flag.
``ffmcp-write`` adds the Tier 2 tools and needs the write flag, an audit ledger and (if the services arm it) an operator pair.

The Claude client launches this process and talks over stdin/stdout; there is no listening port. Nothing is written to
stdout except the protocol; diagnostics go to stderr and never carry a configuration value.
"""
from __future__ import annotations

import json
import sys

import anyio
import mcp_types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from field_mcp import __version__
from field_mcp.audit import Audit
from field_mcp.client import Upstream
from field_mcp.config import Config, ConfigError, load
from field_mcp.tools import Dispatcher


def build_dispatcher(cfg: Config) -> Dispatcher:
    ups = {svc: Upstream(svc, sc.base, sc.key) for svc, sc in cfg.services.items()}
    audit = Audit(ups.get("sealed-ledger"), cfg.operator, signer=cfg.caller) if cfg.tier >= 2 else None
    return Dispatcher(cfg, ups, audit)


def _client_name(ctx) -> str:
    """The client's self-declared name from the initialize request (unauthenticated; for the audit record only)."""
    try:
        return str(ctx.session.client_params.client_info.name)
    except Exception:
        return ""


def build_server(disp: Dispatcher) -> Server:
    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        def ann(tier: int) -> types.ToolAnnotations:
            return types.ToolAnnotations(read_only_hint=tier < 2, destructive_hint=False, open_world_hint=False)
        return types.ListToolsResult(tools=[
            types.Tool(name=s.name, description=s.description, input_schema=s.input_schema, annotations=ann(s.tier))
            for s in disp.list_tools()])

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        if disp.audit is not None and not disp.audit.client_name:
            disp.audit.client_name = _client_name(ctx)
        result = await anyio.to_thread.run_sync(disp.call, params.name, params.arguments)
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result))],
                                    is_error=result.get("status") != "ok")

    return Server("field-mcp", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def _serve(server: Server) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def _main(tier: int) -> None:
    try:
        cfg = load(tier)
    except ConfigError as exc:
        print(f"field-mcp: {exc}", file=sys.stderr)    # fixed text naming a variable, never a value
        raise SystemExit(2) from None
    anyio.run(_serve, build_server(build_dispatcher(cfg)))


def main_read() -> None:
    _main(1)


def main_write() -> None:
    """Tier 1 + Tier 2. Refuses to start without ``FFMCP_ENABLE_WRITES=1`` and a configured sealed ledger (audit)."""
    _main(2)
