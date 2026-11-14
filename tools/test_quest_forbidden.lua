-- Offline test of the forbidden quests ("A Cure for Vampirism" vs the vampire clan goals).
-- Loads the REAL player.lua with mocked openmw.* modules.
-- Usage (from the mod folder, any Lua 5.3/5.4):  lua ../tools/test_quest_forbidden.lua
package.path = './?.lua;' .. package.path
local realPrint = print
print = function() end   -- silence the mod logs
local function out(...) io.write(string.format(...), '\n') end

local sentLines, Q, messages = {}, {}, {}
package.preload['openmw.core'] = function() return { getRealTime = function() return 0 end, getGMST = function() return 10 end, sendGlobalEvent = function() end } end
package.preload['openmw.self'] = function() return { cell = { name = 'Test' }, recordId = 'player' } end
package.preload['openmw.ui'] = function() return { showMessage = function(m) messages[#messages + 1] = m end } end
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

local FORB   = dofile('scripts/ap/quest_forbidden.lua')
local CURE   = 'ms_vampirecure'
local CURE_STAGE = 50   -- final stage; the quest is non_quest, no check

local failures = 0
local function check(name, got, want)
  if got ~= want then failures = failures + 1; out('FAIL %s: got %s, want %s', name, tostring(got), tostring(want))
  else out('ok   %s', name) end
end

local function run(goals, stage)
  sentLines, messages = {}, {}
  Q = { [CURE] = { stage = stage } }
  local h = dofile('scripts/ap/player.lua')
  h.eventHandlers.AP_Config({ goals = goals, expansionGroups = { 'vampire', 'vampire_berne' } })
  sentLines = {}
  h.engineHandlers.onUpdate(2.0)
  h.engineHandlers.onUpdate(2.0)
  return Q[CURE].stage, #messages
end

check('entry exists', FORB.QUESTS[1].quest, CURE)
for _, goal in ipairs({ 'vampire_aundae', 'vampire_berne', 'vampire_quarra', 'vampire_baluath', 'vampire_orlukh' }) do
  local st, msgs = run({ 'main_quest', goal }, 10)
  check(goal .. ': started cure reset to 0', st, 0)
  check(goal .. ': player warned once', msgs, 1)
  st = run({ goal }, CURE_STAGE)
  check(goal .. ': finished cure reset to 0', st, 0)
end
local st, msgs = run({ 'main_quest' }, 10)
check('no clan goal: cure untouched', st, 10)
check('no clan goal: no warning', msgs, 0)
st = run({ 'main_quest', 'daedric_quests' }, 10)
check('other goals: cure untouched', st, 10)

out(failures == 0 and 'all forbidden-quest tests passed' or (failures .. ' FAILED'))
os.exit(failures == 0 and 0 or 1)
