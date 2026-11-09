-- Archipelago item -> in-game action mapping.
--
-- Transport / progression items without a physical object are tracked by
-- global.lua (owned table): they unlock travel services.
local M = {}
local levelUp = require('scripts.ap.level_up')
local FACTION_REQ = require('scripts.ap.faction_requirements')
local GOALS = require('scripts.ap.goals')

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

-- Quest rewards (data/quest_rewards.yaml -> quest_rewards.lua): the vanilla
-- reward is removed by player.lua / global.lua and replaced by a check; the
-- matching AP item gives it back (same record, same quantity).
local REWARDS = require('scripts.ap.quest_rewards')
local REWARD_BY_ITEM = {}
for _, r in ipairs(REWARDS) do
  GIVE[r.item] = { r.record, r.count }
  REWARD_BY_ITEM[r.item] = r
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

-- Number of copies of each record the player may hold, for the quest items
-- ALREADY received from Archipelago: { recordId = count }.
-- Used to remove the duplicate when the vanilla copy lying in the world is
-- picked up after the AP copy was given (the suppression only removes the
-- vanilla copy as long as the AP item has not been received).
-- Several AP ids can give the same record (e.g. a scroll shared by two
-- goals): the allowed counts are added, one time per AP id.
function M.allowedCounts(goals, owned)
  if type(goals) == 'string' then goals = { goals } end
  local out, seen = {}, {}
  for _, goal in ipairs(goals or {}) do
    for _, it in ipairs(QUEST_ITEMS[goal] or {}) do
      if it.give and it.suppress and owned[it.id] and not seen[it.id] then
        seen[it.id] = true
        local record, count = it.give[1], it.give[2] or 1
        out[record] = (out[record] or 0) + count
      end
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
    -- Reward given back by Archipelago: tell the player script so that it
    -- does not mistake this copy for the vanilla reward (player.lua).
    if ok and REWARD_BY_ITEM[itemId] then
      pcall(function() player:sendEvent('AP_RewardGiven', { record = g[1], count = g[2] }) end)
    end
    return true
  end

  local sp = SPELLS[itemId]
  if sp then
    giveSpells(player, sp)
    return true
  end

  -- (Strength bonus removed)

  -- Trap: damage = 90% of the player's max health (applied by player.lua,
  -- which never kills: leaves at least 1 HP).
  if itemId == 7701200 then
    return true, { type = 'damage', fraction = 0.9 }
  end

  -- Trap: bounty
  if itemId == 7701201 then
    pcall(function()
      local cur = types.Player.getCrimeLevel(player)
      types.Player.setCrimeLevel(player, (cur or 0) + 1000)
    end)
    return true
  end

  -- Trap: summon a hostile scamp next to the player
  if itemId == 7701202 then
    local ok, err = pcall(function()
      local world = require('openmw.world')
      local util = require('openmw.util')
      -- Position: 150 units in front of the player (teleport needs a
      -- util.vector3, not a plain table).
      local offset = player.rotation:apply(util.vector3(0, 150, 0))
      local pos = player.position + offset
      local c = world.createObject('scamp', 1)
      if not c then error('createObject(scamp) returned nil') end
      c:teleport(player.cell, pos)
      -- Hostile on arrival (handled in actor.lua, attached to creatures).
      c:sendEvent('AP_Attack', { target = player })
      print('AP: scamp trap spawned')
    end)
    if not ok then print('AP: scamp trap failed: ' .. tostring(err)) end
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

  -- "<faction> Requirements added": stats are only writable from openmw.self,
  -- so the effect is relayed to player.lua (see faction_requirements.lua).
  local goalKey = FACTION_REQ.GOAL_BY_ITEM[itemId]
  if goalKey then
    local g = GOALS[goalKey]
    if g and g.faction then
      return true, { type = 'faction_requirements', faction = g.faction, goal = goalKey }
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
