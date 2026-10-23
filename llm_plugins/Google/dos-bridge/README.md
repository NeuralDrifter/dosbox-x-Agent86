# DOSBox-X MCP Bridge

This package connects an MCP-capable agent to the DOSBox-X `CTTY BRIDGE`
device over loopback TCP. It supports Antigravity natively and retains the
Claude Code plugin files for compatibility.

It includes two optional agent skills:

- `dos-development` for ordinary DOS discovery, editing, compilation, and
  execution through the bridge.
- `dos-tsr-development` for Borland/Turbo C real-mode resident utilities,
  SideKick-style popups, interrupt safety, and deterministic unloading.

## Requirements

- The DOSBox-X build containing the `BRIDGE` device.
- Python 3.10 or newer with the `mcp` package installed.
- Matching port settings on DOSBox-X and the MCP process.

Confirm the Python dependency before installing the plugin:

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

## Antigravity installation

Validate and install this directory with the Antigravity CLI. Run these
from this plugin's root directory (the one containing this README):

```powershell
agy plugin validate .
agy plugin install .
```

Restart Antigravity after installation, then confirm that the `dos-bridge` MCP
server and `dos-development` skill are available.

## Claude Code compatibility

The `.claude-plugin/plugin.json`, `.mcp.json`, and `commands/` files retain the
Claude Code package layout. Claude qualifies the MCP tools as:

- `mcp__dos-bridge__run_dos_command`
- `mcp__dos-bridge__write_dos_file`
- `mcp__dos-bridge__release_dos_console`

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

Run the transport tests without connecting to DOSBox-X. Run this from
this plugin's root directory:

```powershell
python -m unittest discover -s tests -v
```
