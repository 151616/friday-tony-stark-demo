"""
Tool registry — imports and registers all tool modules with the MCP server.
Add new tool modules here as you build them.
"""

from friday.tools import web, system, utils, apps, media, messaging, audio, files


def register_all_tools(mcp):
    """Register all tool groups onto the MCP server instance."""
    web.register(mcp)
    system.register(mcp)
    utils.register(mcp)
    apps.register(mcp)
    media.register(mcp)
    messaging.register(mcp)
    audio.register(mcp)
    files.register(mcp)
