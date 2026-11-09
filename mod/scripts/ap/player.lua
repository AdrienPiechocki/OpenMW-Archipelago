-- Player mod: check detection (Miscellaneous quests, death)
-- and the game goal.
local core  = require('openmw.core')
local self  = require('openmw.self')
local types = require('openmw.types')
local ui    = require('openmw.ui')
local ap    = require('scripts.ap.io')
local json  = require('scripts.ap.json')
local config = require('scripts.ap.config')
local levelUp = require('scripts.ap.level_up')
local startBoost = require('scripts.ap.start_boost')
local factionReq = require('scripts.ap.faction_requirements')
-- Expansion quest groups: <expansion>_<category> (tribunal_main, tribunal_side,
-- bloodmoon_main, bloodmoon_side). Checks only if the group is enabled in the
-- seed (slot_data.options.expansion_groups). Never gating. The Bloodmoon
-- East Empire Company quests (group east_empire_company) follow the `faction`
-- option like the other faction goals.
local EXPANSION_GROUPS = {
  tribunal_main = true, tribunal_side = true,
  bloodmoon_main = true, bloodmoon_side = true,
}
local goalChecks = {
  GROUP_GOALS = { main = 'main_quest', daedric = 'daedric_quests' },
  goalOfGroup = function(group)
    local m = { main = 'main_quest', daedric = 'daedric_quests' }
    return m[group] or group
  end,
  EXPANSION_GROUPS = EXPANSION_GROUPS,
  allowed = function(group, goalList, expansionGroups)
    if group == nil or group == 'misc' then return true end
    -- Tamriel Rebuilt groups (tr_main, tr_side, tr_daedric, tr_<faction>) are enabled by the
    -- server the same way (slot_data.options.expansion_groups).
    if EXPANSION_GROUPS[group] or group:sub(1, 3) == 'tr_' then
      if type(expansionGroups) ~= 'table' then return false end
      for _, k in ipairs(expansionGroups) do
        if k == group then return true end
      end
      return false
    end
    if type(goalList) ~= 'table' then return false end
    local m = { main = 'main_quest', daedric = 'daedric_quests' }
    local key = m[group] or group
    for _, k in ipairs(goalList) do
      if k == key then return true end
    end
    return false
  end,
}
local notify = require('scripts.ap.notify')
local storage = require('openmw.storage')

