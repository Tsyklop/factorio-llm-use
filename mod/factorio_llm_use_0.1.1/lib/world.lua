local M = {operations = {}}

local function safe(fn)
  local ok, value = pcall(fn)
  if ok then return value end
end

function M.remember(s, e)
  if e.unit_number then
    s.entity_refs = s.entity_refs or {}
    s.entity_refs[e.unit_number] = e
  end
  return e
end

function M.entity(e, detailed, s)
  if s then M.remember(s, e) end
  local data = {name = e.name, type = e.type, unit_number = e.unit_number,
                position = e.position, surface = e.surface.name, force = e.force.name,
                direction = e.direction, quality = e.quality.name}
  data.status = safe(function() return e.status end)
  if e.type == "entity-ghost" then data.ghost_name = e.ghost_name end
  if e.type == "resource" then data.amount = e.amount end
  if e.type == "train-stop" then data.station_name = e.backer_name end
  if detailed then
    data.health = safe(function() return e.health end)
    data.recipe = safe(function() local r = e.get_recipe() return r and r.name end)
    data.fluids = safe(function() return e.get_fluid_contents() end)
    data.electric_network_id = safe(function() return e.electric_network_id end)
    data.energy = safe(function() return e.energy end)
    data.inventories = {}
    local seen = {}
    for name, id in pairs(defines.inventory) do
      if not seen[id] then
        seen[id] = true
        local inv = safe(function() return e.get_inventory(id) end)
        if inv then data.inventories[#data.inventories + 1] = {
          name = name, index = id, slots = #inv, contents = inv.get_contents()
        } end
      end
    end
    data.rail_connections = safe(function()
      local result = {}
      for _, direction in pairs(defines.rail_direction) do
        for _, connection in pairs(defines.rail_connection_direction) do
          if connection ~= defines.rail_connection_direction.none then
            local other = e.get_connected_rail{
              rail_direction = direction, rail_connection_direction = connection
            }
            if other then result[#result + 1] = {unit_number = other.unit_number,
              name = other.name, position = other.position, rail_direction = direction,
              rail_connection_direction = connection} end
          end
        end
      end
      return result
    end)
  end
  return data
end

function M.surface(s, p)
  local surface = game.surfaces[p.surface or (s.agent and s.agent.surface.name) or "nauvis"]
  return assert(surface, "Unknown surface")
end

function M.target(s, p)
  if p.unit_number then
    local known = s.entity_refs and s.entity_refs[p.unit_number]
    if known and known.valid then return known end
    local entity = game.get_entity_by_unit_number(p.unit_number)
    if entity then return M.remember(s, entity) end
  end
  assert(p.name and p.position, "unit_number or name/position is required")
  return M.remember(s, assert(M.surface(s, p).find_entity(p.name, p.position), "Entity no longer exists"))
end

