local world = require("lib.world")
local M = {operations = {}}

local function alive(s)
  assert(s.agent and s.agent.valid and s.agent.health > 0, "AI character is absent or dead")
  return s.agent
end

local function stop(s, status, detail)
  if s.agent and s.agent.valid then
    s.agent.walking_state = {walking = false, direction = defines.direction.north}
    s.agent.mining_state = {mining = false}
    s.agent.shooting_state = {state = defines.shooting.not_shooting, position = s.agent.position}
  end
  if s.action then
    s.action.status, s.action.detail = status, detail
    s.action.finished_tick = game.tick
    s.last_action = s.action
    s.action = nil
  end
end

function M.initialize(s)
  if s.spawned then return end
  local surface = game.surfaces.nauvis or game.surfaces[1]
  local force = game.forces.player
  local pos = surface.find_non_colliding_position("character", force.get_spawn_position(surface), 32, 0.5)
  assert(pos, "No free space for the AI character near spawn")
  local character = surface.create_entity{name = "character", position = pos, force = force}
  assert(character, "Could not create AI character")
  character.name_tag = "LLM engineer"
  s.agent, s.spawned = character, true
end

local function distance(a, b)
  return math.sqrt((a.x - b.x)^2 + (a.y - b.y)^2)
end

local function target(s, p)
  local character = alive(s)
  local entity
  if p.unit_number then entity = world.target(s, p) end
  if not entity and p.position then
    local surface = game.surfaces[p.surface or character.surface.name]
    assert(surface, "Unknown surface")
    if p.name then entity = surface.find_entity(p.name, p.position)
    else
      for _, candidate in pairs(surface.find_entities_filtered{position = p.position}) do
        if candidate ~= character and candidate.type ~= "resource" then entity = candidate break end
        if candidate ~= character then entity = candidate end
      end
    end
  end
  assert(entity and entity.valid, "Target no longer exists")
  assert(entity.surface == character.surface, "Target is on another surface")
  assert(character.can_reach_entity(entity), "Target is outside interaction reach")
  return entity, character
end

local function begin(s, kind, p)
  assert(not s.action, "Another action is running; inspect or cancel it first")
  s.next_action = (s.next_action or 0) + 1
  local action = {id = tostring(s.next_action), type = kind, status = "running",
                  started_tick = game.tick, deadline = game.tick + 60 * (p.timeout or 120)}
  s.action = action
  return action
end

M.operations.agent_status = function(s)
  local a = alive(s)
  return {unit_number = a.unit_number, surface = a.surface.name, position = a.position,
          health = a.health, inventory = a.get_main_inventory().get_contents(),
          crafting_queue = a.crafting_queue,
          action = s.action and {id = s.action.id, type = s.action.type, status = s.action.status} or nil,
          last_action = s.last_action and {id = s.last_action.id, type = s.last_action.type,
                          status = s.last_action.status, detail = s.last_action.detail} or nil}
end

M.operations.move_to = function(s, p)
  local a = alive(s)
  assert(not p.surface or p.surface == a.surface.name, "Movement cannot teleport between surfaces")
  assert(type(p.x) == "number" and type(p.y) == "number", "A numeric x/y position is required")
  local action = begin(s, "move", p)
  action.goal, action.within = {x = p.x, y = p.y}, p.within or 0.5
  assert(action.within > 0, "within must be positive")
  action.path_request = a.surface.request_path{
    bounding_box = a.prototype.collision_box, collision_mask = a.prototype.collision_mask,
    start = a.position, goal = action.goal, force = a.force, radius = action.within,
    entity_to_ignore = a, pathfind_flags = {prefer_straight_paths = true}
  }
  return {action_id = action.id, status = action.status}
end

function M.path_finished(s, e)
  local action = s.action
  if not action or action.type ~= "move" or e.id ~= action.path_request then return end
  if e.path and #e.path > 0 then
    action.path, action.path_index = e.path, 1
  else stop(s, "failed", e.try_again_later and "Pathfinder is busy" or "No path") end
end

M.operations.mine_entity = function(s, p)
  local e, a = target(s, p)
  assert(e.force == a.force or e.force.name == "neutral", "Cannot mine another force's entity")
  local action = begin(s, "mine", p)
  action.target, action.count = e, p.count or 1
  action.start_count = a.get_main_inventory().get_item_count()
  return {action_id = action.id, status = "running"}
end

M.operations.craft = function(s, p)
  local a = alive(s)
  assert(not s.action, "Another action is running")
  assert(a.force.recipes[p.recipe] and a.force.recipes[p.recipe].enabled, "Recipe is unavailable")
  local count = p.count or 1
  assert(count > 0 and count % 1 == 0, "count must be a positive integer")
  local queued = a.begin_crafting{recipe = p.recipe, count = count, quality = p.quality}
  assert(queued > 0, "Missing crafting ingredients")
  local action = begin(s, "craft", p)
  action.recipe, action.count = p.recipe, queued
  return {action_id = action.id, queued = queued}
end

M.operations.action_status = function(s, p)
  for _, action in ipairs({s.action or false, s.last_action or false}) do
    if action and (not p.action_id or action.id == p.action_id) then
      return {action_id = action.id, type = action.type, status = action.status,
              detail = action.detail, started_tick = action.started_tick,
              finished_tick = action.finished_tick}
    end
  end
  return {status = "unknown"}
end

M.operations.cancel_action = function(s)
  local a = alive(s)
  if s.action and s.action.type == "craft" then
    while a.crafting_queue and #a.crafting_queue > 0 do
      a.cancel_crafting{index = 1, count = a.crafting_queue[1].count}
    end
  end
  stop(s, "cancelled", "Cancelled by caller")
  return {status = "cancelled"}
