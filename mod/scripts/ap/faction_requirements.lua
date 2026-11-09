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

-- Size of an array-like value, or -1 if it is not indexable. Works for plain
-- Lua tables AND for OpenMW read-only lists / usertypes (`#t` and `t[i]` are
-- guaranteed by the API for lists, `type(t) == 'table'` is NOT).
local function listLen(t)
  if t == nil then return -1 end
  local ok, n = pcall(function() return #t end)
  if ok and tonumber(n) and tonumber(n) >= 0 then return tonumber(n) end
  return -1
end

-- Iterate an array-like value by index (works for OpenMW lists).
local function listValues(t)
  local n = listLen(t)
  local i = 0
  return function()
    i = i + 1
    if i <= n then return i, t[i] end
  end
end

-- Filter out empty / nil / non-string ids: faction records may have unfilled
-- skill or attribute slots, and calling types.NPC.stats.skills[''] or an
-- unknown id would throw.
local function validIds(list)
  local out = {}
  for _, id in listValues(list) do
    if type(id) == 'string' and id ~= '' then out[#out + 1] = id end
  end
  return out
end

-- Pure function (no engine access, unit-testable).
-- `rec`: faction record { name, attributes = {ids}, skills = {ids},
-- ranks = { {attributeValues = {a1, a2}, primarySkillValue, favouredSkillValue}... } }
-- `getBase(kind, id)`: current base value of an attribute ('attribute') or skill ('skill').
-- Returns { attributes = { id = value }, skills = { id = value } }: the target
-- values (already >= current ones), or nil + error message if the record is unusable.
function M.compute(rec, getBase)
  if rec == nil then return nil, 'faction record is nil' end
  local ranks = rec.ranks
  if ranks == nil then
    return nil, ('faction record has no ranks (type=%s)'):format(type(rec))
  end
  local nRanks = listLen(ranks)
  if nRanks < 0 then
    return nil, ('faction ranks is not a list (type=%s)'):format(type(ranks))
  end

  local maxAttr, maxPrimary, maxFavoured = {}, 0, 0
  for i = 1, nRanks do
    local rank = ranks[i]
    if type(rank) == 'table' then
      for j, v in listValues(rank.attributeValues) do
        v = tonumber(v) or 0
        if v > (maxAttr[j] or 0) then maxAttr[j] = v end
      end
      maxPrimary = math.max(maxPrimary, tonumber(rank.primarySkillValue) or 0)
      maxFavoured = math.max(maxFavoured, tonumber(rank.favouredSkillValue) or 0)
    elseif rank ~= nil then
      -- OpenMW may expose ranks as usertypes too: read fields defensively.
      local okA, av = pcall(function() return rank.attributeValues end)
      if okA and av ~= nil then
        for j, v in listValues(av) do
          v = tonumber(v) or 0
          if v > (maxAttr[j] or 0) then maxAttr[j] = v end
        end
      end
      local okP, p = pcall(function() return rank.primarySkillValue end)
      if okP then maxPrimary = math.max(maxPrimary, tonumber(p) or 0) end
      local okF, f = pcall(function() return rank.favouredSkillValue end)
      if okF then maxFavoured = math.max(maxFavoured, tonumber(f) or 0) end
    end
  end

  -- Never let a bad id in getBase crash the whole computation: a single
  -- unknown skill would otherwise abort the entire item application.
  local function safeBase(kind, id)
    local ok, v = pcall(getBase, kind, id)
    if not ok then
      print('AP: cannot read base ' .. kind .. ' "' .. tostring(id) .. '": ' .. tostring(v))
      return 0
    end
    return tonumber(v) or 0
  end

  local out = { attributes = {}, skills = {} }
  local attrOk, attrList = pcall(function() return rec.attributes end)
  local attrIds = validIds(attrOk and attrList or nil)
  for i, id in ipairs(attrIds) do
    local want = math.min(M.CAP, maxAttr[i] or 0)
    local cur = safeBase('attribute', id)
    out.attributes[id] = math.max(cur, want)
  end

  -- The faction skill the player is already best at carries the "primary" value.
  local skillsOk, skillsList = pcall(function() return rec.skills end)
  local ids = validIds(skillsOk and skillsList or nil)
  table.sort(ids, function(a, b)
    local ba, bb = safeBase('skill', a), safeBase('skill', b)
    if ba ~= bb then return ba > bb end
    return a < b
  end)
  for n, id in ipairs(ids) do
    local want = math.min(M.CAP, n == 1 and maxPrimary or maxFavoured)
    local cur = safeBase('skill', id)
    out.skills[id] = math.max(cur, want)
  end
  return out
end

-- Reads the faction record (lowercase id, e.g. 'fighters guild').
local function loadRecord(core, factionId)
  local id = tostring(factionId):lower()
  local ok, rec = pcall(function() return core.factions.records[id] end)
  if ok and rec then return rec, 'records' end
  ok, rec = pcall(function() return core.factions.record(id) end)
  if ok and rec then return rec, 'record()' end
  return nil, 'not found: ' .. id
end

-- Applies the requirements to `actor` (the player, from its local script).
-- Returns the number of stats raised, or nil + error message.
function M.apply(core, types, actor, factionId)
  local rec, via = loadRecord(core, factionId)
  if not rec then return nil, 'faction record not found: ' .. tostring(factionId) end
  -- One-time diagnostic: this is what compute will actually see.
  local diagKey = tostring(factionId)
  if not M._diagDone then M._diagDone = {} end
  if not M._diagDone[diagKey] then
    M._diagDone[diagKey] = true
    local ranks = rec.ranks
    print(('AP: faction record %s (via %s): type=%s ranks=%s (#=%s)'):format(
      diagKey, tostring(via), type(rec), type(ranks), tostring(listLen(ranks))))
  end
  local function getBase(kind, id)
    if kind == 'attribute' then return types.Actor.stats.attributes[id](actor).base end
    return types.NPC.stats.skills[id](actor).base
  end
  local ok, target, err = pcall(M.compute, rec, getBase)
  if not ok then
    -- `target` is the Lua error here: surface it, don't swallow it.
    return nil, 'compute failed: ' .. tostring(target)
  end
  if not target then
    return nil, 'cannot read requirements: ' .. tostring(err or 'unknown reason')
  end

  local raised, failed = 0, 0
  for id, v in pairs(target.attributes) do
    local okS, e = pcall(function()
      local stat = types.Actor.stats.attributes[id](actor)
      if v > (stat.base or 0) then stat.base = v raised = raised + 1 end
    end)
    if not okS then
      failed = failed + 1
      print('AP: cannot set attribute ' .. tostring(id) .. ': ' .. tostring(e))
    end
  end
  for id, v in pairs(target.skills) do
    local okS, e = pcall(function()
      local stat = types.NPC.stats.skills[id](actor)
      if v > (stat.base or 0) then stat.base = v raised = raised + 1 end
    end)
    if not okS then
      failed = failed + 1
      print('AP: cannot set skill ' .. tostring(id) .. ': ' .. tostring(e))
    end
  end
  if failed > 0 then
    return nil, failed .. ' stat(s) could not be set (see log)'
  end
  return raised
end

return M
