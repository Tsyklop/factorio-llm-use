# Architecture

`MCP client -> Python stdio server -> Source RCON -> persistent mod -> Factorio engine`

The mod is the owner of the AI character, actions, path requests, blueprint copies,
plans and recent request results. Its event handlers are registered from source
whenever Factorio loads the mod. Save/load and multiplayer clients therefore load
the same event set; handlers are not injected transiently through console commands.

## Modules

- `bridge.py`: serialized RCON authentication/framing, protocol matching and retry IDs.
- `server.py`: discoverable MCP tool schemas and controller heartbeat.
- `control.lua`: request dispatch, result caching and stable event registration.
- `agent.lua`: the independent character and ordinary timed game actions.
- `world.lua`: prototype-driven observation, inventory discovery, recipes and trains.
- `blueprints.lua`: exact library references, native capture/import/export, plans and previews.

The normal game interface uses `/llm-use` commands and does not need arbitrary Lua
for basic operation. The advanced Lua tool is a separate administrative capability.
It can access the AI with `remote.call('factorio_llm_use', 'get_agent')`, use other
mods' remote interfaces, or inspect native game features that do not yet have a
dedicated typed tool. The assistant remains responsible for the assigned task scope.

## Identity and execution

The AI is a `LuaEntity` character, not `game.connected_players[1]`. It continues to
exist with no human connected. Only one walk/mine/craft/shoot action runs at a time.
Movement and shooting are applied by game ticks, while the MCP client polls action
state. A missing heartbeat cancels movement and mining, and returns unconsumed
crafting ingredients. Combat tactics and reliable automatic retreat are not claimed.

The single current character lives in `storage.llm.agent`. `on_entity_died` clears
that reference, fails the active action and stores a deadline 300 ticks ahead.
The persistent tick handler creates an empty character at the player force spawn
on Nauvis (or the first surface if Nauvis is absent), replacing the shared reference.
It never edits the dead character's loot or corpse. A missing/invalid character in
an old save also starts recovery, and blocked spawns retry after 60 ticks. Pending
deadlines survive save/load. `respawn_agent` permits immediate manual recovery and
is a no-op when the character is already alive. Tools resolve the shared reference
at call time; path results for interrupted actions cannot resume on the new AI.

Retries retain the same request ID. The mod stores the most recent 512 responses
in save state, so a lost response can be retried without repeating an operation
within that retention window. Results outside the window are not an exactly-once
guarantee. Long-running actions return IDs instead of holding the RCON call open.

## Blueprints and construction

Library references use `game/<index>`, `player/<player-index>/<record-index>` and
nested `/child-index` suffixes. Captures/imports use `stored/<slot>`. Plans freeze
independent copies of each source blueprint, preserving user library records.

Footprint/site tools provide geometry and terrain screening, not a guarantee that
a complete rail network is operable. The assistant must reason about rail approaches,
signals, train length, station roles, throughput, water, power and future expansion.
Rail connections and train schedules are observable through the native engine.

Application uses native `build_blueprint` with normal placement. It does not use
forced or superforced demolition. A component that places no ghosts is reported as
an error; the caller must distinguish blocked placement from already existing work.
On component failure, newly returned ghosts from earlier components are removed
where they remain ghosts. Events in other mods can change entities during placement,
so this is not a transaction over arbitrary third-party script effects.

An overlay preview creates no construction ghosts. Ghost application is explicitly
requested and can trigger normal robot construction. Ordinary individual placement
consumes real inventory items and discovers any installed item placement prototype.

## Compatibility boundaries

No entity-name whitelist is used. Special mechanics still need engine-aware operations:
tiles and composite layouts use blueprints; equipment, vehicles, space-platform
operations, train interrupts and mod-specific features may need the advanced tool or
new dedicated tools. Absence of a whitelist is not universal support for every mechanic.
