"""Hello-world ChatGPT MCP server.

Uses the Python MCP SDK v2, which speaks protocol 2026-07-28
(server/discover, resultType) and still accepts the older initialize handshake.
"""

from __future__ import annotations

import os

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

INSTRUCTIONS = "Connectivity probe. Call hello with an optional name."

mcp = MCPServer("chatgpt-mcp-hello", instructions=INSTRUCTIONS)


@mcp.tool()
def hello(name: str = "world") -> str:
    """Return a greeting. Use this to verify the ChatGPT MCP connection."""
    return f"Hello, {name}!"


@mcp.custom_route("/", methods=["GET"])
async def health(_request: Request) -> Response:
    return JSONResponse({"ok": True, "mcp": "/mcp"})


if __name__ == "__main__":
    # Public hostname is not localhost. DNS-rebinding protection would 421
    # every Render request until that host is allowlisted.
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
