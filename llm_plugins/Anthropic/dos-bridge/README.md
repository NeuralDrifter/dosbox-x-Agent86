# DOSBox-X MCP Bridge — Claude Code plugin

This plugin connects Claude Code to the DOSBox-X `CTTY BRIDGE` device over
loopback TCP, so Claude can run DOS commands and write DOS text files natively
inside the emulator.

It ships:

- an MCP server (`dos-bridge`) exposing `run_dos_command`, `write_dos_file`,
  and `release_dos_console`
- a `/dos` slash command for one-off DOS commands
- two skills:
  - `dos-development` — DOS discovery, editing, compilation, and execution
  - `dos-tsr-development` — Borland/Turbo C real-mode resident utilities,
    SideKick-style popups, interrupt safety, and deterministic unloading

## Requirements

- A DOSBox-X build containing the `BRIDGE` device.
- Python 3.10 or newer with the `mcp` package installed.
- Matching port settings on DOSBox-X and the MCP process.

Confirm the Python dependency before installing:

```powershell
python -c "import mcp; print('MCP is available')"
```

## DOSBox-X configuration

The relevant `[dos]` settings are:

```ini
bridge_port = 8090
automount_c = false
```

`bridge_port = 0` disables the listener. Keep `automount_c = false` unless you
deliberately intend to expose the host C: drive.

At the DOS prompt, activate the device manually:

```dos
CTTY BRIDGE
```

The listener starts only after that command succeeds. Restore the normal DOS
console and close the bridge listener with:

```dos
CTTY CON
```

The MCP `release_dos_console` tool performs the same handoff. If the client
disconnects, DOSBox-X automatically restores `CON`; a DOSBox-X reset also
clears bridge-only restrictions.

## Installation

This plugin is published through the `dosbox-x-plugins` marketplace defined in
the parent directory (`../.claude-plugin/marketplace.json`).

Validate, register the marketplace, then install. Run these from this plugin's
root directory (the one containing this README), so `.` is the plugin and `..`
is the marketplace:

```powershell
claude plugin validate . --strict          # this plugin
claude plugin validate .. --strict         # the marketplace + this entry
claude plugin marketplace add ..
claude plugin install dos-bridge@dosbox-x-plugins
```

Restart Claude Code, then confirm the `dos-bridge` MCP server is connected and
that `/dos` and both skills are listed:

```powershell
claude plugin details dos-bridge
```

Installing **copies** the plugin into Claude Code's cache, so later edits here
do not take effect until you run `claude plugin update dos-bridge`.

### Tool names

Claude Code namespaces tools from a plugin-shipped MCP server, so the tools
appear qualified — expect the form `mcp__plugin_<plugin>_<server>__<tool>`:

- `mcp__plugin_dos-bridge_dos-bridge__run_dos_command`
- `mcp__plugin_dos-bridge_dos-bridge__write_dos_file`
- `mcp__plugin_dos-bridge_dos-bridge__release_dos_console`

The skills instruct Claude to use whatever name is actually present in its tool
list, so a rename of the plugin or the server does not break them.

## Runtime configuration

The MCP process accepts these environment variables:

- `DOS_BRIDGE_PORT`: loopback port, default `8090`. It must match
  DOSBox-X `bridge_port`.

The command tool has a fixed 60-second MCP timeout. A timeout or transport
failure leaves command completion unknown; inspect DOS state before retrying a
state-changing command.

## DOS execution model

Treat the DOS guest as single-tasking. Only one foreground DOS command or
program executes at a time, and the MCP server serializes requests. Do not
attempt concurrent or background DOS commands. TSR utilities can temporarily
interrupt a foreground program, but they do not provide general-purpose
parallel execution. If a program does not return to the DOS prompt, the bridge
command may time out with an unknown completion state.

## Safety model

- The TCP listener binds only to `127.0.0.1`.
- The MCP server serializes requests through one persistent connection.
- Commands and output are bounded, and text uses DOS code page 437.
- The file-writing tool accepts only absolute DOS 8.3 paths on drives already
  mounted by the user.
- The command and file-writing tools can modify any drive already mounted in
  DOSBox-X. Mounting new host paths remains governed separately by DOSBox-X's
  operator-controlled bridge policy. A mounted host directory is not an
  isolated sandbox.
- Do not probe or switch to unconfirmed host-backed drives. Run `MOUNT` once to
  inspect the mappings already exposed by the user.

## Tests

Run the transport tests without connecting to DOSBox-X. Run from the plugin
root:

```powershell
python -m unittest discover -s tests -v
```

## Layout

```
.claude-plugin/plugin.json   plugin manifest
.mcp.json                    MCP server definition (${CLAUDE_PLUGIN_ROOT}-relative)
commands/dos.md              /dos slash command
scripts/bridge_client.py     hardened loopback bridge client
scripts/mcp_server.py        FastMCP server exposing the three tools
skills/                      dos-development, dos-tsr-development
tests/                       transport tests, no emulator required
```

`scripts/` and `tests/` are shared verbatim with the other vendor distributions
under `llm_plugins/` so an installed plugin stays self-contained. Nothing in this
plugin hardcodes an absolute path: the MCP server is located through
`${CLAUDE_PLUGIN_ROOT}`, and the tests locate `scripts/` relative to their own
file.
