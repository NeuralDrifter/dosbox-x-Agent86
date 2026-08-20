# Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter
"""Run one command through the hardened DOSBox-X bridge client."""

from pathlib import Path
import sys


def _locate_bridge_scripts() -> Path:
    """Locate any vendor distribution of the dos-bridge plugin's scripts/ dir.

    Resolved relative to this file so the helper works from any working
    directory, and matched by glob so it survives vendor-folder renames.
    """
    root = Path(__file__).resolve().parent
    pattern = "llm_plugins/*/dos-bridge/scripts/bridge_client.py"
    matches = sorted(root.glob(pattern))
    if not matches:
        raise SystemExit(
            f"Could not find {pattern} under {root}. "
            "Install or restore a dos-bridge plugin distribution."
        )
    return matches[0].parent


sys.path.insert(0, str(_locate_bridge_scripts()))

from bridge_client import BridgeError, DosBridgeClient  # noqa: E402


def main(arguments: list[str]) -> int:
    if not arguments:
        print("Usage: python dos_cmd.py <command>")
        return 2

    try:
        with DosBridgeClient() as client:
            print(client.run_command(" ".join(arguments)), end="")
    except (BridgeError, ValueError) as error:
        print(f"Bridge error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
