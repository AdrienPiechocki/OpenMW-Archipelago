-- "<faction> Requirements added" Archipelago items.
--
-- One progression item per faction goal (great house, guild, faction). When
-- it is received, the player's attributes and skills are raised to the MAXIMUM
-- rank requirements of that faction, read from the faction record itself
-- (core.factions), so it also works for Tamriel Rebuilt / Bloodmoon factions
-- without any hardcoded table:
--   * the 2 faction attributes     -> max of rank.attributeValues over all ranks,
--   * the faction skills           -> the player's best faction skill reaches the
--     max primarySkillValue, every other faction skill reaches the max
--     favouredSkillValue (this is exactly what the engine checks to promote:
--     best skill >= primary, next skill >= favoured).
-- Stats are never lowered and capped at 100.
--
-- Item ids must stay in sync with apworld/morrowind_openmw/items.py
-- (FACTION_REQUIREMENTS).
local M = {}

M.CAP = 100

-- goal key (goals.lua) -> AP item id
M.ITEM_IDS = {
  hlaalu = 7701500, redoran = 7701501, telvanni = 7701502, indoril = 7701503,
  fighters_guild = 7701504, mages_guild = 7701505, thieves_guild = 7701506,
  imperial_cult = 7701507, imperial_legion = 7701508, temple = 7701509,
  morag_tong = 7701510, east_empire_company = 7701511, ja_natta_syndicate = 7701512,
}

M.GOAL_BY_ITEM = {}
for goal, id in pairs(M.ITEM_IDS) do M.GOAL_BY_ITEM[id] = goal end

-- Pure function (no engine access, unit-testable).
-- `rec`: faction record { name, attributes = {ids}, skills = {ids},
-- ranks = { {attributeValues = {a1, a2}, primarySkillValue, favouredSkillValue}... } }
-- `getBase(kind, id)`: current base value of an attribute ('attribute') or skill ('skill').
-- Returns { attributes = { id = value }, skills = { id = value } }: the target
-- values (already >= current ones), or nil if the record is unusable.
function M.compute(rec, getBase)
  if type(rec) ~= 'table' or type(rec.ranks) ~= 'table' then return nil end
  local maxAttr, maxPrimary, maxFavoured = {}, 0, 0
  for _, rank in ipairs(rec.ranks) do
    for i, v in ipairs(rank.attributeValues or {}) do
      v = tonumber(v) or 0
      if v > (maxAttr[i] or 0) then maxAttr[i] = v end
    end
    maxPrimary = math.max(maxPrimary, tonumber(rank.primarySkillValue) or 0)
    maxFavoured = math.max(maxFavoured, tonumber(rank.favouredSkillValue) or 0)
  end

  local out = { attributes = {}, skills = {} }
  for i, id in ipairs(rec.attributes or {}) do
    local want = math.min(M.CAP, maxAttr[i] or 0)
    local cur = tonumber(getBase('attribute', id)) or 0
    out.attributes[id] = math.max(cur, want)
  end

  -- The faction skill the player is already best at carries the "primary" value.
  local ids = {}
  for _, id in ipairs(rec.skills or {}) do ids[#ids + 1] = id end
  table.sort(ids, function(a, b)
    local ba, bb = tonumber(getBase('skill', a)) or 0, tonumber(getBase('skill', b)) or 0
    if ba ~= bb then return ba > bb end
    return a < b
  end)
  for n, id in ipairs(ids) do
    local want = math.min(M.CAP, n == 1 and maxPrimary or maxFavoured)
    local cur = tonumber(getBase('skill', id)) or 0
    out.skills[id] = math.max(cur, want)
  end
  return out
end

-- Reads the faction record (lowercase id, e.g. 'fighters guild').
local function loadRecord(core, factionId)
  local id = tostring(factionId):lower()
  local ok, rec = pcall(function() return core.factions.records[id] end)
  if ok and rec then return rec end
  ok, rec = pcall(function() return core.factions.record(id) end)
  if ok and rec then return rec end
  return nil
end

-- Applies the requirements to `actor` (the player, from its local script).
-- Returns the number of stats raised, or nil + error message.
function M.apply(core, types, actor, factionId)
  local rec = loadRecord(core, factionId)
  if not rec then return nil, 'faction record not found: ' .. tostring(factionId) end
  local function getBase(kind, id)
    if kind == 'attribute' then return types.Actor.stats.attributes[id](actor).base end
    return types.NPC.stats.skills[id](actor).base
  end
  local ok, target = pcall(M.compute, rec, getBase)
  if not ok or not target then return nil, 'cannot read requirements: ' .. tostring(target) end

  local raised = 0
  for id, v in pairs(target.attributes) do
    pcall(function()
      local stat = types.Actor.stats.attributes[id](actor)
      if v > (stat.base or 0) then stat.base = v raised = raised + 1 end
    end)
  end
  for id, v in pairs(target.skills) do
    pcall(function()
      local stat = types.NPC.stats.skills[id](actor)
      if v > (stat.base or 0) then stat.base = v raised = raised + 1 end
    end)
  end
  return raised
end

return M
