-- Archipelago item -> in-game action mapping.
--
-- Transport / progression items without a physical object are tracked by
-- global.lua (owned table): they unlock travel services.
local M = {}
local levelUp = require('scripts.ap.level_up')

-- Objects given directly to the inventory.
-- keys = AP id, value = { recordId, quantity }
local GIVE = {
  [7701001] = { 'gold_001', 100 },
  [7701002] = { 'p_restore_health_s', 1 },
  [7701003] = { 'misc_soulgem_common', 1 },
  [7701004] = { 'chitin arrow', 30 },
}

-- Spells added to the player.
local SPELLS = {}

-- Quest items per goal (data/quest_items.yaml -> quest_items.lua):
-- given by Archipelago, and removed from the inventory if they come from
-- quests as long as the matching AP item has not been received.
local QUEST_ITEMS = require('scripts.ap.quest_items')
for _, list in pairs(QUEST_ITEMS) do
  for _, it in ipairs(list) do
    if it.give then GIVE[it.id] = it.give end
    if it.spells then SPELLS[it.id] = it.spells end
  end
end

-- Table { apId = { recordIds } } of objects to suppress for the given
-- goals (list of keys, or one key). Without a known goal (config not yet
-- received): nothing is suppressed.
function M.suppressFor(goals)
  if type(goals) == 'string' then goals = { goals } end
  local out = {}
  for _, goal in ipairs(goals or {}) do
    for _, it in ipairs(QUEST_ITEMS[goal] or {}) do
      if it.suppress then out[it.id] = it.suppress end
    end
  end
  return out
end

-- Object required by the vanilla CharGenDoorExitCaptain script to leave the
-- Census Office. While the player is inside the building, it is kept (and
-- recreated if missing), even if the AP item has not been received yet.
M.CENSUS_PACKAGE = 'bk_a1_1_caiuspackage'

-- True if the list of objects to suppress contains the package and the player
-- is still in the Census Office. We rely on the record rather than on a
-- hardcoded AP id: the ids in data/quest_items.yaml may change.
function M.keepInCensus(records, inCensus)
  if not inCensus then return false end
  for _, recordId in ipairs(records or {}) do
    if recordId == M.CENSUS_PACKAGE then return true end
  end
  return false
end

local function giveObject(player, recordId, count)
  local world = require('openmw.world')
  local types = require('openmw.types')
  local obj = world.createObject(recordId, count or 1)
  if not obj then return false end
  obj:moveInto(types.Actor.inventory(player))
  return true
end

local function giveSpells(player, ids)
  local types = require('openmw.types')
  local spells = types.Actor.spells(player)
  for _, id in ipairs(ids) do
    pcall(function() spells:add(id) end)
  end
  return true
end

-- Apply an item. Returns true if the item was handled (even if the exact
-- effect is unknown), false otherwise.
function M.apply(player, itemId, idx)
  local types = require('openmw.types')

  local g = GIVE[itemId]
  if g then
    print('AP: apply ' .. tostring(itemId) .. ' -> give ' .. tostring(g[1]) .. ' x' .. tostring(g[2]))
    local ok = giveObject(player, g[1], g[2])
    print('AP: giveObject(' .. tostring(g[1]) .. ') = ' .. tostring(ok))
    return true
  end

  local sp = SPELLS[itemId]
  if sp then
    giveSpells(player, sp)
    return true
  end

  -- (Strength bonus removed)

  -- Trap: disease / ambush
  if itemId == 7701200 then
    pcall(function()
      local inv = types.Actor.inventory(player)
      local gold = inv:find('gold_001')
      if gold then
        local n = math.min(gold.count or 0, 100)
        if n > 0 then gold:remove(n) end
      end
    end)
    pcall(function()
      local health = types.Actor.stats.dynamic.health(player)
      local cur = health.current or 0
      health.current = math.max(1, cur - 20)
    end)
    pcall(function()
      local world = require('openmw.world')
      local pos = player.position
      local c = world.createObject('cliff racer', 1)
      if c and pos then
        c:teleport(player.cell, { x = pos.x + 200, y = pos.y + 200, z = pos.z })
      end
    end)
    return true
  end

  -- Trap: bounty
  if itemId == 7701201 then
    pcall(function()
      local cur = types.Player.getCrimeLevel(player)
      types.Player.setCrimeLevel(player, (cur or 0) + 1000)
    end)
    return true
  end

  -- Trap: summon a scamp
  if itemId == 7701202 then
    pcall(function()
      local world = require('openmw.world')
      local pos = player.position
      local c = world.createObject('scamp', 1)
      if c and pos then
        c:teleport(player.cell, { x = pos.x + 200, y = pos.y + 200, z = pos.z })
      end
    end)
    return true
  end

  -- Trap: gold theft
  if itemId == 7701203 then
    pcall(function()
      local types = require('openmw.types')
      local inv = types.Actor.inventory(player)
      local gold = inv:find('gold_001')
      if gold then
        local n = math.min(gold.count or 0, 250)
        if n > 0 then gold:remove(n) end
      end
    end)
    return true
  end

  -- +10 levels: progression is added by player.lua, because stat setters
  -- are only allowed on openmw.self (not from the global script). The
  -- effect is returned to be relayed to the player.
  if itemId == levelUp.ITEM_ID then
    return true, { type = 'level_up', levels = levelUp.LEVELS }
  end

  -- Skill levels: +5 to the matching skill
  if itemId >= 7701300 and itemId <= 7701326 then
    local SKILLS = {
      [7701300] = 'acrobatics', [7701301] = 'alchemy', [7701302] = 'alteration',
      [7701303] = 'armorer', [7701304] = 'athletics', [7701305] = 'axe',
      [7701306] = 'block', [7701307] = 'bluntweapon', [7701308] = 'conjuration',
      [7701309] = 'destruction', [7701310] = 'enchant', [7701311] = 'handtohand',
      [7701312] = 'heavyarmor', [7701313] = 'illusion', [7701314] = 'lightarmor',
      [7701315] = 'longblade', [7701316] = 'marksman', [7701317] = 'mediumarmor',
      [7701318] = 'mercantile', [7701319] = 'mysticism', [7701320] = 'restoration',
      [7701321] = 'security', [7701322] = 'shortblade', [7701323] = 'sneak',
      [7701324] = 'spear', [7701325] = 'speechcraft', [7701326] = 'unarmored',
    }
    local skill = SKILLS[itemId]
    if skill then
      -- Stat setters are only allowed on openmw.self: relayed to player.lua.
      return true, { type = 'skill', skill = skill, amount = 15 }
    end
    return true
  end

  -- Transport / progression items without an object: nothing to give,
  -- possession is tracked by global.lua.
  if itemId >= 7701100 and itemId <= 7701114 then
    return true
  end

  return false
end

return M
