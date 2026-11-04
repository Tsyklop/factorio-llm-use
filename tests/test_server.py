import json
import unittest

from mcp.server.mcpserver.exceptions import ToolError

from factorio_llm_use.bridge import BridgeError
from factorio_llm_use.server import create_server


class BoundaryBridge:
    def call(self, operation, params=None):
        if operation == "craft":
            raise BridgeError("Missing crafting ingredients")
        # A boundary double checks the transport contract. Real action outcomes
        # are covered by the executable engine suite, not by this double.
        return {"ok": True, "result": {"operation": operation, "params": params}}


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_schema_requires_explicit_ghost_mode(self):
        tools = await create_server(BoundaryBridge()).list_tools()
        tool = next(t for t in tools if t.name == "apply_plan")
        self.assertIn("mode", tool.input_schema["required"])
        self.assertEqual(tool.input_schema["properties"]["mode"]["const"], "ghosts")

    async def test_native_placement_parameters_cross_the_transport_boundary(self):
        result = await create_server(BoundaryBridge()).call_tool(
            "place_entity",
            {
                "item": "some-installed-mod-entity",
                "position": {"x": 2.5, "y": 8.5},
                "quality": "legendary",
            },
        )
        response = json.loads(result.content[0].text)
        self.assertEqual(response["result"]["params"]["item"], "some-installed-mod-entity")
        self.assertEqual(response["result"]["params"]["quality"], "legendary")
        self.assertNotIn("invoke", response["result"]["params"])

    async def test_game_error_remains_actionable_in_mcp(self):
        with self.assertRaisesRegex(ToolError, "Missing crafting ingredients"):
            await create_server(BoundaryBridge()).call_tool("craft", {"recipe": "iron-gear-wheel"})


if __name__ == "__main__":
    unittest.main()
