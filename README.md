# Factorio LLM Use

A general Factorio 2.1 toolset for an LLM assistant, using MCP, local RCON and a
persistent game mod. It operates without desktop input and creates its own AI
character, independent of connected human players.

The tool is built first. It does not start a factory project or change a working
world merely because it is installed. The human assigns the tasks and their scope.

## Capabilities

- Inspect surfaces, entities, inventories, fluids, recipes, research, rail connections
  and trains, including installed mod prototypes.
- Walk with native pathfinding; mine and craft over game ticks; build from real
  inventory; transfer items and configure machines and stations.
- Read player and game blueprint libraries and nested books directly. Capture built
  layouts on sandbox surfaces without opening or controlling the sandbox UI.
- Preserve blueprint recipes, wires, modules, station names and snapping through
  Factorio's native blueprint operations.
- Search candidate sites, compose multiple blueprints into a persistent plan, show
  a temporary visual preview, and explicitly place native construction ghosts.
- Inspect and update a selected train's basic schedule, operating mode and destination.
- Use an explicit advanced Lua tool for capabilities not covered by the normal tools,
  including other mods' remote interfaces and advanced schedule features.

There is **no list of permitted entity names**. Placement discovers the installed
item prototype's `place_result`; inventory access uses the entity's real inventory
indices. Native game restrictions, reach, materials, collision rules and recipe
availability still apply. Unsupported mechanics return an error rather than silently
substituting another entity.

This is not a promise of complete coverage of every game mechanic. Reliable combat
has not been established. A bounded shooting primitive runs per tick in the mod;
the LLM should not be relied on for frame-by-frame threat response. New capabilities
can be added without adding entity whitelists.

## Requirements

- Factorio 2.1; developed against 2.1.24. Space Age is optional, but clients and server
  need the same game version, expansion settings and enabled mods.
- Python 3.12+ and [uv](https://docs.astral.sh/uv/).
- A locally hosted or dedicated Factorio server with RCON enabled on loopback.

## Setup

```powershell
uv sync --frozen
uv run python scripts/package_mod.py
```

Install `dist/factorio_llm_use_0.1.0.zip` in the server and client mod directories and
enable **Factorio LLM Use**. The mod adds an empty AI character near the player
force's spawn. It does not add starter items or unlock technologies.

For a first check, the supplied Windows launcher makes an isolated copy of a save
and the installed mod files. It starts a hidden server; it never controls the game
window or overwrites the source save. All session files are kept under `.runtime/`.

```powershell
./scripts/start-server.ps1 -FactorioExe 'D:\path\Factorio.exe' -Save 'D:\saves\world.zip'
```

The game port defaults to `34199` and RCON to `27075`. The launcher creates a random
password in `.runtime/rcon-password.txt`. It refuses to overwrite an existing
session save. The server runs while humans are disconnected; current AI movement
stops after ten seconds without controller requests. Keep session saves/autosaves
when stopping or replacing a session.

Configure the MCP client with a standard stdio server:

```json
{
  "mcpServers": {
    "factorio": {
      "command": "powershell.exe",
      "args": ["-NoProfile", "-File", "D:\\path\\factorio-llm-use\\scripts\\start-mcp.ps1"]
    }
  }
}
```

For the Codex desktop app/CLI, register the current virtual environment directly:

```powershell
uv run python scripts/register_mcp.py
```

This creates only the `factorio-llm-use` MCP entry. The password remains in the
ignored local file. Restart the MCP connection or open a new session if the client
has not refreshed its tool catalog. Registration does not launch or select a world.

For an existing server, set `FACTORIO_RCON_PASSWORD` or
`FACTORIO_RCON_PASSWORD_FILE`, plus `FACTORIO_RCON_PORT` and optionally
`FACTORIO_RCON_HOST`, then run `uv run factorio-llm-use`. Credentials are read from
the environment or a local file, not stored in the repository or the MCP tool schemas.

To stop the supplied session, `./scripts/stop-server.ps1` completes and verifies a
new native save before terminating the recorded project server. Resume with
`./scripts/start-server.ps1 -FactorioExe 'D:\path\Factorio.exe' -Resume`; the most
recent session save is selected. These scripts do not stop unrelated game processes.

## Assigning work

Tasks may ask for inspection, repair, production changes, transport, blueprint work
or other supported actions. The tool does not impose planning as the only workflow.
For example, an assistant can read an oil-processing layout from a sandbox, inspect
the `RAILS` book, compare suitable locations and rail approaches, then place the
factory, stations and rail segments as one construction plan.

`preview_plan` draws temporary footprint overlays only. `apply_plan(mode="ghosts")`
creates real native ghosts: supplied construction robots can build them immediately.
Actual construction uses the normal factory's materials. The assistant should choose
the action that matches the human's assignment, without silently forcing demolition
or creating free construction items.

## Development and verification

```powershell
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -p 'test_*.py'
```

Engine verification is separate from Python tests. See [architecture](docs/architecture.md)
and [verification](docs/verification.md) for precise coverage and limitations.

## Project origin

The MCP plus companion-mod approach was informed by examining
[menbou404/factorioMCP](https://github.com/menbou404/factorioMCP). That repository had
no declared license when inspected. This repository contains an independent
implementation and original English documentation, not a redistribution of its code.
This project's source is MIT licensed.