M.operations.world = function()
  local surfaces, players, forces = {}, {}, {}
  for _, surface in pairs(game.surfaces) do
    surfaces[#surfaces + 1] = {name = surface.name, index = surface.index,
      platform = surface.platform ~= nil,
      sandbox = surface.name:find("bpsb", 1, true) ~= nil}
  end
  for _, p in pairs(game.players) do
    players[#players + 1] = {name = p.name, index = p.index, connected = p.connected,
      surface = p.surface.name, position = p.position}
  end
  for _, force in pairs(game.forces) do forces[#forces + 1] = force.name end
  return {surfaces = surfaces, players = players, forces = forces,
          game_speed = game.speed, tick = game.tick}
end

M.operations.observe = function(s, p)
  local surface = M.surface(s, p)
  local filter = {area = p.area, position = not p.area and
      (p.position or (s.agent and s.agent.position) or {0, 0}) or nil,
    radius = not p.area and (p.radius or 32) or nil, name = p.names, type = p.types,
    force = p.force}
  local entities = surface.find_entities_filtered(filter)
  table.sort(entities, function(a, b)
    if a.position.y ~= b.position.y then return a.position.y < b.position.y end
    if a.position.x ~= b.position.x then return a.position.x < b.position.x end
    return (a.unit_number or 0) < (b.unit_number or 0)
  end)
  local offset, limit = p.offset or 0, math.min(p.limit or 100, 1000)
  assert(offset >= 0 and limit > 0, "Invalid pagination")
  local result = {}
  for i = offset + 1, math.min(offset + limit, #entities) do
    result[#result + 1] = M.entity(entities[i], p.detailed, s)
  end
  return {surface = surface.name, entities = result, total = #entities,
    next_offset = offset + limit < #entities and offset + limit or nil}
end

M.operations.inspect_entity = function(s, p) return M.entity(M.target(s, p), true, s) end

M.operations.prototypes = function(s, p)
  local group = p.kind or "entity"
  local source = assert(prototypes[group], "Unknown prototype kind")
  local names = {}
  for name in pairs(source) do
    if not p.query or name:find(p.query, 1, true) then names[#names + 1] = name end
  end
  table.sort(names)
  local result, offset, limit = {}, p.offset or 0, math.min(p.limit or 100, 1000)
  for i = offset + 1, math.min(offset + limit, #names) do
    local proto = source[names[i]]
    result[#result + 1] = {name = names[i], type = safe(function() return proto.type end),
      collision_box = safe(function() return proto.collision_box end)}
  end
  return {prototypes = result, total = #names,
    next_offset = offset + limit < #names and offset + limit or nil}
end

M.operations.recipes = function(s, p)
  local force = game.forces[p.force or (s.agent and s.agent.force.name) or "player"]
  local results = {}
  for name, recipe in pairs(force.recipes) do
    if (not p.query or name:find(p.query, 1, true)) and (p.include_locked or recipe.enabled) then
      results[#results + 1] = {name = name, enabled = recipe.enabled,
        categories = recipe.categories, energy = recipe.energy,
        ingredients = recipe.ingredients, products = recipe.products}
    end
  end
  table.sort(results, function(a, b) return a.name < b.name end)
  local out, offset, limit = {}, p.offset or 0, math.min(p.limit or 50, 500)
  for i = offset + 1, math.min(offset + limit, #results) do out[#out + 1] = results[i] end
  return {recipes = out, total = #results,
    next_offset = offset + limit < #results and offset + limit or nil}
end

M.operations.research = function(s, p)
  local force = game.forces[p.force or (s.agent and s.agent.force.name) or "player"]
  if p.start then assert(force.add_research(p.start), "Research could not be queued") end
  local available = {}
  for name, tech in pairs(force.technologies) do
    if tech.enabled and not tech.researched then
      local ready = true
      for _, prereq in pairs(tech.prerequisites) do if not prereq.researched then ready = false end end
      if ready then available[#available + 1] = name end
    end
  end
  table.sort(available)
  return {current = force.current_research and force.current_research.name or nil,
          progress = force.research_progress, available = available}
end

M.operations.trains = function(s, p)
  if p.manual_mode ~= nil or p.schedule or p.go_to_station then
    assert(p.train_id, "An explicit train_id is required when modifying a train")
  end
  local trains = game.train_manager.get_trains{force = p.force or "player", surface = p.surface}
  local out = {}
  for _, train in pairs(trains) do
    if not p.train_id or train.id == p.train_id then
      if p.manual_mode ~= nil then train.manual_mode = p.manual_mode end
      if p.schedule then train.schedule = p.schedule end
      if p.go_to_station then train.go_to_station(p.go_to_station) end
      local carriages = {}
      for _, carriage in pairs(train.carriages) do carriages[#carriages + 1] = M.entity(carriage, false, s) end
      out[#out + 1] = {id = train.id, state = train.state, manual_mode = train.manual_mode,
        speed = train.speed, schedule = train.schedule, group = train.group,
        station = train.station and train.station.backer_name or nil, carriages = carriages}
    end
  end
  return {trains = out}
end

return M
