"""stdio entry points. ``ffmcp-read`` is the default deployment: Tier 1 tools only, no operator identity, no write flag.

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
from field_mcp.client import Upstream
from field_mcp.config import Config, ConfigError, load
from field_mcp.tools import Dispatcher, ToolSpec


def build_dispatcher(cfg: Config) -> Dispatcher:
    ups = {svc: Upstream(svc, sc.base, sc.key) for svc, sc in cfg.services.items()}
    # the write path exists only in a Tier 2 configuration, and only for a service that has its own write key
    writers = {svc: Upstream(svc, sc.base, sc.write_key) for svc, sc in cfg.services.items()
               if cfg.tier >= 2 and sc.write_key}
    return Dispatcher(cfg, ups, writers)


def _annotations(spec: ToolSpec) -> types.ToolAnnotations:
    if spec.tier == 1:
        return types.ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
    return types.ToolAnnotations(read_only_hint=False, destructive_hint=spec.tool.effect.endswith("irreversible"),
                                 idempotent_hint=False, open_world_hint=spec.tool.action == "regwatch_check")


def _client_name(ctx) -> str:
    """The client's self-declared name (unauthenticated: a label for the audit row, not an identity)."""
    try:
        return str(ctx.session.client_params.client_info.name)[:100] or "unknown"
    except Exception:
        return "unknown"


def build_server(disp: Dispatcher) -> Server:
    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(name=s.name, description=s.description, input_schema=s.input_schema, annotations=_annotations(s))
            for s in disp.list_tools()])

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        result = await anyio.to_thread.run_sync(disp.call, params.name, params.arguments, _client_name(ctx))
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
    """Tier 1 tools, plus the eight Tier 2 tools when FFMCP_ENABLE_WRITES is exactly 1 (otherwise exactly Tier 1)."""
    _main(2)
