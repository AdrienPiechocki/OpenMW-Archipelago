-- Offline test of the mutually exclusive quest groups (branching quests).
-- Loads the REAL player.lua with mocked openmw.* modules.
-- Usage (from the mod folder, any Lua 5.3/5.4):  lua tests/test_exclusive.lua
package.path = './?.lua;' .. package.path
local realPrint = print
print = function() end   -- silence the mod logs
local function out(...) io.write(string.format(...), '\n') end

local sentLines, Q = {}, {}
local function mock()
  package.preload['openmw.core'] = function() return { getRealTime = function() return 0 end, getGMST = function() return 10 end, sendGlobalEvent = function() end } end
  package.preload['openmw.self'] = function() return { cell = { name = 'Test' }, recordId = 'player' } end
  package.preload['openmw.ui'] = function() return { showMessage = function() end } end
  package.preload['openmw.storage'] = function() return { globalSection = function() return { get = function() return nil end, set = function() end } end } end
  package.preload['openmw.types'] = function()
    return {
      Player = { quests = function() return Q end },
      Actor = { isDead = function() return false end, stats = { dynamic = { health = function() return { current = 100 } end }, level = function() return {} end } },
      NPC = { getFactionRank = function() return 0 end, stats = { skills = {} } },
    }
  end
  package.preload['scripts.ap.io'] = function()
    return { send = function(line) sentLines[#sentLines + 1] = line; return true end, poll = function() return {} end, dir = function() return '/tmp/' end }
  end
end
mock()

local LOOKUP = dofile('scripts/ap/quest_completions.lua')
local EXCL   = dofile('scripts/ap/quest_exclusive.lua')
local GOALS  = dofile('scripts/ap/goals.lua')
local LOCKS  = dofile('scripts/ap/quest_locks.lua')

local ALL_GOALS, EXP = {}, { 'tribunal_main', 'tribunal_side', 'bloodmoon_main', 'bloodmoon_side' }
for k in pairs(GOALS) do ALL_GOALS[#ALL_GOALS + 1] = k end

local function completionStage(q)
  local info = LOOKUP[q]
  if not info then return nil end
  local th = tonumber(info[1]) or 0
  local fails = {}
  for _, f in ipairs(info[2] or {}) do fails[tonumber(f)] = true end
  if th > 0 and not fails[th] then return th end
  for _, a in ipairs(info[5] or {}) do return tonumber(a) end
  return nil
end

local function run(goals, stages)
  sentLines, Q = {}, {}
  for q, st in pairs(stages) do Q[q] = { stage = st } end
  local h = dofile('scripts/ap/player.lua')
  h.eventHandlers.AP_Config({ goals = goals, expansionGroups = EXP })
  local ids = {}
  for _, list in pairs(LOCKS) do for _, lk in ipairs(list) do ids[#ids + 1] = lk.id end end
  h.eventHandlers.AP_Owned({ ids = ids })
  sentLines = {}                      -- ignore the resync
  h.engineHandlers.onUpdate(2.0)
  h.engineHandlers.onUpdate(2.0)
  local ids2, goal = {}, false
  for _, l in ipairs(sentLines) do
    local id = l:match('"check","id":(%d+)')
    if id then ids2[tonumber(id)] = true end
    if l:find('"goal"', 1, true) then goal = true end
  end
  return ids2, goal
end

local function groupActive(group)
  if group == nil or group == 'misc' then return true end
  for _, e in ipairs(EXP) do if e == group then return true end end
  if group == 'main' then return GOALS.main_quest ~= nil end
  if group == 'daedric' then return GOALS.daedric_quests ~= nil end
  return GOALS[group] ~= nil
end
local skipped = {}
local failures, groups, tested = 0, {}, 0
local seen = {}
for q, members in pairs(EXCL) do
  local key = table.concat(members, ',')
  if not seen[key] then seen[key] = true; groups[#groups + 1] = members end
end
table.sort(groups, function(a, b) return a[1] < b[1] end)

out('== %d exclusive groups ==', #groups)
for _, members in ipairs(groups) do
  -- expected = all ids of all members
  local expected, problems = {}, {}
  for _, m in ipairs(members) do
    local info = LOOKUP[m]
    if not info then problems[#problems + 1] = m .. ' missing from quest_completions'
    elseif not info[3] or #info[3] == 0 then problems[#problems + 1] = m .. ' has no check id'
    else for _, id in ipairs(info[3]) do expected[id] = m end end
    local g = EXCL[m]
    if not g or table.concat(g, ',') ~= table.concat(members, ',') then problems[#problems + 1] = m .. ' not symmetric' end
  end
  for _, p in ipairs(problems) do out('  [DATA] %s: %s', members[1], p); failures = failures + 1 end

  local active = LOOKUP[members[1]] and groupActive(LOOKUP[members[1]][4])
  if LOOKUP[members[1]] and not active then skipped[#skipped + 1] = members[1] .. ' (' .. tostring(LOOKUP[members[1]][4]) .. ')' end
  for _, trigger in ipairs(members) do
    local st = completionStage(trigger)
    if st and LOOKUP[trigger] and active then
      tested = tested + 1
      local got = run(ALL_GOALS, { [trigger] = st })
      local missing = {}
      for id, who in pairs(expected) do if not got[id] then missing[#missing + 1] = ('%d(%s)'):format(id, who) end end
      if #missing > 0 then
        failures = failures + 1
        table.sort(missing)
        out('  [FAIL] completing %s -> missing checks: %s', trigger, table.concat(missing, ' '))
      end
    end
  end
end
out('== %d scenarios tested, %d inactive groups skipped, %d failures ==', tested, #skipped, failures)
for _, k in ipairs(skipped) do out('  [SKIP] inactive group (no matching goal in the mod): %s', k) end

-- Goal "group" (e.g. daedric_quests): is it reachable when only ONE branch of
-- each exclusive group is completed?
out('== goal reachability with one branch per exclusive group ==')
for key, g in pairs(GOALS) do
  if g.group then
    local stages, n = {}, 0
    local doneGroup = {}
    for q, info in pairs(LOOKUP) do
      if info[4] == g.group then
        local ex = EXCL[q]
        local gk = ex and table.concat(ex, ',') or q
        if not doneGroup[gk] then
          doneGroup[gk] = true
          stages[q] = completionStage(q); n = n + 1
        end
      end
    end
    local _, goal = run({ key }, stages)
    out('  goal %s: %d quests completed (1 branch / group) -> goal sent: %s', key, n, tostring(goal))
    if not goal then failures = failures + 1 end
  end
end
os.exit(failures == 0 and 0 or 1)
