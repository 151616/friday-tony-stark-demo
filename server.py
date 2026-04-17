"""
Friday MCP Server — Entry Point
Default transport is stdio (used by agent_friday.py as an embedded subprocess).
Pass --sse to expose the same tools over SSE for external clients.

Run:
  python server.py              # stdio (for agent)
  python server.py --sse        # sse on default port
"""

import sys

from mcp.server.fastmcp import FastMCP
from friday.tools import register_all_tools
from friday.prompts import register_all_prompts
from friday.resources import register_all_resources

# Create the MCP server instance
mcp = FastMCP(
    name="Friday",
    instructions=(
        "You are Friday, a Tony Stark-style AI assistant. "
        "You have access to a set of tools to help the user. "
        "Be concise, accurate, and a little witty."
    ),
)

# Register tools, prompts, and resources
register_all_tools(mcp)
register_all_prompts(mcp)
register_all_resources(mcp)


def main():
    # Default transport is stdio so agent_friday.py can spawn this module
    # as an MCPServerStdio subprocess without any port / URL config.
    transport = "stdio"
    if "--sse" in sys.argv:
        transport = "sse"
    elif "--streamable-http" in sys.argv:
        transport = "streamable-http"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