end

M.operations.place_entity = function(s, p)
  local a = alive(s)
  assert(not s.action, "Another action is running")
  local item = assert(prototypes.item[p.item], "Unknown item prototype")
  local prototype = assert(item.place_result, "Item does not place an entity; use native blueprints for tiles")
  local pos = assert(p.position, "position is required")
  assert(distance(a.position, pos) <= a.build_distance, "Position is outside building reach")
  local quality = p.quality or "normal"
  local stack = {name = p.item, count = 1, quality = quality}
  assert(a.get_item_count(stack) > 0, "Item is missing from the AI inventory")
  local args = {name = prototype.name, position = pos, force = a.force,
                direction = p.direction or 0, quality = quality}
  if p.underground_type then args.type = p.underground_type end
  assert(a.surface.can_place_entity(args), "Placement is blocked")
  assert(a.remove_item(stack) == 1, "Could not reserve the construction item")
  args.raise_built = true
  local ok, entity = pcall(a.surface.create_entity, args)
  if not ok or not entity then
    a.insert(stack)
    error(ok and "Placement failed; item returned" or tostring(entity))
  end
  world.remember(s, entity)
  return {unit_number = entity.unit_number, name = entity.name, position = entity.position,
          quality = entity.quality.name}
end

local function inventory(entity, index)
  if not index then return assert(entity.get_main_inventory(), "No main inventory") end
  local id = type(index) == "number" and index or defines.inventory[index]
  assert(id, "Unknown inventory index")
  return assert(entity.get_inventory(id), "This entity has no such inventory")
end

M.operations.entity_inventory = function(s, p)
  local e = target(s, p)
  local inv = inventory(e, p.inventory)
  return {contents = inv.get_contents(), slots = #inv, empty_slots = inv.count_empty_stacks()}
end

M.operations.transfer_items = function(s, p)
  assert(not s.action, "Another action is running")
  local e, a = target(s, p)
  local entity_inv, agent_inv = inventory(e, p.inventory), a.get_main_inventory()
  local source, destination = agent_inv, entity_inv
  if p.direction == "from_entity" then source, destination = entity_inv, agent_inv
  else assert(p.direction == "to_entity", "direction must be to_entity or from_entity") end
  assert(type(p.count) == "number" and p.count > 0 and p.count % 1 == 0, "Invalid count")
  local stack = {name = p.item, quality = p.quality or "normal", count = p.count}
  local removed = source.remove(stack)
  stack.count = removed
  local inserted = removed > 0 and destination.insert(stack) or 0
  if inserted < removed then stack.count = removed - inserted source.insert(stack) end
  return {transferred = inserted, source_count = source.get_item_count(stack),
          destination_count = destination.get_item_count(stack)}
end

M.operations.configure_entity = function(s, p)
  local e, a = target(s, p)
  assert(e.force == a.force, "Cannot configure another force's entity")
  if p.recipe then e.set_recipe(p.recipe, p.quality) end
  if p.rotate then e.rotate{reverse = p.reverse or false} end
  if p.direction then e.direction = p.direction end
  if p.station_name then assert(e.type == "train-stop", "Target is not a station") e.backer_name = p.station_name end
  if p.control_parameters then
    local control = assert(e.get_or_create_control_behavior(), "Entity has no control behavior")
    control.parameters = p.control_parameters
  end
  return {name = e.name, position = e.position, direction = e.direction}
end

M.operations.shoot_at = function(s, p)
  local action = begin(s, "shoot", p)
  action.goal = assert(p.position, "position is required")
  action.deadline = game.tick + 60 * math.min(p.seconds or 2, 30)
  return {action_id = action.id, status = "running"}
end

function M.tick(s)
  if not s.spawned then M.initialize(s) end
  local action = s.action
  if not action then return end
  if not s.agent or not s.agent.valid or s.agent.health <= 0 then stop(s, "failed", "Character died") return end
  local a = s.agent
  if game.tick - (s.heartbeat or action.started_tick) > 600 then
    if action.type == "craft" then M.operations.cancel_action(s) end
    stop(s, "cancelled", "Controller heartbeat expired") return
  end
  if game.tick > action.deadline then
    stop(s, action.type == "shoot" and "succeeded" or "failed", "Action time elapsed") return
  end
  if action.type == "move" then
    if distance(a.position, action.goal) <= action.within then stop(s, "succeeded") return end
    if not action.path then return end
    local waypoint = action.path[action.path_index]
    if waypoint and distance(a.position, waypoint.position) < 0.4 then
      action.path_index = action.path_index + 1
      waypoint = action.path[action.path_index]
    end
    local pos = waypoint and waypoint.position or action.goal
    local angle = math.atan2(pos.x - a.position.x, a.position.y - pos.y)
    local direction = (math.floor(angle / (math.pi / 4) + 0.5) * 2) % 16
    a.walking_state = {walking = true, direction = direction}
  elseif action.type == "mine" then
    if not action.target.valid or a.get_main_inventory().get_item_count() >= action.start_count + action.count then
      stop(s, "succeeded") return
    end
    if not a.can_reach_entity(action.target) then stop(s, "failed", "Target moved out of reach") return end
    a.selected = action.target
    a.mining_state = {mining = true, position = action.target.position}
  elseif action.type == "craft" then
    if not a.crafting_queue or #a.crafting_queue == 0 then stop(s, "succeeded") end
  elseif action.type == "shoot" then
    a.shooting_state = {state = defines.shooting.shooting_enemies, position = action.goal}
  end
end

return M
