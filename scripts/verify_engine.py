"""Real MCP/engine checks on an isolated copy. Never point the engine at the source save."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from factorio_llm_use.bridge import Bridge

PROJECT = Path(__file__).resolve().parents[1]


class McpClient:
    def __init__(self, password: str | None, port: int, root: Path, program=None, extra_env=None):
        env = dict(os.environ, FACTORIO_RCON_PORT=str(port))
        env.pop("FACTORIO_RCON_PASSWORD", None)
        if password:
            env["FACTORIO_RCON_PASSWORD"] = password
        env.update(extra_env or {})
        self.error_file = (root / "mcp.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            program or [sys.executable, "-m", "factorio_llm_use.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.error_file,
            text=True,
            encoding="utf-8",
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.messages: queue.Queue = queue.Queue()
        self.serial = 0
        threading.Thread(target=self._read, daemon=True).start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "factorio-llm-use-engine-check", "version": "0.1.1"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self):
        assert self.process.stdout
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                pass

    def _send(self, value):
        assert self.process.stdin
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.serial += 1
        self._send({"jsonrpc": "2.0", "id": self.serial, "method": method, "params": params})
        deadline = time.monotonic() + 25
        while True:
            response = self.messages.get(timeout=max(0.1, deadline - time.monotonic()))
            if response.get("id") == self.serial:
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response["result"]

    def tool(self, tool_name, **arguments):
        result = self.request("tools/call", {"name": tool_name, "arguments": arguments})
        text = "".join(part.get("text", "") for part in result.get("content", []))
        if result.get("isError"):
            raise RuntimeError(text)
        value = json.loads(text)
        if not value.get("ok", True):
            raise RuntimeError(value)
        return value.get("result", value)

    def close(self):
        assert self.process.stdin
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.error_file.close()


def run(args):
    root = PROJECT / ".runtime" / ("verify-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    (root / "data/saves").mkdir(parents=True)
    (root / "mods").mkdir()
    for source in Path(args.mods).iterdir():
        if source.is_file():
            shutil.copy2(source, root / "mods" / source.name)
    shutil.copytree(PROJECT / "mod/factorio_llm_use_0.1.1", root / "mods/factorio_llm_use_0.1.1")
    mods = json.loads((root / "mods/mod-list.json").read_text(encoding="utf-8-sig"))
    mods["mods"] = [m for m in mods["mods"] if m["name"] != "factorio_llm_use"]
    mods["mods"].append({"name": "factorio_llm_use", "enabled": True})
    (root / "mods/mod-list.json").write_text(json.dumps(mods), encoding="utf-8")
    copied_save = root / "source-copy.zip"
    shutil.copy2(args.save, copied_save)
    executable = Path(args.factorio).resolve()
    read_data = executable.parents[2] / "data"
    config = root / "config.ini"
    config.write_text(
        f"[path]\nread-data={read_data.as_posix()}\nwrite-data={(root / 'data').as_posix()}\n",
        encoding="utf-8",
    )
    settings = root / "server-settings.json"
    settings.write_text(
        json.dumps(
            {
                "name": "Isolated Factorio LLM Use verification",
                "description": "Disposable engine verification copy",
                "visibility": {"public": False, "lan": False},
                "require_user_verification": False,
                "auto_pause": False,
                "autosave_interval": 0,
            }
        ),
        encoding="utf-8",
    )
    password = uuid4().hex
    bridge = Bridge(password, port=args.rcon_port)
    server_log = (root / "server.log").open("w", encoding="utf-8")
    process = None
    mcp = None
    report = {"checks": [], "source_save": str(args.save), "artifacts": str(root)}

    def start(save):
        command = [
            str(executable),
            "--config",
            str(config),
            "--mod-directory",
            str(root / "mods"),
            "--start-server",
            str(save),
            "--server-settings",
            str(settings),
            "--bind",
            "127.0.0.1",
            "--port",
            str(args.game_port),
            "--rcon-bind",
            f"127.0.0.1:{args.rcon_port}",
            "--rcon-password",
            password,
        ]
        proc = subprocess.Popen(
            command,
            stdout=server_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("Engine exited; inspect the isolated server log")
            try:
                bridge.call("ping")
                return proc
            except (OSError, RuntimeError):
                time.sleep(0.2)
        proc.terminate()
        proc.wait(timeout=10)
        raise TimeoutError("Engine startup")

    def check(name, condition=True):
        assert condition, name
        report["checks"].append(name)
        print("PASS " + name, flush=True)

    def lua(code):
        raw = bridge.lua(code)
        try:
            return json.loads(raw) if raw.strip() else None
        except ValueError as exc:
            raise RuntimeError("Engine query failed: " + raw) from exc

    def wait_action(action_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = mcp.tool("get_action_status", action_id=action_id)
            if status["status"] != "running":
                assert status["status"] == "succeeded", status
                return status
            time.sleep(0.1)
        raise TimeoutError("AI action")

    try:
        process = start(copied_save)
        mcp = McpClient(password, args.rcon_port, root)
        report["tool_count"] = len(mcp.request("tools/list", {})["tools"])
        check("MCP initialization and tool discovery", report["tool_count"] >= 25)
        status = mcp.tool("get_agent_status")
        agent_id = status["unit_number"]
        check("independent AI character with empty inventory", not status["inventory"])
        world = mcp.tool("get_world")
        check("world and sandbox enumeration", len(world["surfaces"]) >= 1)
        mcp.tool("observe", position=status["position"], detailed=True)
        check("generic observation with Factorio 2.1 fluid interface")
        catalog = mcp.tool("blueprint_catalog", query="RAILS")
        report["rail_book_matches"] = catalog["total"]
        check("player blueprint library read")
        if catalog["total"]:
            exact_book = next(
                entry
                for entry in catalog["blueprints"]
                if entry.get("label") == "RAILS" and entry["kind"] == "book"
            )
            ref = exact_book["ref"]
            book = mcp.tool("blueprint_catalog", ref=ref)
            check("nested rail book enumeration", book["total"] > 1)
        result = mcp.tool(
            "move_to",
            x=status["position"]["x"] + 3,
            y=status["position"]["y"],
            surface=status["surface"],
        )
        wait_action(result["action_id"])
        moved = mcp.tool("get_agent_status")
        check(
            "real pathfinding movement without connected humans",
            abs(moved["position"]["x"] - status["position"]["x"]) > 1,
        )
        # The first administrative Lua request can be rejected by Factorio's native
        # confirmation. Prime that boundary with an idempotent read, never a mutation.
        for _ in range(2):
            lua("rcon.print(helpers.table_to_json({tick=game.tick}))")
        lua("""local a=remote.call('factorio_llm_use','get_agent')
