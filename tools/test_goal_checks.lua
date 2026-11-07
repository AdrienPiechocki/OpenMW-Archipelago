-- Test of the goal quest check filter.
--   luajit tools/test_goal_checks.lua   (from the repository root)
package.path = 'mod/?.lua;' .. package.path
local gc = require('scripts.ap.goal_checks')

local failures = 0
local function check(name, actual, expected)
  if actual ~= expected then
    failures = failures + 1
    print(('FAIL %s: got %s, expected %s'):format(name, tostring(actual), tostring(expected)))
  else
    print(('ok   %s'):format(name))
  end
end

local goals = { 'main_quest', 'hlaalu', 'daedric_quests' }

check('misc always allowed (off)', gc.allowed('misc', 0, goals), true)
check('misc allowed without goals', gc.allowed('misc', 0, nil), true)
check('nil group = misc', gc.allowed(nil, 0, nil), true)

check('main allowed (on, any mode > 0)', gc.allowed('main', 1, goals), true)
check('main allowed (full)', gc.allowed('main', 2, goals), true)
check('main refused when off', gc.allowed('main', 0, goals), false)
check('main refused without option (old seed)', gc.allowed('main', nil, goals), false)
check('main refused while goals unknown', gc.allowed('main', 1, nil), false)

check('chosen house allowed', gc.allowed('hlaalu', 1, goals), true)
check('unchosen house refused', gc.allowed('redoran', 1, goals), false)
check('daedric maps to daedric_quests', gc.allowed('daedric', 2, goals), true)
check('daedric refused if goal not chosen', gc.allowed('daedric', 2, { 'main_quest' }), false)
check('non-goal group refused', gc.allowed('vampire', 2, goals), false)
check('blades refused', gc.allowed('blades', 2, goals), false)

if failures > 0 then
  print(('%d failure(s)'):format(failures))
  os.exit(1)
end
print('all goal checks tests passed')
