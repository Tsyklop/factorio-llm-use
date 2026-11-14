local MODE = require("test_mode")
-- Only loaded by scripts/verify_respawn_offline.py in a disposable engine copy.
local function invoke(op, params)
  -- The normal RCON command refreshes the controller heartbeat on each call.
  remote.call("factorio_llm_use", "invoke", "ping", {})
  return remote.call("factorio_llm_use", "invoke", op, params or {})
end

local function character()
  local a = remote.call("factorio_llm_use", "get_agent")
  return a and a.valid and a.health > 0 and a or nil
end

local function check(name, condition)
  assert(condition, name)
  storage.checks[#storage.checks + 1] = name
  log("RESPAWN PASS: " .. name)
  helpers.write_file("respawn-report.json", helpers.table_to_json{
    mode = MODE, checks = storage.checks, tick = game.tick,
    death_tick = storage.death_tick, respawn_tick = storage.observed_respawn_tick
  }, false)
end

local function kill()
  local a = assert(character(), "Expected living test AI")
  storage.old_id, storage.death_tick = a.unit_number, game.tick
  storage.death_position = a.position
  storage.corpse_before = a.surface.count_entities_filtered{type = "character-corpse"}
  a.clear_items_inside()
  a.insert{name = "iron-plate", count = 7}
  assert(a.die(), "Native death failed")
end

local function finish()
  helpers.write_file("respawn-complete.txt", MODE, false)
  script.on_event(defines.events.on_tick, nil)
end

local function run()
  if storage.mode ~= MODE then
    storage.mode, storage.stage, storage.started = MODE, 0, game.tick
    storage.checks = {}
    game.speed = 16
  end
  local age = game.tick - storage.started
  local mode, stage = storage.mode, storage.stage
  if mode == "legacy" then
    if stage == 0 then
      if character() then kill() end
      check("authentic old mod state has no living AI", not character())
      game.server_save("legacy-dead")
      storage.stage = 1
    elseif age > 30 then finish() end
    return
  end

  if mode == "reload" then
    if character() then
      storage.observed_respawn_tick = game.tick
      check("pending respawn survives save/load without restarting delay",
            game.tick - storage.death_tick >= 300 and game.tick - storage.death_tick <= 301)
      check("restored timer produces an empty new character",
            character().unit_number ~= storage.old_id and character().get_item_count() == 0)
      finish()
    end
    assert(age < 400, "Pending respawn did not recover")
    return
  end

  if stage == 0 then
    if not character() then assert(age < 400, "Legacy save did not recover") return end
    check("existing 0.1.1 dead save recovers automatically", character().get_item_count() == 0)
    local a = character()
    -- Test-only fixture: prepare clear ground away from biters and human buildings.
    local surface = a.surface
    surface.request_to_generate_chunks({x = 320, y = 320}, 3)
    surface.force_generate_chunk_requests()
    for _, e in pairs(surface.find_entities_filtered{area={{270,270},{370,370}}}) do
      if e.type ~= "character" then e.destroy() end
    end
    local tiles = {}
    for x = 280, 360 do for y = 280, 360 do
      tiles[#tiles+1] = {name = "grass-1", position = {x, y}}
    end end
    surface.set_tiles(tiles)
    a.force.set_spawn_position({320, 320}, surface)
    local live = invoke("respawn_agent")
    check("manual recovery preserves a living AI", not live.respawned and live.unit_number == a.unit_number)
    -- Death while an action is pending must clear the action and stale path result.
    invoke("move_to", {x = a.position.x + 12, y = a.position.y, within = 0.5})
    kill()
    check("interrupted movement fails at death", invoke("action_status").status == "failed")
    check("dead entity is removed from shared reference", not remote.call("factorio_llm_use", "get_agent"))
    storage.stage = 1
  elseif stage == 1 then
    local a = character()
    local elapsed = game.tick - storage.death_tick
    if elapsed < 300 then assert(not a, "AI respawned too early") return end
    assert(a and elapsed <= 301, "AI did not respawn after 300 ticks")
    storage.observed_respawn_tick = game.tick
    check("automatic respawn takes exactly 300 game ticks", elapsed >= 300 and elapsed <= 301)
    local status = invoke("agent_status")
    check("shared reference and agent_status use the new identity",
          a.unit_number ~= storage.old_id and status.unit_number == a.unit_number)
    check("replacement inventory is empty", a.get_item_count() == 0)
    local spawn = a.force.get_spawn_position(a.surface)
    check("spawn follows current player force spawn point",
          math.abs(a.position.x - spawn.x) < 2 and math.abs(a.position.y - spawn.y) < 2)
    local corpses = a.surface.find_entities_filtered{type = "character-corpse",
        position = storage.death_position, radius = 1}
    local iron = 0
    for _, corpse in pairs(corpses) do
      local inv = corpse.get_inventory(defines.inventory.character_corpse)
      if inv then iron = iron + inv.get_item_count("iron-plate") end
    end
    check("native character corpse retains the seven test items", iron >= 7)
    -- Unrelated character death must not schedule a replacement for the AI.
    local other = a.surface.create_entity{name="character", position={330,330}, force=a.force}
    other.die()
    check("unrelated character death leaves the AI alive", character() == a)
    storage.goal = {x = a.position.x + 4, y = a.position.y}
    storage.move_id = invoke("move_to", {x=storage.goal.x, y=storage.goal.y, within=0.5}).action_id
    storage.move_started = game.tick
    storage.stage = 2
  elseif stage == 2 then
    local action = invoke("action_status", {action_id = storage.move_id})
    if action.status == "running" then
      assert(game.tick - storage.move_started < 600, "Replacement could not walk") return
    end
    local a = character()
    check("new character walks with native pathfinding", action.status == "succeeded" and
          math.abs(a.position.x - storage.goal.x) <= 0.5 and
          math.abs(a.position.y - storage.goal.y) <= 0.5)
    check("agent_status reports actual moved engine character",
          invoke("agent_status").unit_number == a.unit_number and
          invoke("agent_status").position.x == a.position.x)
    kill()
    local manual = invoke("respawn_agent")
    check("manual recovery works while timer is pending", manual.respawned and character().get_item_count() == 0)
    local repeated = invoke("respawn_agent")
    check("repeated recovery cannot duplicate AI", not repeated.respawned and repeated.unit_number == manual.unit_number)
    -- Also cover the fallback when another script removes the AI without death.
    character().destroy()
    storage.fallback_started = game.tick
    storage.stage = 3
  elseif stage == 3 then
    if not character() then
      assert(game.tick - storage.fallback_started <= 301, "Missing-character fallback failed") return
    end
    check("tick fallback recovers character removed without a death event", character().get_item_count() == 0)
    -- Block the whole 32-tile spawn search, then restore it after one failed attempt.
    local surface = character().surface
    kill()
    local tiles = {}
    for x=285,355 do for y=285,355 do tiles[#tiles+1]={name="water",position={x,y}} end end
    surface.set_tiles(tiles)
    storage.stage = 4
  elseif stage == 4 then
    local elapsed = game.tick - storage.death_tick
    if elapsed < 310 then assert(not character(), "Respawn should be blocked") return end
    check("blocked spawn does not crash the tick handler", not character())
    local tiles = {}
    for x=315,325 do for y=315,325 do tiles[#tiles+1]={name="grass-1",position={x,y}} end end
    game.surfaces.nauvis.set_tiles(tiles)
    storage.stage = 5
  elseif stage == 5 then
    if not character() then assert(game.tick - storage.death_tick < 400, "Spawn retry failed") return end
    check("blocked spawn retries successfully when space returns", character().get_item_count() == 0)
    kill()
    storage.stage = 6
  elseif stage == 6 then
    if game.tick - storage.death_tick == 100 then
      game.server_save("pending-respawn")
      check("saved a partially elapsed respawn timer", not character())
    elseif game.tick - storage.death_tick > 125 then finish() end
  end
end

script.on_event(defines.events.on_tick, run)