local surface=game.create_surface('llm-use-verification',{width=128,height=128,autoplace_controls={}})
surface.request_to_generate_chunks({0,0},1) surface.force_generate_chunk_requests()
for _,e in pairs(surface.find_entities_filtered{area={{-32,-32},{32,32}}}) do e.destroy() end
local tiles={} for x=-32,31 do for y=-32,31 do tiles[#tiles+1]={name='grass-1',position={x,y}} end end
surface.set_tiles(tiles) a.teleport({0,0},surface)
a.force.chart(surface,{{-64,-64},{64,64}})
for _,stack in ipairs({{name='steel-chest',count=3},{name='oil-refinery',count=1},{name='assembling-machine-2',count=1},{name='iron-plate',count=100}}) do a.insert(stack) end
rcon.print(helpers.table_to_json({ready=true}))""")
        chest = mcp.tool("place_entity", item="steel-chest", position={"x": -2.5, "y": 0.5})
        refinery = mcp.tool("place_entity", item="oil-refinery", position={"x": 4.5, "y": 0.5})
        assembler = mcp.tool(
            "place_entity", item="assembling-machine-2", position={"x": 0.5, "y": 4.5}
        )
        actual = lua(
            """local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({refineries=a.surface.count_entities_filtered{name='oil-refinery'},assemblers=a.surface.count_entities_filtered{name='assembling-machine-2'},remaining_refineries=a.get_item_count('oil-refinery')}))"""
        )
        check(
            "unrestricted refinery and assembler-2 placement consumes real items",
            actual["refineries"] == actual["assemblers"] == 1
            and actual["remaining_refineries"] == 0
            and refinery["unit_number"] > 0,
        )
        before = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({count=a.surface.count_entities_filtered{name='oil-refinery'}}))"
        )
        try:
            mcp.tool("place_entity", item="oil-refinery", position={"x": 4.5, "y": 0.5})
            raise AssertionError("Missing construction items were accepted")
        except RuntimeError as exc:
            assert "missing from the AI inventory" in str(exc), str(exc)
        after = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({count=a.surface.count_entities_filtered{name='oil-refinery'}}))"
        )
        check("failed placement preserves real world state", before == after)
        mcp.tool(
            "transfer_items",
            item="iron-plate",
            count=12,
            direction="to_entity",
            unit_number=chest["unit_number"],
            inventory="chest",
        )
        actual = lua(
            "local e=game.surfaces['llm-use-verification'].find_entity('steel-chest',{-2.5,0.5}) rcon.print(helpers.table_to_json({count=e.get_inventory(defines.inventory.chest).get_item_count('iron-plate')}))"
        )
        check("generic inventory transfer persists twelve real items", actual["count"] == 12)
        mcp.tool("configure_entity", unit_number=assembler["unit_number"], recipe="iron-gear-wheel")
        actual = lua(
            "local e=game.surfaces['llm-use-verification'].find_entity('assembling-machine-2',{0.5,4.5}) rcon.print(helpers.table_to_json({recipe=e.get_recipe().name}))"
        )
        check("assembler-2 recipe configuration", actual["recipe"] == "iron-gear-wheel")
        result = mcp.tool("craft", recipe="iron-gear-wheel", count=1)
        wait_action(result["action_id"])
        actual = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({gears=a.get_item_count('iron-gear-wheel')}))"
        )
        check("timed crafting creates the actual product", actual["gears"] >= 1)
        bp = mcp.tool(
            "capture_blueprint",
            surface="llm-use-verification",
            area={"left_top": {"x": -5, "y": -3}, "right_bottom": {"x": 8, "y": 8}},
            label="Engine fixture",
        )
        check("native layout capture", bp["entity_count"] == 3)
        inspected = mcp.tool("inspect_blueprint", ref=bp["ref"], include_entities=True)
        check(
            "captured blueprint retains the machine recipe",
            any(e.get("recipe") == "iron-gear-wheel" for e in inspected["entities"]),
        )
        plan = mcp.tool(
            "create_plan",
            surface="llm-use-verification",
            components=[{"ref": bp["ref"], "position": {"x": 16, "y": 16}, "direction": 0}],
            label="Verification plan",
        )
        mcp.tool("preview_plan", plan_id=plan["id"], seconds=2)
        actual = lua(
            "rcon.print(helpers.table_to_json({ghosts=game.surfaces['llm-use-verification'].count_entities_filtered{type='entity-ghost'}}))"
        )
        check("preview creates zero construction ghosts", actual["ghosts"] == 0)
        mcp.tool("apply_plan", plan_id=plan["id"], mode="ghosts")
        actual = lua(
            "local out={} for _,e in pairs(game.surfaces['llm-use-verification'].find_entities_filtered{type='entity-ghost'}) do out[#out+1]={name=e.ghost_name,recipe=e.ghost_name=='assembling-machine-2' and e.get_recipe() and e.get_recipe().name or nil} end rcon.print(helpers.table_to_json({ghosts=out}))"
        )
        check("native plan application creates three real ghosts", len(actual["ghosts"]) == 3)
        check(
            "native ghost preserves the assembler recipe",
            any(e.get("recipe") == "iron-gear-wheel" for e in actual["ghosts"]),
        )
        again = mcp.tool("apply_plan", plan_id=plan["id"], mode="ghosts")
        check(
            "reapplying a plan does not duplicate construction",
            again["status"] == "already_applied",
        )
        sites = mcp.tool(
            "find_sites",
            ref=bp["ref"],
            surface="llm-use-verification",
            area={"left_top": {"x": -24, "y": -24}, "right_bottom": {"x": 24, "y": 24}},
            step=16,
        )
        check("site screening returns candidate footprints", len(sites["sites"]) > 0)
        mcp.tool("trains")
        check("native train inspection")
        mcp.tool("research")
        mcp.tool("list_recipes", query="iron-gear")
        check("native research and recipe inspection")
        # Exercise the remaining advertised action and retry seams against persisted state.
        stock_before = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({chests=a.get_item_count('steel-chest')}))"
        )
        params = {"item": "steel-chest", "position": {"x": -4.5, "y": -2.5}}
        first = bridge.call("place_entity", params, request_id="engine-idempotence-check")
        second = bridge.call("place_entity", params, request_id="engine-idempotence-check")
        stock_after = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({chests=a.get_item_count('steel-chest')}))"
        )
        check(
            "native request retry spends exactly one construction item",
            first == second and stock_after["chests"] == stock_before["chests"] - 1,
        )
        ore_before = lua(
            "local a=remote.call('factorio_llm_use','get_agent') a.surface.create_entity{name='iron-ore',position={-1.5,-1.5},amount=50} rcon.print(helpers.table_to_json({ore=a.get_item_count('iron-ore')}))"
        )
        result = mcp.tool(
            "mine_entity",
            name="iron-ore",
            position={"x": -1.5, "y": -1.5},
            surface="llm-use-verification",
            count=1,
        )
        wait_action(result["action_id"])
        ore_after = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({ore=a.get_item_count('iron-ore')}))"
        )
        check("real timed resource mining adds actual ore", ore_after["ore"] > ore_before["ore"])
        result = mcp.tool("mine_entity", unit_number=chest["unit_number"], count=1)
        wait_action(result["action_id"])
        actual = lua(
            "local a=remote.call('factorio_llm_use','get_agent') rcon.print(helpers.table_to_json({exists=a.surface.find_entity('steel-chest',{-2.5,0.5})~=nil,iron=a.get_item_count('iron-plate')}))"
        )
        check(
            "real structure recovery removes the entity and returns contents",
            not actual["exists"] and actual["iron"] >= 98,
        )
        mcp.tool("move_to", x=-25, y=25, surface="llm-use-verification")
        mcp.tool("cancel_action")
        cancelled = mcp.tool("get_agent_status")
        time.sleep(0.15)
        stationary = mcp.tool("get_agent_status")
        check(
            "cancelled movement stops at a stable actual position",
            cancelled["last_action"]["status"] == "cancelled"
            and cancelled["position"] == stationary["position"],
        )
        fixture_train = lua("""local s=game.surfaces['llm-use-verification']