-- Tables generated from data/*.yaml (tools/gen_lua.py)
local QUEST_COMPLETE_LOOKUP = require('scripts.ap.quest_completions') -- ['quest'] = {stage, {fails}, {ids}, group, {alternative ending stages}}
local EXCLUSIVE = require('scripts.ap.quest_exclusive') -- ['quest'] = { members of its mutually exclusive group (itself included) }
local GOALS = require('scripts.ap.goals')
local REWARDS = require('scripts.ap.quest_rewards') -- list of { item, loc, record, count, quest, stage, group, name }
local LOCKS = require('scripts.ap.quest_locks')   -- goal -> { {id = AP item, quest} }

local sent = {}
local goalSent = false
local startAttributes = nil  -- YAML attribute_<id> bonuses { strength = 5 ... } (non-zero only), received from the server
local startSkills = nil      -- YAML skill_<id> bonuses { longblade = 10 ... } (non-zero only), received from the server
local startBoostDone = false -- attribute / skill bonuses already applied (remembered in the save)
local expansionGroups = nil -- enabled expansion groups ('tribunal_main', 'bloodmoon_side'...), received from the server
local goalList = nil        -- GOALS keys to complete (main quest + house/guild/faction), received from the server
local reachedGoals = {}     -- key -> true, remembered once reached
local ownedIds = {}         -- received AP item ids (relayed by global.lua)
local lockWarned = {}
local reqWarned = {}
local rewardsOn = false     -- quest_rewards option (YAML), received from the server
local rewardBase = {}       -- reward record -> inventory count already accounted for
local rewardSuspect = {}    -- reward record -> true: increase seen, confirmed at the next poll
local dagothDead = false
local wasDead = false
local deathlinkTime = 0
local lastDeathTime = 0
local lastRank = {}

local function lower(s) return tostring(s or ''):lower() end

local function check(id)
  if not id or sent[id] then return end
  -- Only remembered as sent if the line really reached out.jsonl: otherwise
  -- the check would be lost for good (neither resent nor retried by the poll).
  if not ap.send(('{"t":"check","id":%d}'):format(id)) then
    print('AP: check ' .. tostring(id) .. ' could not be written, will retry')
    return
  end
  sent[id] = true
  print('AP check sent: ' .. tostring(id))
end

local function sendGoal()
  if goalSent then return end
  goalSent = true
  ap.send('{"t":"goal"}')
  print('AP: goal sent (' .. table.concat(goalList or {}, ', ') .. ')')
end

-- Set of quests to watch. We index the quests object directly rather than
-- using pairs(): iteration is not guaranteed depending on the OpenMW
-- version (and fails silently).
local allQuests = {}
for q in pairs(QUEST_COMPLETE_LOOKUP) do allQuests[q] = true end
for _, g in pairs(GOALS) do
  for _, e in ipairs(g.quests or {}) do allQuests[e.quest] = true end
end

local function questStage(quests, qkey)
  local ok, quest = pcall(function() return quests[qkey] end)
  if not ok or not quest then return 0 end
  return tonumber(quest.stage) or 0
end

-- A quest is complete (successfully) if its stage reached the completion
-- threshold without being on a failure branch, OR if it is one of its
-- alternative ending stages (info[5], often below the threshold).
local function questComplete(qkey, stage)
  local info = QUEST_COMPLETE_LOOKUP[qkey]
  if not info then return false end
  for _, f in ipairs(info[2] or {}) do
    if tonumber(f) == stage then return false end
  end
  for _, a in ipairs(info[5] or {}) do
    if tonumber(a) == stage then return true end
  end
  local threshold = tonumber(info[1]) or 0
  if threshold <= 0 or stage < threshold then return false end
  return true
end

local function factionRank(fid)
  local ok, r = pcall(function() return types.NPC.getFactionRank(self, fid) end)
  if ok and type(r) == 'number' then return r end
  return 0
end

-- A goal (GOALS key) is reached if ONE of its conditions is met.
-- Once reached, it stays reached (remembered in the save).
local function keyReached(key, quests)
  if reachedGoals[key] then return true end
  local g = GOALS[key]
  if not g then return false end
  local ok = false

  if g.quests then
    for _, e in ipairs(g.quests) do
      if questStage(quests, e.quest) >= e.stage then ok = true end
    end
  end

  if g.faction then
    local r = factionRank(g.faction)
    if r ~= lastRank[g.faction] then
      lastRank[g.faction] = r
      print(('AP: rank %s = %d (goal: %d)'):format(g.faction, r, g.rank or 10))
    end
    -- The goal only counts once the "<faction> Requirements added" item has
    -- been received (progression item of the apworld).
    local reqId = factionReq.ITEM_IDS[key]
    if r >= (g.rank or 10) then
      if not reqId or ownedIds[reqId] then
        ok = true
      elseif not reqWarned[key] then
        reqWarned[key] = true
        print(('AP: %s rank reached but the Requirements item is missing: goal on hold'):format(key))
      end
    end
  end

  if g.group then
    local n, done = 0, 0
    for qkey, info in pairs(QUEST_COMPLETE_LOOKUP) do
      if info[4] == g.group then
        n = n + 1
        if questComplete(qkey, questStage(quests, qkey)) then done = done + 1 end
      end
    end
    if n > 0 and done == n then ok = true end
  end

  if key == 'main_quest' and dagothDead then ok = true end

  if ok then
    reachedGoals[key] = true
    print('AP: goal reached: ' .. key)
  end
  return ok
end

-- All chosen goals are reached (we evaluate them all: rank logs).
local function allGoalsReached(quests)
  if not goalList or #goalList == 0 then return false end
  local all = true
  for _, key in ipairs(goalList) do
    if not keyReached(key, quests) then all = false end
  end
  return all
end

local function goalActive(key)
  if not goalList then return false end
  for _, k in ipairs(goalList) do
    if k == key then return true end
  end
  return false
end

-- Locked quests: as long as the unlocking AP item has not been received, the
-- quest cannot progress (journal reset to zero on every check).
-- Only applies if the matching goal is selected (e.g. Daedric Quests) and,
-- for entries with a `group` (TR daedric princes), if that group is enabled
-- in the seed (tamriel_rebuilt_daedric_quests too).
local function enforceLocks(quests)
  if not goalList then return end
  for goal, list in pairs(LOCKS) do
    if goalActive(goal) then
      for _, lk in ipairs(list) do
        local enabled = not lk.group
          or goalChecks.allowed(lk.group, goalList, expansionGroups)
        if enabled and not ownedIds[lk.id] and questStage(quests, lk.quest) > 0 then
          local ok = pcall(function() quests[lk.quest].stage = 0 end)
          if ok then
            print('AP: locked quest reset to zero: ' .. lk.quest)
          elseif not lockWarned[lk.quest] then
            lockWarned[lk.quest] = true
            print('AP: cannot lock quest ' .. lk.quest .. ' (stage API not writable?)')
          end
        end
      end
    end
  end
end

-- Starting bonuses: applied once, as soon as the tutorial is over.
local function applyStartBoost(quests)
  if startBoostDone or not startAttributes or not startSkills then return end
  if startBoost.isEmpty(startAttributes, startSkills) then
    startBoostDone = true       -- all bonuses at 0 = vanilla: nothing to do
    return
  end
  if questStage(quests, startBoost.TRIGGER_QUEST) < startBoost.TRIGGER_STAGE then return end
  startBoostDone = true
  if startBoost.apply(types, self, startAttributes, startSkills) then
    local total = startBoost.total(startAttributes, startSkills)
    print(('AP: starting bonuses applied (%d points in total)'):format(total))
    pcall(function()
      ui.showMessage(('Archipelago: starting bonuses applied (+%d in total)'):format(total))
    end)
  end
end

-- Quest rewards (unique items, quest_rewards option). When a reward record
-- enters the inventory (count above the baseline) while its quest has reached
-- the stage that gives it, the vanilla copy is removed (global script) and the
-- location check is sent. The copy given by Archipelago itself is not counted
-- (AP_RewardGiven raises the baseline). An increase is only confirmed at the
-- NEXT poll, so that the event of a copy given by Archipelago has the time to
-- arrive. Once the check is sent, the item is no longer watched.
local function inventoryCount(record)
  local ok, n = pcall(function() return types.Actor.inventory(self):countOf(record) end)
  return ok and tonumber(n) or 0
end

local function pollRewards(quests)
  if not rewardsOn then return end
  for _, r in ipairs(REWARDS) do
    if not sent[r.loc] then
      local cnt = inventoryCount(r.record)
      local base = rewardBase[r.record]
      if base == nil then
        rewardBase[r.record] = cnt     -- first observation: baseline
      else
        local delta = cnt - base
        local gated = delta > 0
          and questStage(quests, r.quest) >= (r.stage or 1)
          and goalChecks.allowed(r.group, goalList, expansionGroups)
        if gated then
          if rewardSuspect[r.record] then
            local n = math.min(delta, r.count or 1)
            rewardSuspect[r.record] = nil
            rewardBase[r.record] = cnt - n
            core.sendGlobalEvent('AP_RemoveReward', { record = r.record, count = n })
            check(r.loc)
            print('AP: quest reward randomized: ' .. tostring(r.record) .. ' (' .. tostring(r.quest) .. ')')
            pcall(function()
              ui.showMessage('Archipelago: reward sent (' .. tostring(r.name):gsub('^Reward: ', '') .. ')')
            end)
          else
            rewardSuspect[r.record] = true     -- wait for the next poll
          end
        else
          rewardSuspect[r.record] = nil
          rewardBase[r.record] = cnt           -- sold, dropped, or other source
        end
      end
    end
  end
end

-- Copy of a reward given by Archipelago (global.lua / items.lua): raise the
-- baseline so that it is not taken for the vanilla reward.
local function onRewardGiven(data)
  if type(data) ~= 'table' or not data.record then return end
  local rec = lower(data.record)
  if rewardBase[rec] ~= nil then
    rewardBase[rec] = rewardBase[rec] + (tonumber(data.count) or 1)
  end
  rewardSuspect[rec] = nil
end

local function pollQuests()
  local quests = types.Player.quests(self)
  if not quests then return end
  enforceLocks(quests)
  applyStartBoost(quests)
  pollRewards(quests)
  for qkey in pairs(allQuests) do
    local stage = questStage(quests, qkey)
    if stage > 0 then
      -- Completion check: Miscellaneous quests, and quests of the chosen
      -- goals if the Goal Quest Checks option is enabled.
      local info = QUEST_COMPLETE_LOOKUP[qkey]
      if info and questComplete(qkey, stage)
          and goalChecks.allowed(info[4], goalList, expansionGroups) then
        -- Mutually exclusive quests: completing one member validates the
        -- whole group, so the checks of ALL members are sent (even the
        -- variants whose journal never advances in this playthrough).
        -- check() deduplicates via `sent`, which is persisted in the save.
        local group = EXCLUSIVE[qkey]
        if group then
          for _, q in ipairs(group) do
            local mi = QUEST_COMPLETE_LOOKUP[q]
            if mi and goalChecks.allowed(mi[4], goalList, expansionGroups) then
              for _, cid in ipairs(mi[3] or {}) do check(cid) end
            end
          end
        else
          for _, cid in ipairs(info[3] or {}) do check(cid) end
        end
      end
    end
  end

  if goalList and not goalSent and allGoalsReached(quests) then
    sendGoal()
  end
end

local function deathlinkEnabled()
  local ok, sec = pcall(function() return storage.globalSection('SettingsArchipelago') end)
  if ok and sec then
    local v = sec:get('deathlink')
    if v ~= nil then return v end
  end
  return config.deathlink
end

local function checkDeath()
  local dead = types.Actor.isDead(self)
  if not dead then
    local ok, hp = pcall(function() return types.Actor.stats.dynamic.health(self).current end)
    dead = ok and hp ~= nil and hp <= 0
  end
  if dead and not wasDead then
    local now = core.getRealTime()
    local enabled = deathlinkEnabled()
    print(('AP: death detected (deathlink=%s, %.1fs since last received)'):format(tostring(enabled), now - deathlinkTime))
    if (now - deathlinkTime) > 5 and enabled then
      local place = nil
      pcall(function()
        local c = self.cell
        place = (c.name and c.name ~= '' and c.name) or c.region
      end)
      local sent = ap.send(json.encode({ t = 'death', cause = place and ('died in ' .. tostring(place)) or 'died' }))
      print('AP: death written to out.jsonl: ' .. tostring(sent))
      lastDeathTime = now
    end
  end
  wasDead = dead
end

-- Archipelago item notifications (received / sent): display queue, one
-- message every notify.GAP seconds so they stay readable.
local notifyQueue = {}
local notifyWait = 0

local function notificationsEnabled()
  -- Value written by the options page into connection.cfg (see settings.lua).
  local okF, txt = pcall(function() return ap.readFile('connection.cfg') end)
  if okF and txt then
    local v = txt:match('\n%s*notifications%s*=%s*(%a+)')
    if v then return v:lower() == 'true' end
  end
  local ok, sec = pcall(function() return storage.globalSection('SettingsArchipelago') end)
  if ok and sec then
    local v = sec:get('notifications')
    if v ~= nil then return v end
  end
  return true
end

local function onNotify(data)
  local text = notify.format(data)
  if not text then return end
  print('AP notification: ' .. text)
  if not notificationsEnabled() then return end
  if #notifyQueue >= notify.MAX_QUEUE then return end
  notifyQueue[#notifyQueue + 1] = text
end

local function notifyTick(dt)
  if notifyWait > 0 then notifyWait = notifyWait - dt end
  if notifyWait <= 0 and #notifyQueue > 0 then
    local text = table.remove(notifyQueue, 1)
    pcall(function() ui.showMessage(text) end)
    notifyWait = notify.GAP
  end
end

local timer = 0
local function onUpdate(dt)
  notifyTick(dt)
  local okD, errD = pcall(checkDeath)
  if not okD then print('AP: checkDeath error: ' .. tostring(errD)) end

  timer = timer + dt
  local interval = tonumber(config.poll_interval) or 1.0
  if interval < 0.2 then interval = 0.2 end
  if timer < interval then return end
  timer = 0
  local okP, errP = pcall(pollQuests)
  if not okP then print('AP: pollQuests error: ' .. tostring(errP)) end
end

local function onSave()
  return { sent = sent, goalSent = goalSent, goalList = goalList, expansionGroups = expansionGroups, startAttributes = startAttributes, startSkills = startSkills, startBoostDone = startBoostDone, reachedGoals = reachedGoals, ownedIds = ownedIds }
end

-- Resends every check already obtained (and the goal): idempotent on the
-- bridge side, deduplicated by the server. Called on load, when the config
-- arrives, and on AP_Resync (new bridge session, bridge back, game that was
-- frozen in the background).
local function resendAll()
  local n = 0
  for id in pairs(sent) do
    n = n + 1
    ap.send(('{"t":"check","id":%d}'):format(id))
  end
  print(('AP: %d check(s) resent'):format(n))
  if goalSent then
    ap.send('{"t":"goal"}')
  end
end

-- Diagnostic: journal quests (known to the mod) that still have a check not
-- sent, with the reason. One line per quest, printed again only when it
-- changes. complete=false: stage below the threshold / failure stage;
-- allowed=false: quest group not enabled by the seed (goal / expansion).
local lastDiag = {}
local function diagnose()
  local ok, quests = pcall(function() return types.Player.quests(self) end)
  if not ok or not quests then return end
  local pending = 0
  for qkey in pairs(QUEST_COMPLETE_LOOKUP) do
    local stage = questStage(quests, qkey)
    local info = QUEST_COMPLETE_LOOKUP[qkey]
    if stage > 0 and info then
      local missing = 0
      for _, cid in ipairs(info[3] or {}) do
        if not sent[cid] then missing = missing + 1 end
      end
      if missing > 0 then
        pending = pending + 1
        local line = ('%s stage=%d threshold=%s fail=%s complete=%s allowed=%s group=%s missing=%d'):format(
          qkey, stage, tostring(info[1]), table.concat(info[2] or {}, '/'),
          tostring(questComplete(qkey, stage)),
          tostring(goalChecks.allowed(info[4], goalList, expansionGroups)),
          tostring(info[4]), missing)
        if lastDiag[qkey] ~= line then
          lastDiag[qkey] = line
          print('AP: pending ' .. line)
        end
      end
    end
  end
  print(('AP: diag: %d quest(s) in the journal with a check not sent'):format(pending))
end

local function onResync()
  print('AP: resync, resending checks')
  resendAll()
  pcall(diagnose)
end

local function requestConfig()
  pcall(function() core.sendGlobalEvent('AP_RequestConfig', {}) end)
end

local function onLoad(d)
  if d then
    sent = d.sent or {}
    goalSent = d.goalSent or false
    goalList = d.goalList
    expansionGroups = d.expansionGroups
    startAttributes = d.startAttributes
    startSkills = d.startSkills
    startBoostDone = d.startBoostDone or false
    reachedGoals = d.reachedGoals or {}
    ownedIds = d.ownedIds or {}
  end
  -- resync: resend all already obtained checks (idempotent on the bridge side)
  resendAll()
  requestConfig()
end

local function onInit()
  ap.send(('{"t":"hello","slot":"%s","version":1}'):format(tostring(config.slot or '')))
  requestConfig()
end

local function onDeathLink(data)
  deathlinkTime = core.getRealTime()   -- anti-écho : pas de renvoi de cette mort
  pcall(function()
    local from = (type(data) == 'table' and data.from) and tostring(data.from) or '?'
    local cause = (type(data) == 'table' and data.cause) and tostring(data.cause) or ''
    local msg
    if cause ~= '' then
      msg = 'DeathLink: ' .. cause
      if not msg:find(from, 1, true) then msg = msg .. ' (' .. from .. ')' end
    else
      msg = 'DeathLink: ' .. from .. ' died'
    end
    ui.showMessage(msg)
  end)
  local ok, err = pcall(function()
    types.Actor.stats.dynamic.health(self).current = 0
  end)
  print('AP: DeathLink applied to player: ' .. tostring(ok) .. (ok and '' or (' ' .. tostring(err))))
end

-- Server config (slot_data) relayed by global.lua: data.goals = list of
-- keys (main quest + chosen house / guild / faction). Old format:
-- data.goal = 'main_quest' or 0.
local function onConfig(data)
  if type(data) ~= 'table' then return end

  -- Starting bonuses (attribute_<id> / skill_<id> options). Absent (old
  -- server): unchanged.
  local sa = startBoost.cleanAttributes(data.attributeBonuses)
  local ss = startBoost.cleanSkills(data.skillBonuses)
  if sa and ss then
    if not startBoostDone then
      print(('AP: starting bonuses = %d points'):format(startBoost.total(sa, ss)))
    end
    startAttributes, startSkills = sa, ss
  end

  -- quest_rewards option: absent (old server) = disabled.
  rewardsOn = data.questRewards == true

  -- Enabled expansion groups (tribunal_main_quest, bloodmoon_side_quests...
  -- options). Absent (old server): the previous value is kept.
  if type(data.expansionGroups) == 'table' then
    local exp = {}
    for _, k in ipairs(data.expansionGroups) do exp[#exp + 1] = lower(k) end
    if table.concat(exp, ',') ~= table.concat(expansionGroups or {}, ',') then
      print('AP: expansion groups = ' .. (#exp > 0 and table.concat(exp, ', ') or 'none'))
    end
    expansionGroups = exp
  end

  -- Resync: AP_Config only arrives after the bridge connects. The bridge may
  -- have reset its checks to zero (new seed) while `sent` persists in the
  -- save: we resend everything (idempotent on the bridge side, deduplicated
  -- by the server).
  resendAll()

  local raw = {}
  if type(data.goals) == 'table' then
    for _, k in ipairs(data.goals) do raw[#raw + 1] = lower(k) end
  elseif data.goal ~= nil then
    if type(data.goal) == 'number' then
      if data.goal == 0 then raw[1] = 'main_quest' end
    else
      raw[1] = lower(data.goal)
    end
  end
  local list, seen = {}, {}
  for _, k in ipairs(raw) do
    if GOALS[k] and not seen[k] then
      seen[k] = true
      list[#list + 1] = k
    elseif not GOALS[k] then
      print('AP: unknown goal: ' .. k)
    end
  end
  if #list > 0 then
    local changed = (goalList == nil) or (table.concat(goalList, ',') ~= table.concat(list, ','))
    goalList = list
    if changed then print('AP: goals = ' .. table.concat(list, ', ')) end
  end
end

-- Received AP items (ids), relayed by global.lua: they unlock quests.
local function onOwned(data)
  if type(data) ~= 'table' or type(data.ids) ~= 'table' then return end
  for _, id in ipairs(data.ids) do ownedIds[tonumber(id)] = true end
end

-- "+10 levels" item: we add vanilla level-up progress to the player
-- (self). The setter is only allowed in a local script, hence the relay
-- through global.lua. The player then sleeps to choose their attributes.
local function onLevelUp(data)
  local levels = levelUp.LEVELS
  if type(data) == 'table' and tonumber(data.levels) then
    levels = tonumber(data.levels)
  end
  pcall(function()
    local total = tonumber(core.getGMST('iLevelUpTotal')) or levelUp.DEFAULT_LEVEL_UP_TOTAL
    local stat = types.Actor.stats.level(self)
    stat.progress = levelUp.newProgress(stat.progress, levels, total)
  end)
  pcall(function()
    ui.showMessage(('Archipelago item: +%d levels. Sleep to choose your attributes.'):format(levels))
  end)
end

-- "<faction> Requirements added" item (relayed by global.lua: setters only
-- work on self): attributes / skills raised to the faction's max requirements.
local function onFactionRequirements(data)
  if type(data) ~= 'table' or not data.faction then return end
  local raised, err = factionReq.apply(core, types, self, data.faction)
  local label = tostring(data.faction)
  pcall(function()
    local rec = core.factions.records[tostring(data.faction):lower()]
    if rec and rec.name then label = rec.name end
  end)
  if raised then
    print(('AP: requirements of %s applied (%d stat(s) raised)'):format(tostring(data.faction), raised))
    pcall(function()
      ui.showMessage(('Archipelago item: %s requirements added'):format(label))
    end)
  else
    print('AP: faction requirements failed: ' .. tostring(err))
  end
end

-- Trap damage (relayed by global.lua): `fraction` of max health (items.lua sends 0.9),
-- or a flat `amount`. Never kills: leaves at least 1 HP.
local function onDamage(data)
  local fraction = type(data) == 'table' and tonumber(data.fraction) or nil
  local amount = type(data) == 'table' and tonumber(data.amount) or nil
  pcall(function()
    local health = types.Actor.stats.dynamic.health(self)
    local dmg
    if fraction then
      dmg = ((health.base or 0) + (health.modifier or 0)) * fraction
    else
      dmg = amount or 20
    end
    health.current = math.max(1, (health.current or 0) - dmg)
  end)
end

-- Daedric shrine activation blocked by global.lua (missing AP item).
local function onLockedActivation(data)
  local name = 'daedric shrine'
  if type(data) == 'table' and data.name ~= nil then
    name = tostring(data.name)
  end
  pcall(function()
    ui.showMessage('Shrine locked: ' .. name .. ' (Archipelago item required)')
  end)
end

-- Death of Dagoth Ur (relayed by actor.lua -> global.lua).
local function onDagothDead()
  dagothDead = true
end

return {
  engineHandlers = {
    onInit = onInit,
    onLoad = onLoad,
    onSave = onSave,
    onUpdate = onUpdate,
  },
  eventHandlers = {
    AP_DeathLink = onDeathLink,
    AP_Config = onConfig,
    AP_Resync = onResync,
    AP_RewardGiven = onRewardGiven,
    AP_Owned = onOwned,
    AP_LevelUp = onLevelUp,
    AP_FactionRequirements = onFactionRequirements,
    AP_Damage = onDamage,
    AP_LockedActivation = onLockedActivation,
    AP_Notify = onNotify,
    AP_DagothDead = onDagothDead,
  },
}
