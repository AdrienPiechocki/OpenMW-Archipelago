-- Mod joueur : detection des checks (quetes Miscellaneous, mort)
-- et de l'objectif de la partie (goal).
local core  = require('openmw.core')
local self  = require('openmw.self')
local types = require('openmw.types')
local ui    = require('openmw.ui')
local ap    = require('scripts.ap.io')
local json  = require('scripts.ap.json')
local config = require('scripts.ap.config')
local levelUp = require('scripts.ap.level_up')
local goalChecks = require('scripts.ap.goal_checks')
local notify = require('scripts.ap.notify')
local storage = require('openmw.storage')

-- Tables generees depuis data/*.yaml (tools/gen_lua.py)
local QUEST_COMPLETE_LOOKUP = require('scripts.ap.quest_completions') -- ['quest'] = {stage, {fails}, {ids}, groupe}
local GOALS = require('scripts.ap.goals')
local LOCKS = require('scripts.ap.quest_locks')   -- objectif -> { {id = item AP, quest} }

local sent = {}
local goalSent = false
local goalList = nil        -- cles de GOALS a accomplir (quete principale + maison/guilde/faction), recues du serveur
local reachedGoals = {}     -- cle -> true, memorise une fois accompli
local ownedIds = {}         -- ids d'items AP recus (relayes par global.lua)
local lockWarned = {}
local dagothDead = false
local wasDead = false
local deathlinkTime = 0
local lastDeathTime = 0
local lastRank = {}

local function lower(s) return tostring(s or ''):lower() end

local function check(id)
  if not id or sent[id] then return end
  sent[id] = true
  ap.send(('{"t":"check","id":%d}'):format(id))
  print('AP check sent: ' .. tostring(id))
end

local function sendGoal()
  if goalSent then return end
  goalSent = true
  ap.send('{"t":"goal"}')
  print('AP: goal envoye (' .. table.concat(goalList or {}, ', ') .. ')')
end

-- Ensemble des quetes a surveiller. On indexe directement l'objet quests
-- plutot que d'utiliser pairs() : l'iteration n'est pas garantie selon la
-- version d'OpenMW (et echoue silencieusement).
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

-- Une quete est terminee (avec succes) si son stage a atteint le seuil de
-- completion sans etre sur une branche d'echec.
local function questComplete(qkey, stage)
  local info = QUEST_COMPLETE_LOOKUP[qkey]
  if not info then return false end
  local threshold = tonumber(info[1]) or 0
  if threshold <= 0 or stage < threshold then return false end
  for _, f in ipairs(info[2] or {}) do
    if tonumber(f) == stage then return false end
  end
  return true
end

local function factionRank(fid)
  local ok, r = pcall(function() return types.NPC.getFactionRank(self, fid) end)
  if ok and type(r) == 'number' then return r end
  return 0
end

-- Un objectif (cle de GOALS) est accompli si UNE de ses conditions est remplie.
-- Une fois accompli, il le reste (memorise dans la sauvegarde).
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
      print(('AP: rang %s = %d (objectif : %d)'):format(g.faction, r, g.rank or 10))
    end
    if r >= (g.rank or 10) then ok = true end
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
    print('AP: objectif accompli : ' .. key)
  end
  return ok
end

-- Tous les objectifs choisis sont accomplis (on les evalue tous : logs de rang).
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

-- Quetes verrouillees : tant que l'item AP de deverrouillage n'est pas recu, la
-- quete ne peut pas progresser (journal remis a zero a chaque verification).
-- Ne s'applique que si l'objectif correspondant est choisi (ex. Daedric Quests).
local function enforceLocks(quests)
  if not goalList then return end
  for goal, list in pairs(LOCKS) do
    if goalActive(goal) then
      for _, lk in ipairs(list) do
        if not ownedIds[lk.id] and questStage(quests, lk.quest) > 0 then
          local ok = pcall(function() quests[lk.quest].stage = 0 end)
          if ok then
            print('AP: quete verrouillee remise a zero : ' .. lk.quest)
          elseif not lockWarned[lk.quest] then
            lockWarned[lk.quest] = true
            print('AP: impossible de verrouiller la quete ' .. lk.quest .. ' (API stage non modifiable ?)')
          end
        end
      end
    end
  end
end

local function pollQuests()
  local quests = types.Player.quests(self)
  if not quests then return end
  enforceLocks(quests)
  for qkey in pairs(allQuests) do
    local stage = questStage(quests, qkey)
    if stage > 0 then
      -- Check de completion : quetes Miscellaneous, et quetes des objectifs
      -- choisis si l'option Goal Quest Checks est active.
      local info = QUEST_COMPLETE_LOOKUP[qkey]
      if info and questComplete(qkey, stage)
          and goalChecks.allowed(info[4], goalList) then
        for _, cid in ipairs(info[3] or {}) do check(cid) end
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
  if dead and not wasDead then
    local now = core.getRealTime()
    if (now - deathlinkTime) > 5 and deathlinkEnabled() then
      ap.send('{"t":"death","cause":"player"}')
      lastDeathTime = now
    end
  end
  wasDead = dead
end

-- Notifications d'items Archipelago (recus / envoyes) : file d'affichage, un
-- message toutes les notify.GAP secondes pour qu'ils restent lisibles.
local notifyQueue = {}
local notifyWait = 0

local function notificationsEnabled()
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
  timer = timer + dt
  local interval = tonumber(config.poll_interval) or 1.0
  if interval < 0.2 then interval = 0.2 end
  if timer < interval then
    return
  end
  timer = 0
  pollQuests()
  checkDeath()
end

local function onSave()
  return { sent = sent, goalSent = goalSent, goalList = goalList, reachedGoals = reachedGoals, ownedIds = ownedIds }
end

local function requestConfig()
  pcall(function() core.sendGlobalEvent('AP_RequestConfig', {}) end)
end

local function onLoad(d)
  if d then
    sent = d.sent or {}
    goalSent = d.goalSent or false
    goalList = d.goalList
    reachedGoals = d.reachedGoals or {}
    ownedIds = d.ownedIds or {}
  end
  -- resync : renvoyer tous les checks deja obtenus (idempotent cote bridge)
  for id in pairs(sent) do
    ap.send(('{"t":"check","id":%d}'):format(id))
  end
  if goalSent then
    ap.send('{"t":"goal"}')
  end
  requestConfig()
end

local function onInit()
  ap.send(('{"t":"hello","slot":"%s","version":1}'):format(tostring(config.slot or '')))
  requestConfig()
end

local function onDeathLink()
  deathlinkTime = core.getRealTime()
end

-- Config du serveur (slot_data) relayee par global.lua : data.goals = liste de
-- cles (quete principale + maison / guilde / faction choisies). Ancien format :
-- data.goal = 'main_quest' ou 0.
local function onConfig(data)
  if type(data) ~= 'table' then return end

  -- Resync : AP_Config n'arrive qu'apres la connexion du bridge. Le bridge a pu
  -- remettre ses checks a zero (nouvelle seed) alors que `sent` persiste dans
  -- la save : on renvoie tout (idempotent cote bridge, dedoublonne par le serveur).
  for id in pairs(sent) do
    ap.send(('{"t":"check","id":%d}'):format(id))
  end
  if goalSent then
    ap.send('{"t":"goal"}')
  end


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
      print('AP: objectif inconnu : ' .. k)
    end
  end
  if #list > 0 then
    local changed = (goalList == nil) or (table.concat(goalList, ',') ~= table.concat(list, ','))
    goalList = list
    if changed then print('AP: objectifs = ' .. table.concat(list, ', ')) end
  end
end

-- Items AP recus (ids), relayes par global.lua : deverrouillent les quetes.
local function onOwned(data)
  if type(data) ~= 'table' or type(data.ids) ~= 'table' then return end
  for _, id in ipairs(data.ids) do ownedIds[tonumber(id)] = true end
end

-- Item "+10 niveaux" : on ajoute la progression de niveau vanilla sur le
-- joueur (self). Le setter n'est autorise que dans un script local, d'ou le
-- relais par global.lua. Le joueur dort ensuite pour choisir ses attributs.
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
    ui.showMessage(('Item Archipelago : +%d niveaux. Dormez pour choisir vos attributs.'):format(levels))
  end)
end

-- Activation d'un sanctuaire daedrique bloquee par global.lua (item AP manquant).
local function onLockedActivation(data)
  local name = 'sanctuaire daedrique'
  if type(data) == 'table' and data.name ~= nil then
    name = tostring(data.name)
  end
  pcall(function()
    ui.showMessage('Sanctuaire verrouillé : ' .. name .. ' (item Archipelago requis)')
  end)
end

-- Mort de Dagoth Ur (relayee par actor.lua -> global.lua).
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
    AP_Owned = onOwned,
    AP_LevelUp = onLevelUp,
    AP_LockedActivation = onLockedActivation,
    AP_Notify = onNotify,
    AP_DagothDead = onDagothDead,
  },
}