for y=-24,-4,2 do s.create_entity{name='straight-rail',position={-20,y},direction=0,force='player'} end
local l=s.create_entity{name='locomotive',position={-20,-14},direction=0,force='player'}
assert(l and l.train,'Train fixture did not form')
rcon.print(helpers.table_to_json({id=l.train.id,unit_number=l.unit_number}))""")
        mcp.tool(
            "trains",
            train_id=fixture_train["id"],
            manual_mode=True,
            schedule={
                "current": 1,
                "records": [
                    {
                        "station": "Verification station",
                        "wait_conditions": [{"type": "time", "compare_type": "and", "ticks": 60}],
                    }
                ],
            },
        )
        actual = lua(
            "local l=game.surfaces['llm-use-verification'].find_entities_filtered{name='locomotive'}[1] rcon.print(helpers.table_to_json({manual=l.train.manual_mode,station=l.train.schedule.records[1].station}))"
        )
        check(
            "selected train schedule is persisted by the native engine",
            actual["manual"] and actual["station"] == "Verification station",
        )
        rails = mcp.tool(
            "observe",
            surface="llm-use-verification",
            names=["straight-rail"],
            position={"x": -20, "y": -14},
            radius=16,
            detailed=True,
        )
        check(
            "native connected-rail topology is inspectable",
            any(e.get("rail_connections") for e in rails["entities"]),
        )
        rail_bp = mcp.tool(
            "capture_blueprint",
            surface="llm-use-verification",
            area={"left_top": {"x": -22, "y": -26}, "right_bottom": {"x": -18, "y": -2}},
            label="Rail fixture",
        )
        rail_plan = mcp.tool(
            "create_plan",
            surface="llm-use-verification",
            components=[{"ref": rail_bp["ref"], "position": {"x": -20, "y": 16}, "direction": 0}],
        )
        mcp.tool("apply_plan", plan_id=rail_plan["id"], mode="ghosts")
        actual = lua(
            "local n=0 for _,e in pairs(game.surfaces['llm-use-verification'].find_entities_filtered{type='entity-ghost'}) do if e.ghost_name=='straight-rail' then n=n+1 end end rcon.print(helpers.table_to_json({rails=n}))"
        )
        check("native blueprint rail placement creates actual rail ghosts", actual["rails"] >= 10)
        frozen_status = mcp.tool("get_agent_status")
        bridge.command("/server-save llm-use-verified")
        saved = root / "data/saves/llm-use-verified.zip"
        deadline = time.monotonic() + 10
        while not saved.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        time.sleep(0.3)
        process.terminate()
        process.wait(timeout=10)
        process = start(saved)
        restored = mcp.tool("get_agent_status")
        check(
            "AI identity and inventory survive engine save/load",
            restored["unit_number"] == agent_id
            and restored["inventory"] == frozen_status["inventory"],
        )
        check(
            "plan state survives engine save/load",
            mcp.tool("inspect_plan", plan_id=plan["id"])["status"] == "applied",
        )
        report["passed"] = True
    except Exception as exc:
        report["passed"], report["error"] = False, str(exc).replace(password, "<REDACTED>")
        raise
    finally:
        if mcp:
            mcp.close()
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        server_log.close()
        (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "passed": report.get("passed", False),
                    "checks": len(report["checks"]),
                    "artifacts": str(root),
                    "error": report.get("error"),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorio", required=True)
    parser.add_argument("--save", required=True)
    parser.add_argument("--mods", required=True)
    parser.add_argument("--game-port", type=int, default=34200)
    parser.add_argument("--rcon-port", type=int, default=27077)
    run(parser.parse_args())
