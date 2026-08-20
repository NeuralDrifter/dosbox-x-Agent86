# Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter
"""MCP tools for serialized access to the DOSBox-X CTTY BRIDGE."""

import atexit

from mcp.server.fastmcp import FastMCP

from bridge_client import DosBridgeClient

mcp = FastMCP("dos-bridge")
bridge_client = DosBridgeClient()
atexit.register(bridge_client.close)


@mcp.tool()
def run_dos_command(command: str) -> str:
    """Execute one command in DOS and return its bounded CP437 output."""
    return bridge_client.run_command(command)


@mcp.tool()
def write_dos_file(filename: str, content: str) -> str:
    """Write one CP437 text file to an allowed DOS drive using an 8.3 path."""
    return bridge_client.write_file(filename, content)


if __name__ == "__main__":
    mcp.run()
