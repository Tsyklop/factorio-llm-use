local world = require("lib.world")
local M = {operations = {}}

local function attempt(fn)
  local ok, value = pcall(fn)
  if ok then return value end
end

local function owned(s)
  if not s.blueprints or not s.blueprints.valid then s.blueprints = game.create_inventory(16) end
  return s.blueprints
end

local function allocate(s)
  local inv = owned(s)
  for i = 1, #inv do if not inv[i].valid_for_read then return inv[i], i end end
  local index = #inv + 1
  inv.resize(#inv * 2)
  return inv[index], index
end

local function export(record)
  if record.object_name == "LuaRecord" then return record.export_record() end
  return record.export_stack()
end

local function children(record)
  if record.object_name == "LuaRecord" then return attempt(function() return record.contents end) end
  if record.valid_for_read and record.is_blueprint_book then return record.get_inventory(defines.inventory.item_main) end
end

local function resolve(s, ref)
  assert(type(ref) == "string", "A blueprint reference is required")
  local parts = {}
  for value in ref:gmatch("[^/]+") do parts[#parts + 1] = value end
  local record, index
  if parts[1] == "stored" then record, index = owned(s)[tonumber(parts[2])], 3
  elseif parts[1] == "game" then record, index = game.blueprints[tonumber(parts[2])], 3
  elseif parts[1] == "player" then
    local player = assert(game.get_player(tonumber(parts[2])), "Player no longer exists")
    record, index = player.blueprints[tonumber(parts[3])], 4
  elseif parts[1] == "inventory" then
    local player = assert(game.get_player(tonumber(parts[2])), "Player no longer exists")
    record, index = player.get_main_inventory()[tonumber(parts[3])], 4
  end
  assert(record and record.valid, "Blueprint reference no longer exists")
  for i = index or 1, #parts do record = assert(children(record), "Reference is not a book")[tonumber(parts[i])] end
  assert(record and record.valid, "Blueprint reference no longer exists")
  return record
end

local function metadata(record, ref)
  local book = children(record)
  local result = {ref = ref, label = attempt(function() return record.label end), kind = book and "book" or "blueprint"}
  if not book then
    result.entity_count = attempt(function() return record.get_blueprint_entity_count() end)
    result.cost = attempt(function() return record.cost_to_build end)
    result.snap_to_grid = attempt(function() return record.blueprint_snap_to_grid end)
  end
  return result
end

local function visit(record, ref, output, query, recursive)
  if not record or not record.valid then return end
  if record.object_name ~= "LuaRecord" and not record.valid_for_read then return end
  local book = children(record)
  local count = not book and attempt(function() return record.get_blueprint_entity_count() end)
  if not book and not count then return end
  local data = metadata(record, ref)
  if not query or (data.label or ""):lower():find(query:lower(), 1, true) then output[#output + 1] = data end
  if book and recursive then
    if record.object_name == "LuaRecord" then
      for i, child in pairs(book) do visit(child, ref .. "/" .. i, output, query, recursive) end
    else
      for i = 1, #book do visit(book[i], ref .. "/" .. i, output, query, recursive) end
    end
  end
end

M.operations.blueprint_catalog = function(s, p)
  local output = {}
  local recursive = p.recursive or p.query ~= nil
  if p.ref then visit(resolve(s, p.ref), p.ref, output, p.query, true)
  else
    for i, record in pairs(game.blueprints) do visit(record, "game/" .. i, output, p.query, recursive) end
    for _, player in pairs(game.players) do
      for i, record in pairs(player.blueprints) do
        visit(record, "player/" .. player.index .. "/" .. i, output, p.query, recursive)
      end
      local inv = player.get_main_inventory()
      if inv then for i = 1, #inv do visit(inv[i], "inventory/" .. player.index .. "/" .. i, output, p.query, recursive) end end
    end
    local inv = owned(s)
    for i = 1, #inv do visit(inv[i], "stored/" .. i, output, p.query, recursive) end
  end
  table.sort(output, function(a, b) return a.ref < b.ref end)
  local result, offset, limit = {}, p.offset or 0, math.min(p.limit or 100, 1000)
  for i = offset + 1, math.min(offset + limit, #output) do result[#result + 1] = output[i] end
  return {blueprints = result, total = #output,
          next_offset = offset + limit < #output and offset + limit or nil}
end

M.operations.blueprint_import = function(s, p)
  local stack, index = allocate(s)
  stack.set_stack("blueprint")
  local data = assert(p.data, "Blueprint string is required")
  local ok, result = pcall(stack.import_stack, data)
  if not ok or result == 1 then stack.clear() error(ok and "Invalid blueprint string" or tostring(result)) end
  return metadata(stack, "stored/" .. index)
end

M.operations.blueprint_export = function(s, p)
  return {data = export(resolve(s, p.ref))}
end

M.operations.blueprint_capture = function(s, p)
  assert(p.area, "Capture area is required")
  local stack, index = allocate(s)
  stack.set_stack("blueprint")
  local map = stack.create_blueprint{surface = world.surface(s, p), force = p.force or "player",
    area = p.area, always_include_tiles = p.include_tiles or false,
    include_entities = true, include_modules = true, include_station_names = true,
    include_trains = p.include_trains or false}
  stack.label = p.label or "Captured layout"
  local result = metadata(stack, "stored/" .. index)
  result.captured_entities = 0
  for _ in pairs(map) do result.captured_entities = result.captured_entities + 1 end
  return result
end

local function rotate(pos, direction)
  local turns = ((direction or 0) % 16) / 4
  assert(turns % 1 == 0, "Blueprint direction must be 0, 4, 8 or 12")
  local x, y = pos.x, pos.y
  for _ = 1, turns do x, y = -y, x end
  return {x = x, y = y}
end

local function bounds(record, position, direction)
  local box = {left_top = {x = math.huge, y = math.huge}, right_bottom = {x = -math.huge, y = -math.huge}}
  local function include(pos, dx, dy)
    local p = rotate(pos, direction)
    box.left_top.x = math.min(box.left_top.x, p.x + position.x - dx)
    box.left_top.y = math.min(box.left_top.y, p.y + position.y - dy)
    box.right_bottom.x = math.max(box.right_bottom.x, p.x + position.x + dx)
    box.right_bottom.y = math.max(box.right_bottom.y, p.y + position.y + dy)
  end
  for _, entity in pairs(record.get_blueprint_entities() or {}) do
    local proto = prototypes.entity[entity.name]
    local selection = proto and proto.selection_box
    local dx = selection and math.max(math.abs(selection.left_top.x), math.abs(selection.right_bottom.x)) or 0.5
    local dy = selection and math.max(math.abs(selection.left_top.y), math.abs(selection.right_bottom.y)) or 0.5
    if ((entity.direction or 0) + (direction or 0)) % 8 == 4 then dx, dy = dy, dx end
    include(entity.position, dx, dy)
  end
  for _, tile in pairs(record.get_blueprint_tiles() or {}) do include(tile.position, 0.5, 0.5) end
  assert(box.left_top.x ~= math.huge, "Blueprint is empty")
  return box
end

M.operations.blueprint_inspect = function(s, p)
  local record = resolve(s, p.ref)
  local result = metadata(record, p.ref)
  if result.kind == "book" then return result end
  local entities = record.get_blueprint_entities() or {}
  local counts, stations = {}, {}
  for _, entity in pairs(entities) do
    counts[entity.name] = (counts[entity.name] or 0) + 1
    if entity.station then stations[#stations + 1] = {name = entity.station, position = entity.position, direction = entity.direction} end
  end
  result.counts, result.stations = counts, stations
  result.bounds = bounds(record, {x = 0, y = 0}, p.direction)
  if p.include_entities then result.entities = entities result.tiles = record.get_blueprint_tiles() end
  return result
end

M.operations.find_sites = function(s, p)
  local record = resolve(s, p.ref)
  local surface = world.surface(s, p)
  local area = assert(p.area, "Search area is required")
  local lt, rb = area.left_top or {x = area[1][1], y = area[1][2]}, area.right_bottom or {x = area[2][1], y = area[2][2]}
  local step, offset = p.step or 32, p.offset or 0
  assert(step >= 1 and offset >= 0, "Invalid search grid")
  local result, scanned, index = {}, 0, 0
  local limit = math.min(p.limit or 200, 1000)
  for y = lt.y, rb.y, step do
    for x = lt.x, rb.x, step do
      if index >= offset and scanned < limit then
        local box = bounds(record, {x = x, y = y}, p.direction)
        local occupied = surface.count_entities_filtered{area = box, force = p.force or "player"}
        local water = surface.count_tiles_filtered{area = box, collision_mask = "water_tile"}
        local resources = surface.count_entities_filtered{area = box, type = "resource"}
        local cliffs = surface.count_entities_filtered{area = box, type = "cliff"}
        if occupied == 0 and water == 0 and cliffs == 0 and (p.allow_resources or resources == 0) then
          result[#result + 1] = {position = {x = x, y = y}, bounds = box,
            trees = surface.count_entities_filtered{area = box, type = "tree"}, resources = resources}
        end
        scanned = scanned + 1
      end
      index = index + 1
    end
  end
  return {sites = result, scanned = scanned, total_grid_points = index,
    next_offset = offset + scanned < index and offset + scanned or nil,
    note = "Candidate footprints only; validate the assembled plan and rail connections before applying."}
end

M.operations.plan_create = function(s, p)
  assert(type(p.components) == "table" and #p.components > 0, "Plan components are required")
  s.plans = s.plans or {}
  s.next_plan = (s.next_plan or 0) + 1
  local plan = {id = tostring(s.next_plan), label = p.label or "Construction plan", status = "draft",
                surface = world.surface(s, p).name, force = p.force or "player", components = {}}
  for _, component in ipairs(p.components) do
    local source = resolve(s, component.ref)
    assert(not children(source), "A plan component must reference a blueprint, not a book")
    local copy = M.operations.blueprint_import(s, {data = export(source)})
    local position = assert(component.position, "Component position is required")
    plan.components[#plan.components + 1] = {ref = copy.ref, source_ref = component.ref,
      position = position, direction = component.direction or 0,
      bounds = bounds(resolve(s, copy.ref), position, component.direction),
      entity_count = copy.entity_count, label = component.label or copy.label}
  end
  s.plans[plan.id] = plan
  return plan
end

M.operations.plan_inspect = function(s, p)
  return assert(s.plans and s.plans[p.plan_id], "Unknown plan")
end

M.operations.plan_preview = function(s, p)
  local plan = M.operations.plan_inspect(s, p)
  for _, component in ipairs(plan.components) do
    rendering.draw_rectangle{surface = plan.surface, left_top = component.bounds.left_top,
      right_bottom = component.bounds.right_bottom, color = {r = 0.2, g = 0.8, b = 1},
      width = 3, time_to_live = 60 * (p.seconds or 60), forces = {plan.force}}
    rendering.draw_text{surface = plan.surface, target = component.bounds.left_top,
      text = component.label or component.ref, color = {r = 0.2, g = 0.8, b = 1},
      scale = 1.5, time_to_live = 60 * (p.seconds or 60), forces = {plan.force}}
  end
  return {plan_id = plan.id, status = "preview", created_ghosts = 0,
          note = "Visual overlay only. No buildings, ghosts or deconstruction orders were created."}
end

M.operations.plan_apply = function(s, p)
  local plan = M.operations.plan_inspect(s, p)
  assert(p.mode == "ghosts", "Explicit mode=ghosts is required; real construction consumes normal supplies")
  if plan.status == "applied" then return {plan_id = plan.id, status = "already_applied", created_ghosts = 0} end
  local surface, created = game.surfaces[plan.surface], {}
  local ok, reason = pcall(function()
    for _, component in ipairs(plan.components) do
      local ghosts = resolve(s, component.ref).build_blueprint{
        surface = surface, force = plan.force, position = component.position,
        direction = component.direction, build_mode = defines.build_mode.normal,
        skip_fog_of_war = true, raise_built = true}
      assert(ghosts and #ghosts > 0, "A component created no ghosts; placement may be blocked or already built")
      for _, ghost in pairs(ghosts) do if ghost.valid then created[#created + 1] = ghost end end
    end
  end)
  if not ok then
    for _, ghost in pairs(created) do
      if ghost.valid and (ghost.type == "entity-ghost" or ghost.type == "tile-ghost") then
        ghost.destroy{raise_destroy = true}
      end
    end
    error(tostring(reason))
  end
  plan.status, plan.applied_tick, plan.created_ghosts = "applied", game.tick, #created
  return {plan_id = plan.id, status = "applied", created_ghosts = #created,
          note = "Native construction robots may build these ghosts immediately if supplied."}
end

return M
