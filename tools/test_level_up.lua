-- Regression test for the Archipelago "+10 levels" item.
--
-- Run from the repository root:
--   luajit tools/test_level_up.lua
--
-- Receiving the item must add real level-up progress (not just the level
-- number), so the player gets the vanilla level-up dialog with attributes
-- and health when they sleep.
package.path = 'mod/?.lua;' .. package.path

local levelUp = require('scripts.ap.level_up')

local failures = 0
local function check(name, actual, expected)
  if actual ~= expected then
    failures = failures + 1
    print(('FAIL %s: got %s, expected %s'):format(name, tostring(actual), tostring(expected)))
  else
    print(('ok   %s'):format(name))
  end
end

-- Ten level-ups need ten times the GMST threshold (10 by default).
check('ten levels at total 10', levelUp.newProgress(0, 10, 10), 100)
check('existing progress is kept', levelUp.newProgress(3, 10, 10), 103)
check('missing progress starts at zero', levelUp.newProgress(nil, 10, 10), 100)
check('missing total uses 10', levelUp.newProgress(0, 10, nil), 100)
check('invalid total uses 10', levelUp.newProgress(0, 10, 0), 100)
check('negative levels are ignored', levelUp.newProgress(0, -10, 10), 0)
check('negative progress is clamped', levelUp.newProgress(-4, 10, 10), 100)

-- The item must not be confused with a skill or quest item.
check('level item id', levelUp.ITEM_ID, 7703000)
check('levels per item', levelUp.LEVELS, 10)

if failures > 0 then
  print(('%d failure(s)'):format(failures))
  os.exit(1)
end
print('all level up tests passed')
