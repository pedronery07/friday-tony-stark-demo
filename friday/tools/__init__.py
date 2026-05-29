"""
Tool registry — imports and registers all tool modules with the MCP server.
Add new tool modules here as you build them.
"""

from friday.tools import web, system, utils, memory, weather, github_tool, calendar_tool, timers, spotify_tool, gmail_tool


def register_all_tools(mcp):
    """Register all tool groups onto the MCP server instance."""
    web.register(mcp)
    system.register(mcp)
    utils.register(mcp)
    memory.register(mcp)
    weather.register(mcp)
    github_tool.register(mcp)
    calendar_tool.register(mcp)
    timers.register(mcp)
    spotify_tool.register(mcp)
    gmail_tool.register(mcp)
