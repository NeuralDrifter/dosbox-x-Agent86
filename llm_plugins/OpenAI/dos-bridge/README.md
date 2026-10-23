# DOSBox-X Bridge for Codex

This is the standalone Codex distribution of the DOSBox-X MCP bridge. It
contains its own runtime, tests, and skills so an installed plugin does not
depend on the Antigravity package remaining at a particular path.

## Included capabilities

- Serialized DOS command execution over loopback TCP.
- Bounded CP437 output and fixed MCP command timeouts.
- DOS 8.3 text-file writes to any drive already mounted by the user.
- Explicit console release plus automatic recovery after client disconnects.
- `dos-development` guidance for discovery, Borland development, and testing.
- `dos-tsr-development` guidance for interrupt-safe resident utilities and
  SideKick-style popup architecture.

## Requirements

- A DOSBox-X build containing the `BRIDGE` device.
- Python 3.10 or newer.
- Matching DOSBox-X `bridge_port` and MCP `DOS_BRIDGE_PORT` values.

## Install the MCP command

Install this directory as a Python package before installing or enabling the
Codex plugin. From the directory containing this README, run:

```powershell
python -m pip install .
```

That command installs the `mcp` dependency and creates the portable
`dos-bridge-mcp` console command used by `.mcp.json`. Confirm that the command
is visible without connecting to DOSBox-X:

```powershell
python -c "import shutil; assert shutil.which('dos-bridge-mcp'), 'dos-bridge-mcp is not on PATH'"
```

The Python interpreter's scripts directory must be on `PATH` for Codex. Using
an isolated environment is supported, but Codex must be launched with that
environment's scripts directory on `PATH`.

## Install the Codex plugin

This repository includes a local Codex marketplace one directory above this
plugin. From the directory containing this README, run:

```powershell
codex plugin marketplace add ..
codex plugin add dos-bridge@dosbox-x-openai
```

Then restart the ChatGPT desktop app. The marketplace may be cloned or moved;
the MCP configuration does not refer to the source or cache directory.

## DOSBox-X activation

Keep these `[dos]` defaults unless exposure is intentional:

```ini
bridge_port = 8090
automount_c = false
```

Activate the listener manually at the DOS prompt with `CTTY BRIDGE`. Restore
the local console and close the listener with `CTTY CON` or the MCP
`release_dos_console` tool. A client disconnect also restores `CON`
automatically, and a DOSBox-X reset clears bridge restrictions.

## Runtime configuration

- `DOS_BRIDGE_PORT`: loopback port, default `8090`.

The command and file-writing tools can modify any drive already mounted in
DOSBox-X. Mounting new host paths remains governed separately by DOSBox-X's
operator-controlled bridge policy. Mounted host directories are not an
isolated sandbox.

## Codex approvals

The command and file-writing tools advertise that they can mutate or destroy
data. This is intentional: DOS commands and file writes can affect directories
mounted from the host. The console-release tool is non-destructive and
idempotent. Keep Codex tool approval prompts enabled and approve mutations only
after checking their command, target drive, and path.

## Execution model

Treat the DOS guest as single-tasking. The MCP server serializes requests, so
do not attempt parallel or background DOS commands. TSRs can temporarily
interrupt a foreground application, but they do not provide general-purpose
multitasking. A timeout leaves command completion unknown.

## Development checks

Validate the package and run its transport tests without using the live
bridge. Run these from this plugin's root directory (the one containing
this README). `validate_plugin.py` ships with the Codex `plugin-creator`
system skill, typically under
`<codex-home>\skills\.system\plugin-creator\scripts\`:

```powershell
python <path-to>\validate_plugin.py .
python -m unittest discover -s tests -v
```
