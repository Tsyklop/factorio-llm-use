"""MCP entry point. Game mechanics and persistent state live in the companion mod."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .bridge import Bridge, BridgeError


def create_server(bridge: Bridge) -> MCPServer:
    server = MCPServer("Factorio LLM Use")

    async def invoke(operation: str, params: dict[str, Any] | None = None) -> str:
        try:
            result = await asyncio.to_thread(bridge.call, operation, params)
        except (BridgeError, OSError) as exc:
            raise ToolError(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False)

    @server.tool()
    async def factorio_ping() -> str:
        """Check the connection, game version and supported operations."""
        return await invoke("ping")

    @server.tool()
    async def get_world() -> str:
        """List surfaces, sandbox surfaces, players, forces and simulation state."""
        return await invoke("world")

    @server.tool()
    async def get_agent_status() -> str:
        """Read the independent AI character's actual inventory, position and action."""
        return await invoke("agent_status")

    @server.tool()
    async def observe(
        surface: str = "nauvis",
        area: dict[str, Any] | None = None,
        position: dict[str, float] | None = None,
        radius: float = 32,
        names: list[str] | None = None,
        types: list[str] | None = None,
        detailed: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        """Read any entity prototypes in an area. Pagination is independent of entity type.

        area: {left_top:{x,y},right_bottom:{x,y}}. Detailed results include fluid,
        inventory, recipe, power and rail-connection data when supported by the entity.
        """
        return await invoke("observe", locals_to_params(locals()))

    @server.tool()
    async def inspect_entity(
        unit_number: int | None = None,
        name: str | None = None,
        position: dict[str, float] | None = None,
        surface: str = "nauvis",
    ) -> str:
        """Inspect an entity, including inventory indices and connected rails. No reach required."""
        return await invoke("inspect_entity", locals_to_params(locals()))

    @server.tool()
    async def move_to(
        x: float, y: float, surface: str | None = None, within: float = 0.5, timeout: float = 120
    ) -> str:
        """Walk with the engine pathfinder. Returns an action ID; never teleports."""
        return await invoke("move_to", locals_to_params(locals()))

    @server.tool()
    async def mine_entity(
        unit_number: int | None = None,
        name: str | None = None,
        position: dict[str, float] | None = None,
        surface: str | None = None,
        count: int = 1,
        timeout: float = 120,
    ) -> str:
        """Mine resources or recover structures using real mining time and interaction reach."""
        return await invoke("mine_entity", locals_to_params(locals()))

    @server.tool()
    async def craft(recipe: str, count: int = 1, quality: str | None = None) -> str:
        """Queue hand crafting using real ingredients and game time. Returns an action ID."""
        return await invoke("craft", locals_to_params(locals()))

    @server.tool()
    async def get_action_status(action_id: str | None = None) -> str:
        """Read completion, cancellation or failure of the current or most recent action."""
        return await invoke("action_status", {"action_id": action_id})

    @server.tool()
    async def cancel_action() -> str:
        """Stop the AI character and cancel its current action, returning crafting ingredients."""
        return await invoke("cancel_action")

    @server.tool()
    async def place_entity(
        item: str,
        position: dict[str, float],
        direction: int = 0,
        quality: str = "normal",
        underground_type: Literal["input", "output"] | None = None,
    ) -> str:
        """Build any item.place_result prototype from the AI inventory within normal reach.

        There is no entity whitelist. The engine checks collisions and placement rules.
        For complete layouts, tiles, wires and settings, use native blueprint plans.
        """
        return await invoke("place_entity", locals_to_params(locals()))

    @server.tool()
    async def transfer_items(
        item: str,
        count: int,
        direction: Literal["to_entity", "from_entity"],
        unit_number: int | None = None,
        name: str | None = None,
        position: dict[str, float] | None = None,
        surface: str | None = None,
        inventory: str | int | None = None,
        quality: str = "normal",
    ) -> str:
        """Transfer real items to/from a nearby entity.

        Discover inventory indices with inspect_entity. inventory accepts a numeric index
        or a defines.inventory name. No per-entity role whitelist.
        """
        return await invoke("transfer_items", locals_to_params(locals()))

    @server.tool()
    async def configure_entity(
        unit_number: int | None = None,
        name: str | None = None,
        position: dict[str, float] | None = None,
        surface: str | None = None,
        recipe: str | None = None,
        rotate: bool = False,
        direction: int | None = None,
        station_name: str | None = None,
        control_parameters: dict[str, Any] | None = None,
    ) -> str:
        """Configure a nearby machine, station or control behavior using native entity methods."""
        return await invoke("configure_entity", locals_to_params(locals()))

    @server.tool()
    async def list_prototypes(
        kind: Literal["entity", "item", "recipe", "technology", "tile"] = "entity",
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        """Discover installed base, expansion and mod prototypes by name."""
        return await invoke("prototypes", locals_to_params(locals()))

    @server.tool()
    async def list_recipes(
        query: str | None = None, include_locked: bool = False, offset: int = 0, limit: int = 50
    ) -> str:
        """Read real recipe ingredients, products, category, energy and research availability."""
        return await invoke("recipes", locals_to_params(locals()))

    @server.tool()
    async def research(start: str | None = None, force: str = "player") -> str:
        """Read research and available technologies; optionally queue a technology normally."""
        return await invoke("research", locals_to_params(locals()))

    @server.tool()
    async def trains(
        train_id: int | None = None,
        surface: str | None = None,
        manual_mode: bool | None = None,
        schedule: dict[str, Any] | None = None,
        go_to_station: int | None = None,
    ) -> str:
        """Inspect trains, schedules and carriages; modify one explicit train ID when requested.

        schedule uses Factorio's TrainSchedule structure. Groups and interrupts are available
        through get_schedule() in the advanced Lua tool; a basic schedule is a separate interface.
        """
        return await invoke("trains", locals_to_params(locals()))

    @server.tool()
    async def blueprint_catalog(
        ref: str | None = None,
        query: str | None = None,
        recursive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> str:
        """Browse player/game libraries, nested books, inventory and captured blueprints.

        Returned references identify exact records. Search RAILS or a project label with query.
        Original library records are never modified.
        """
        return await invoke("blueprint_catalog", locals_to_params(locals()))

    @server.tool()
    async def capture_blueprint(
        surface: str,
        area: dict[str, Any],
        label: str = "Captured layout",
        include_tiles: bool = False,
        include_trains: bool = False,
    ) -> str:
        """Capture a layout, including sandbox surfaces, with native blueprint settings."""
        return await invoke("blueprint_capture", locals_to_params(locals()))

    @server.tool()
    async def import_blueprint(data: str) -> str:
        """Import an exported blueprint or nested book into bridge-owned storage."""
        return await invoke("blueprint_import", {"data": data})

    @server.tool()
    async def export_blueprint(ref: str) -> str:
        """Export an exact blueprint or book record as a standard Factorio string."""
        return await invoke("blueprint_export", {"ref": ref})

    @server.tool()
    async def inspect_blueprint(ref: str, include_entities: bool = False) -> str:
        """Read footprint, quantities, stations, grid snapping and optional full native entities."""
        return await invoke("blueprint_inspect", locals_to_params(locals()))

    @server.tool()
    async def find_sites(
        ref: str,
        surface: str,
        area: dict[str, Any],
        direction: int = 0,
        step: int = 32,
        allow_resources: bool = False,
        offset: int = 0,
        limit: int = 200,
    ) -> str:
        """Find candidate footprints without existing structures, water or cliffs.

        This is terrain screening. Plan rail approaches, grid alignment, utilities and future
        expansion separately from the returned footprints, using the user's blueprint standards.
        """
        return await invoke("find_sites", locals_to_params(locals()))

    @server.tool()
    async def create_plan(
        surface: str, components: list[dict[str, Any]], label: str = "Construction plan"
    ) -> str:
        """Freeze an ordered plan of native blueprints without building anything.

        Each component is {ref,position:{x,y},direction:0|4|8|12,label?}.
        Include factory blocks, stations, signals and rail book segments in one plan.
        """
        return await invoke("plan_create", locals_to_params(locals()))

    @server.tool()
    async def inspect_plan(plan_id: str) -> str:
        """Read a persistent construction plan and its application state."""
        return await invoke("plan_inspect", {"plan_id": plan_id})

    @server.tool()
    async def preview_plan(plan_id: str, seconds: int = 60) -> str:
        """Draw temporary footprint overlays. Does not create ghosts or start robot construction."""
        return await invoke("plan_preview", locals_to_params(locals()))

    @server.tool()
    async def apply_plan(plan_id: str, mode: Literal["ghosts"]) -> str:
        """Place a plan as native ghosts. Supplied construction robots can build them immediately.

        Use only when the assigned task authorizes placing ghosts. Normal placement does not
        force deconstruction. Real construction uses the existing factory's normal materials.
        """
        return await invoke("plan_apply", locals_to_params(locals()))

    @server.tool()
    async def shoot_at(position: dict[str, float], seconds: float = 2) -> str:
        """Aim/shoot for a bounded duration with real weapons/ammo; executed per tick by the mod.

        This primitive does not establish reliable autonomous combat or tactical threat response.
        """
        return await invoke("shoot_at", locals_to_params(locals()))

    @server.tool()
    async def execute_lua(code: str) -> str:
        """Run explicit administrative Lua for advanced game/mod capabilities not covered above.

        Use rcon.print(helpers.table_to_json(...)) to return data. Obtain the independent character
        through remote.call('factorio_llm_use','get_agent'). This has full game scripting power:
        use the specific tools for ordinary gameplay and respect the user's task scope.
        """
        return await asyncio.to_thread(bridge.lua, code)

    return server


def locals_to_params(values: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in values.items() if name not in {"invoke", "server"}}


def main() -> None:
    password = os.environ.get("FACTORIO_RCON_PASSWORD", "")
    password_file = os.environ.get("FACTORIO_RCON_PASSWORD_FILE")
    if not password and password_file:
        password = Path(password_file).read_text(encoding="utf-8-sig").strip()
    bridge = Bridge(
        password,
        os.environ.get("FACTORIO_RCON_HOST", "127.0.0.1"),
        int(os.environ.get("FACTORIO_RCON_PORT", "27075")),
    )
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(2):
            try:
                bridge.call("ping")
            except (OSError, RuntimeError):
                pass

    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        create_server(bridge).run()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
