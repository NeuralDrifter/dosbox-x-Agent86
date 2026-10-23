---
name: dos
description: Execute a command directly inside the DOSBox-X environment
argument-hint: [command]
---

Execute the following command inside DOSBox-X using this plugin's `run_dos_command` tool.

Command: `$ARGUMENTS`

## Calling the tool

The tool ships with this plugin's `dos-bridge` MCP server, so Claude Code namespaces
it. Call whichever `run_dos_command` entry appears in your available tools — expect
the form `mcp__plugin_dos-bridge_dos-bridge__run_dos_command`
(`mcp__plugin_<plugin>_<server>__<tool>`), but trust your tool list over this note.

If no such tool is available, do not guess at a name or open a socket yourself. Tell
the user to:

1. Run `CTTY BRIDGE` at the DOS prompt inside DOSBox-X.
2. Confirm `[dos] bridge_port` in the DOSBox-X config matches `DOS_BRIDGE_PORT`
   (both default to `8090`).
3. Confirm the `dos-bridge` MCP server started with this plugin enabled.

## Reporting the result

Wait for the command to finish, then show its DOS output. The transport strips its
own private completion marker, so the output needs no cleanup.

A timeout or transport error is an **unknown completion state**, not a failure — the
command may have already run. Report it as unknown and inspect DOS state before
retrying. Never automatically retry a state-changing command.
