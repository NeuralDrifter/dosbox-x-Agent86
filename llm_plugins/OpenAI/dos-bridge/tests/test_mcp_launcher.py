# Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import mcp_server  # noqa: E402


class McpPackagingTests(unittest.TestCase):
    def test_plugin_config_uses_installed_console_command(self):
        config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["dos-bridge"]

        self.assertEqual(server["command"], "dos-bridge-mcp")
        self.assertEqual(server["args"], [])
        self.assertNotIn("cwd", server)

    def test_repository_marketplace_points_to_plugin(self):
        marketplace_root = PLUGIN_ROOT.parent
        manifest_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugin = next(item for item in manifest["plugins"] if item["name"] == "dos-bridge")

        self.assertEqual(manifest["name"], "dosbox-x-openai")
        self.assertEqual(plugin["source"]["source"], "local")
        self.assertEqual(
            (marketplace_root / plugin["source"]["path"]).resolve(),
            PLUGIN_ROOT.resolve(),
        )

    def test_console_entrypoint_runs_stdio_server(self):
        with patch.object(mcp_server.mcp, "run") as run:
            mcp_server.main()

        run.assert_called_once_with()

    def test_mutating_tools_report_destructive_annotations(self):
        for tool_name in ("run_dos_command", "write_dos_file"):
            with self.subTest(tool=tool_name):
                tool = mcp_server.mcp._tool_manager.get_tool(tool_name)

                self.assertIsNotNone(tool)
                self.assertFalse(tool.annotations.readOnlyHint)
                self.assertTrue(tool.annotations.destructiveHint)
                self.assertFalse(tool.annotations.idempotentHint)
                self.assertFalse(tool.annotations.openWorldHint)

    def test_release_tool_reports_nondestructive_annotations(self):
        tool = mcp_server.mcp._tool_manager.get_tool("release_dos_console")

        self.assertIsNotNone(tool)
        self.assertFalse(tool.annotations.readOnlyHint)
        self.assertFalse(tool.annotations.destructiveHint)
        self.assertTrue(tool.annotations.idempotentHint)
        self.assertFalse(tool.annotations.openWorldHint)


if __name__ == "__main__":
    unittest.main()
