-- Regression test for the Census Office / Caius package exemption.
--
-- Run from the repository root:
--   luajit tools/test_census_package.lua
--
-- Vanilla's CharGenDoorExitCaptain script refuses to open the Census Office
-- exit door unless bk_a1_1_caiuspackage is in the player's inventory. The mod
-- suppresses quest items until their AP item is received, so it must keep
-- this specific record while the player is still inside the Census Office.
--
-- The old code checked a hardcoded AP id (7701119) instead of the actual
-- package item id (7702077), so the exemption never applied and the package
-- was removed as soon as Sellus Gravius gave it.
package.path = 'mod/?.lua;' .. package.path

local items = require('scripts.ap.items')

local failures = 0
local function check(name, actual, expected)
  if actual ~= expected then
    failures = failures + 1
    print(('FAIL %s: got %s, expected %s'):format(name, tostring(actual), tostring(expected)))
  else
    print(('ok   %s'):format(name))
  end
end

-- Locate the package in the main quest suppression table, exactly like
-- global.lua does when applying the player's goals.
local suppress = items.suppressFor({ 'main_quest' })
local packageId, packageRecords
for apId, records in pairs(suppress) do
  for _, recordId in ipairs(records) do
    if recordId == 'bk_a1_1_caiuspackage' then
      packageId, packageRecords = apId, records
    end
  end
end

check('package is suppressed for main_quest', packageId ~= nil, true)
check('package record id', items.CENSUS_PACKAGE, 'bk_a1_1_caiuspackage')

-- The exemption must follow the record, not a hardcoded AP id that can
-- drift from data/quest_items.yaml.
check('keep package inside Census Office', items.keepInCensus(packageRecords, true), true)
check('remove package outside Census Office', items.keepInCensus(packageRecords, false), false)
check('ignore unrelated records', items.keepInCensus({ 'some_other_item' }, true), false)
check('ignore missing records', items.keepInCensus(nil, true), false)

if failures > 0 then
  print(('%d failure(s)'):format(failures))
  os.exit(1)
end
print('all census package tests passed')
