# Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter
"""MCP tools for serialized access to the DOSBox-X CTTY BRIDGE."""

import atexit

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bridge_client import DosBridgeClient

mcp = FastMCP("dos-bridge")
bridge_client = DosBridgeClient()
atexit.register(bridge_client.close)

MUTATING_DOS_TOOL_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)
CONSOLE_CONTROL_TOOL_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=MUTATING_DOS_TOOL_ANNOTATIONS)
def run_dos_command(command: str) -> str:
    """Execute one command in DOS and return its bounded CP437 output."""
    return bridge_client.run_command(command)


@mcp.tool(annotations=MUTATING_DOS_TOOL_ANNOTATIONS)
def write_dos_file(filename: str, content: str) -> str:
    """Write one CP437 text file to a mounted DOS drive using an 8.3 path."""
    return bridge_client.write_file(filename, content)


@mcp.tool(annotations=CONSOLE_CONTROL_TOOL_ANNOTATIONS)
def release_dos_console() -> str:
    """End the bridge session and restore the local DOSBox-X console."""
    return bridge_client.release_console()


if __name__ == "__main__":
    mcp.run()
