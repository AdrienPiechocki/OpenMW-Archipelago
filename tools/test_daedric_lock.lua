-- Regression test for the Daedric shrine activation lock.
--
-- Run from the repository root:
--   luajit tools/test_daedric_lock.lua
--
-- Vanilla Daedric quests are started by activating an ACTI whose MWScript
-- tests `OnActivate == 1` (DaedraAzura, DaedraBoethiah2, ...). Resetting the
-- journal stage after the fact is too late: the script already spoke, set the
-- journal and enabled its minions in the same frame. The activation must be
-- refused before the standard action runs.
package.path = 'mod/?.lua;' .. package.path

local activationLock = require('scripts.ap.activation_lock')
local ACTIVATORS = require('scripts.ap.quest_lock_activators')

local failures = 0
local function check(name, actual, expected)
  if actual ~= expected then
    failures = failures + 1
    print(('FAIL %s: got %s, expected %s'):format(name, tostring(actual), tostring(expected)))
  else
    print(('ok   %s'):format(name))
  end
end

local function daedricGoal(key) return key == 'daedric_quests' end
local function noGoal() return false end

-- Every vanilla shrine script must map to the matching AP item / journal.
local expectedScripts = {
  { script = 'DaedraAzura',      id = 7701400, quest = 'da_azura' },
  { script = 'DaedraBoethiah',   id = 7701401, quest = 'da_boethiah' },
  { script = 'DaedraBoethiah2',  id = 7701401, quest = 'da_boethiah' },
  { script = 'DaedraMalacath',   id = 7701402, quest = 'da_malacath' },
  { script = 'DaedraMehrunes',   id = 7701403, quest = 'da_mehrunes' },
  { script = 'DaedraMephala',    id = 7701404, quest = 'da_mephala' },
  { script = 'DaedraMolagBal',   id = 7701405, quest = 'da_molagbal' },
  { script = 'DaedraSheogorath', id = 7701406, quest = 'da_sheogorath' },
}

for _, e in ipairs(expectedScripts) do
  local entry = activationLock.blockedLock(
    ACTIVATORS,
    { id = 'ignored_record', mwscript = e.script },
    {},
    daedricGoal
  )
  check(e.script .. ' maps to item id', entry and entry.id, e.id)
  check(e.script .. ' maps to journal', entry and entry.quest, e.quest)
end

-- Without the AP item the activation is refused...
local azura = { id = 'active_dae_azura', mwscript = 'DaedraAzura' }
check('locked before item', activationLock.blockedLock(ACTIVATORS, azura, {}, daedricGoal) ~= nil, true)

-- ...and allowed as soon as the item is owned.
check('allowed after item', activationLock.blockedLock(ACTIVATORS, azura, { [7701400] = true }, daedricGoal), nil)

-- Locks only apply when the daedric goal is selected.
check('allowed without daedric goal', activationLock.blockedLock(ACTIVATORS, azura, {}, noGoal), nil)

-- Fallback on the record id if a mod renamed the script.
local renamed = { id = 'active_dae_mephala', mwscript = 'SomeRenamedScript' }
local byRecord = activationLock.blockedLock(ACTIVATORS, renamed, {}, daedricGoal)
check('record id fallback', byRecord and byRecord.id, 7701404)

-- Unrelated activators are never blocked.
check('unknown activator', activationLock.blockedLock(
  ACTIVATORS, { id = 'active_sign_balmora_02', mwscript = 'signScript' }, {}, daedricGoal), nil)
check('missing record', activationLock.blockedLock(ACTIVATORS, nil, {}, daedricGoal), nil)

-- Every activator record used by the base game must be covered.
local expectedRecords = {
  { record = 'active_dae_azura',              id = 7701400 },
  { record = 'Ex_DAE_Boethiah_fixed',         id = 7701401 },
  { record = 'active_dae_boethiah',           id = 7701401 },
  { record = 'active_dae_boethiah_ruin',      id = 7701401 },
  { record = 'active_DAE_B_Bo_Head',          id = 7701401 },
  { record = 'active_dae_malacath',           id = 7701402 },
  { record = 'active_dae_mehrunes',           id = 7701403 },
  { record = 'active_dae_mephala',            id = 7701404 },
  { record = 'active_velothi_altar_Mephala',  id = 7701404 },
  { record = 'active_dae_molagbal',           id = 7701405 },
  { record = 'active_dae_sheogorath',         id = 7701406 },
}

for _, e in ipairs(expectedRecords) do
  local entry = activationLock.blockedLock(ACTIVATORS, { id = e.record }, {}, daedricGoal)
  check(e.record .. ' maps to item id', entry and entry.id, e.id)
end

if failures > 0 then
  print(('%d failure(s)'):format(failures))
  os.exit(1)
end
print('all daedric lock tests passed')
