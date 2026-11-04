local agent = require("lib.agent")
local world = require("lib.world")
local blueprints = require("lib.blueprints")

local function state()
  storage.llm = storage.llm or {cache = {}, cache_order = {}}
  return storage.llm
end

local operations = {}
for _, group in ipairs({agent.operations, world.operations, blueprints.operations}) do
  for name, handler in pairs(group) do operations[name] = handler end
end
operations.ping = function(s)
  s.heartbeat = game.tick
  return {version = "0.1.0", factorio_version = script.active_mods.base,
          connected_players = #game.connected_players, capabilities = operations.help(s)}
end
operations.help = function()
  local names = {}
  for name in pairs(operations) do names[#names + 1] = name end
  table.sort(names)
  return names
end

commands.add_command("llm-use", "Factorio LLM Use RCON bridge", function(command)
  if command.player_index then return end
  local request = helpers.json_to_table(command.parameter or "")
  if type(request) ~= "table" or type(request.id) ~= "string" then
    rcon.print(helpers.table_to_json({ok = false, error = "Invalid request"}))
    return
  end
  local s = state()
  s.heartbeat = game.tick
  local cached = s.cache[request.id]
  if cached then rcon.print(cached) return end
  local handler = operations[request.operation]
  local ok, result = pcall(function()
    assert(handler, "Unknown operation: " .. tostring(request.operation))
    return handler(s, request.params or {})
  end)
  local encoded, response = pcall(helpers.table_to_json, {id = request.id, ok = ok, tick = game.tick,
    result = ok and result or nil, error = not ok and tostring(result) or nil})
  if not encoded then
    response = helpers.table_to_json({id = request.id, ok = false, tick = game.tick,
      error = "Result could not be serialized; inspect actual state before retrying: " .. tostring(response)})
  end
  s.cache[request.id] = response
  s.cache_order[#s.cache_order + 1] = request.id
  if #s.cache_order > 512 then
    s.cache[table.remove(s.cache_order, 1)] = nil
  end
  rcon.print(response)
end)

script.on_init(function() agent.initialize(state()) end)
script.on_configuration_changed(function() agent.initialize(state()) end)
script.on_event(defines.events.on_tick, function() agent.tick(state()) end)
script.on_event(defines.events.on_script_path_request_finished, function(event)
  agent.path_finished(state(), event)
end)

remote.add_interface("factorio_llm_use", {
  get_agent = function() return state().agent end,
  invoke = function(operation, params)
    assert(operations[operation], "Unknown operation")
    return operations[operation](state(), params or {})
  end
})
