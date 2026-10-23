---
name: dos
description: Execute a command directly inside the DOSBox environment
argument-hint: [command]
---

Execute the following command inside DOSBox-X using the `mcp__dos-bridge__run_dos_command` tool. If the tool is unavailable, tell the user to activate `CTTY BRIDGE` in DOSBox-X and verify that the MCP server is running.

Command: `$ARGUMENTS`

Wait for the command to finish and show its DOS output. The transport removes its private completion marker automatically. A timeout has an unknown completion state, so do not automatically retry a state-changing command.
