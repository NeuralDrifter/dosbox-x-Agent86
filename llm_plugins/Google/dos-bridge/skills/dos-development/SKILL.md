---
name: dos-development
description: Instructs the agent on how to write code, discover compilers, and execute commands natively inside MS-DOS via the DOSBox-X TCP bridge. Use this skill when asked to interact with DOS, compile C/C++ or Basic code in DOS, or explore the DOS environment.
version: 1.2.0
---

# DOSBox-X Development Bridge

You are equipped with an MCP integration to a DOSBox-X emulator running DOS. It exposes two tools through the `dos-bridge` MCP server:

- `run_dos_command(command: str)`
- `write_dos_file(filename: str, content: str)`

The host may qualify these names. For example, Claude Code exposes `run_dos_command` as `mcp__dos-bridge__run_dos_command`.

## Activation and configuration

- The user must run `CTTY BRIDGE` at the DOS prompt before an MCP client can connect. Do not attempt to activate it through TCP.
- The listener binds to loopback only. Its DOSBox-X `[dos]` `bridge_port` setting defaults to `8090`; `bridge_port = 0` disables it.
- The MCP process uses `DOS_BRIDGE_PORT`, also defaulting to `8090`. Both port settings must match.
- `CTTY CON` restores the normal DOS console and closes the bridge listener.
- `DOS_BRIDGE_WRITE_DRIVES` controls the dedicated write tool's allowed drives and defaults to `A`.

## Workflow for DOS Tasks

Treat the DOS guest as single-tasking. Only one foreground command or program
executes at a time, and the MCP server serializes requests. Do not attempt
parallel or background DOS commands. TSR utilities may interrupt a foreground
program, but they are not general-purpose multitasking. Use the separate
`dos-tsr-development` skill only when resident interrupt-driven behavior is
actually requested.

1. **Environment Discovery:**
   Do NOT assume where the compiler (Borland C++, Turbo C, QBasic, MASM) is located, or even what drives are mounted.
   When asked to compile or explore, start by exploring the environment:
   - Run `mount` once to discover the drives already exposed to DOS. Do not probe absent host drives.
   - Check the `PATH` variable using `run_dos_command("set")`.
   - Look for standard installation directories (e.g., `TC\BIN`, `BORLANDC`, `BC5`).

2. **Writing Code:**
   You MUST write files *inside* the DOS environment to remain authentic unless requested otherwise.
   - Use `write_dos_file(filename, content)` to stream code via `copy con` directly to DOS.
   - Use an absolute path on an allowed drive and keep every component in 8.3 format (for example, `A:\\PROGRAM.C`). Writes default to `A:` only.

3. **Compiling:**
   - Compiling inside an emulator takes time. MCP command calls have a fixed 60-second timeout.
   - Use the compiler discovered from `PATH` or the mounted development drive; do not assume it is on C:.
   - Look for a `BUILD.BAT` in the directory first before constructing your own compile commands.

4. **Testing and Execution:**
   - Execute the compiled `.EXE` or `.COM` file using `run_dos_command("PROGRAM.EXE")`.
   - The tool returns bounded CP437 output over the loopback TCP bridge.

5. **Connection Discipline:**
   - Use only the MCP tools; do not open parallel or ad-hoc TCP connections to the configured bridge port.
   - The MCP server serializes calls over one persistent connection. Wait for each tool call to finish before issuing another.
   - A timeout or transport error is an unknown completion state. Inspect DOS state before retrying a state-changing command.

Remember: You are operating natively inside an MS-DOS prompt. Standard DOS commands (`dir`, `del`, `type`, `copy`, `ren`) apply. Avoid Unix tools (`ls`, `rm`, `cat`).

## ⚠️ CRITICAL SECURITY WARNING
**DO NOT ASSUME THIS IS A FULLY ISOLATED SANDBOX.**
DOSBox-X allows users to explicitly mount folders from the host operating system into the DOS environment.
Any files you modify, delete, or overwrite while working in these mounted DOS drives will permanently alter the files on the user's actual host PC!
**ALWAYS** double-check what drive you are in (e.g., using `dir` and paying attention to folder contents) and proceed with extreme caution before executing destructive commands.

The dedicated `write_dos_file` tool is drive-restricted, but `run_dos_command` can still modify any drive already mounted in DOSBox-X. Keep `automount_c = false`, never probe unconfirmed drives, and never automatically retry a destructive command after a timeout.
