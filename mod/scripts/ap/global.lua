-- Script global : reception des items, lancement du bridge, application des
-- effets et suppression des copies vanilla des objets cles.
local core  = require('openmw.core')
local world = require('openmw.world')
local types = require('openmw.types')
local storage = require('openmw.storage')
local I     = require('openmw.interfaces')
local ap    = require('scripts.ap.io')
local json  = require('scripts.ap.json')
local items = require('scripts.ap.items')
local activationLock = require('scripts.ap.activation_lock')
local ACTIVATORS = require('scripts.ap.quest_lock_activators')
local config = require('scripts.ap.config')
local liveness = require('scripts.ap.liveness')
local notify = require('scripts.ap.notify')

local SETTINGS_KEY = 'SettingsArchipelago'
local function setting(key, fallback)
  local ok, sec = pcall(function() return storage.globalSection(SETTINGS_KEY) end)
  if ok and sec then
    local v = sec:get(key)
    if v ~= nil then return v end
  end
  return fallback
end

-- Enregistrement du groupe de parametres dans le stockage global (pour que
-- le script global puisse lire les valeurs au demarrage).
local regOk, regErr = pcall(function()
  if not I.Settings then error('I.Settings is nil') end
  if not I.Settings.registerGroup then error('registerGroup missing') end
  I.Settings.registerGroup {
    key = SETTINGS_KEY,
    page = 'Archipelago',
    l10n = 'Archipelago',
    name = 'groupName',
    description = '',
    permanentStorage = true,
    order = 0,
    settings = {
      { key = 'host', renderer = 'textLine', name = 'hostName', description = 'hostDesc', default = config.host or '127.0.0.1' },
      { key = 'port', renderer = 'number', name = 'portName', description = 'portDesc', default = config.port or 38281, argument = { integer = true, min = 1, max = 65535 } },
      { key = 'slot', renderer = 'textLine', name = 'slotName', description = 'slotDesc', default = config.slot or 'TestMW' },
      { key = 'password', renderer = 'textLine', name = 'passwordName', description = 'passwordDesc', default = config.password or '' },
      { key = 'deathlink', renderer = 'checkbox', name = 'deathlinkName', description = 'deathlinkDesc', default = config.deathlink ~= false },
      { key = 'notifications', renderer = 'checkbox', name = 'notificationsName', description = 'notificationsDesc', default = true },
    }
  }
end)
if not regOk then
  -- silencieux en production ; decommenter pour debug
end

-- Index du dernier item applique. -1 = aucun item (l'index Archipelago
-- commence a 0).
local lastIdx = -1
local owned = {}          -- item AP id -> true
local pending = {}        -- messages "item" en attente d'un joueur charge
local lastNotify = 0      -- dernier id de notification relayee au joueur
local pendingNotify = {}  -- notifications en attente d'un joueur charge
local serverOptions = {}  -- options envoyees dans slot_data
local timer = 0
-- (transportTimer supprime)
local bridgeStarted = false
local bridgeStartedAt = 0
local lastBridgeCheck = 0
local dbgCounter = 0
local lastHeartbeat = 0

local function getPlayer()
  local players = world.players
  if players and #players > 0 then return players[1] end
  return nil
end

local function shq(s) return ap.shquote(s) end

local function readFile(path)
  local f = io.open(path, 'r')
  if not f then return nil end
  local d = f:read('*a')
  f:close()
  return d
end

-- Le bridge ecrit un timestamp Unix dans bridge.heartbeat. On le compare
-- uniquement a os.time() : core.getRealTime() a une autre origine (temps
-- depuis le boot) et rendait tout fichier heartbeat valide pour toujours,
-- y compris apres la mort du bridge.
local function isBridgeAlive()
  local ok, res = pcall(function()
    return liveness.isBridgeAlive(ap.expand(config.data_dir), os.time(), readFile, 15)
  end)
  return ok and res == true
end

-- Signature des parametres de connexion : si elle change alors que le bridge
-- tourne deja, il est tue et relance avec les nouvelles valeurs.
local function currentSig()
  return table.concat({
    tostring(setting('host', config.host or '127.0.0.1')),
    tostring(setting('port', config.port or 38281)),
    tostring(setting('slot', config.slot or '')),
    tostring(setting('password', config.password or '')),
    tostring(setting('deathlink', config.deathlink ~= false)),
  }, '|')
end

local activeSig = nil
local pendingSig, pendingSince = nil, 0

local function startBridge()
  if not config.auto_start_bridge then return end
  local alive = isBridgeAlive()
  local sig = currentSig()
  local killPrefix = ''
  local oldSig = ap.readFile('bridge.sig')
  if alive and oldSig == sig then
    -- Bridge deja en cours avec les bons parametres.
    activeSig = sig
    bridgeStarted = true
    return
  end
  if alive then
    -- Parametres changes : arreter l'ancien bridge puis relancer.
    local pid = tonumber((ap.readFile('bridge.lock') or ''):match('%d+'))
    if pid then killPrefix = ('kill %d 2>/dev/null; sleep 1; '):format(pid) end
  end
  -- Changement de serveur (host, port ou slot) : on repart de zero. Les checks
  -- completes sont dans state.json (checks deja envoyes) et out.jsonl (que le
  -- bridge rejoue a chaque demarrage), donc les deux sont supprimes, une fois
  -- l'ancien bridge arrete.
  local function conn(x) return x and x:match('^([^|]*|[^|]*|[^|]*)') end
  if oldSig and conn(oldSig) ~= conn(sig) then
    local d = ap.dir()
    killPrefix = killPrefix .. ('rm -f %s %s %s; '):format(
      shq(d .. 'state.json'), shq(d .. 'out.jsonl'), shq(d .. 'in.jsonl'))
    print('AP: serveur change, checks completes effaces')
  end
  print('AP: startBridge, alive=' .. tostring(alive))
  bridgeStarted = true
  bridgeStartedAt = core.getRealTime()
  activeSig = sig
  ap.writeFile('bridge.sig', sig)

  local dir = ap.dir()
  local bridge = ap.expand(config.bridge_path)
  local python = config.python or 'python3'
  local host = setting('host', config.host or '127.0.0.1')
  local port = setting('port', config.port or 38281)
  local slot = setting('slot', config.slot or '')
  local password = setting('password', config.password or '')
  local deathlink = setting('deathlink', config.deathlink ~= false)

  local env = ('AP_HOST=%s AP_PORT=%s AP_SLOT=%s AP_PASSWORD=%s AP_DATA_DIR=%s AP_DEATHLINK=%s AP_DAEMON=1'):format(
    shq(host),
    shq(tostring(port)),
    shq(slot),
    shq(password),
    shq(dir),
    shq(deathlink and '1' or '0')
  )

  -- Le bridge garantit lui-meme son unicite (flock sur bridge.lock).
  local cmd = ('( %snohup env %s %s %s ) >/dev/null 2>&1 </dev/null &'):format(
    killPrefix, env, shq(python), shq(bridge)
  )
  local ok = ap.exec(cmd)
  print(('AP: bridge launch exec=%s -> %s:%s (slot %s)'):format(
    tostring(ok), tostring(host), tostring(port), tostring(slot)))
end

-- Relance le bridge quand les parametres changent (stables depuis 3 s, pour
-- ne pas relancer a chaque frappe).
local function checkSettingsChange()
  local sig = currentSig()
  if sig == activeSig then pendingSig = nil return end
  local now = core.getRealTime()
  if sig ~= pendingSig then pendingSig, pendingSince = sig, now return end
  if now - pendingSince >= 3 then
    pendingSig = nil
    startBridge()
  end
end

-- Relaye au joueur la liste des items AP recus (deverrouillage des quetes).
local function sendOwned()
  local pl = getPlayer()
  if not pl then return end
  local ids = {}
  for id in pairs(owned) do ids[#ids + 1] = id end
  pcall(function() pl:sendEvent('AP_Owned', { ids = ids }) end)
end

local function applyItem(msg)
  local idx = tonumber(msg.idx)
  if idx == nil then return true end
  if idx <= lastIdx then return true end

  local player = getPlayer()
  if not player then return false end

  local itemId = tonumber(msg.id)
  if itemId then
    -- Marquer avant de donner : la suppression des objets cles ne doit pas
    -- retirer l'objet que l'on vient d'accorder.
    owned[itemId] = true
    sendOwned()
    local ok, applied, effect = pcall(items.apply, player, itemId, idx)
    if not ok then
      print('AP: erreur application item ' .. tostring(itemId) .. ': ' .. tostring(applied))
    elseif applied and effect and effect.type == 'level_up' then
      -- Les stats ne sont modifiables que depuis openmw.self : le script
      -- joueur applique la progression de niveau.
      pcall(function()
        player:sendEvent('AP_LevelUp', { levels = effect.levels })
      end)
    end
    print(('AP item recu: %s (idx %d)'):format(tostring(itemId), idx))
  end
  lastIdx = idx
  return true
end

local function processPending()
  if not getPlayer() then return end
  local i = 1
  while i <= #pending do
    if not applyItem(pending[i]) then return end
    table.remove(pending, i)
  end
end

-- Relaie au script joueur les notifications d'items (recus / envoyes).
local function processNotify()
  if #pendingNotify == 0 then return end
  local pl = getPlayer()
  if not pl then return end
  for _, m in ipairs(pendingNotify) do
    pcall(function()
      pl:sendEvent('AP_Notify', {
        dir = m.dir, item = m.item, player = m.player,
        location = m.location, flags = m.flags,
      })
    end)
  end
  pendingNotify = {}
end

local function handle(msg)
  if type(msg) ~= 'table' then return end

  if msg.t == 'item' then
    pending[#pending + 1] = msg
  elseif msg.t == 'notify' then
    local okT, now = pcall(os.time)
    if notify.accept(msg, lastNotify, okT and now or nil) then
      lastNotify = tonumber(msg.id)
      pendingNotify[#pendingNotify + 1] = msg
    end
  elseif msg.t == 'config' then
    serverOptions = msg.options or {}
    if msg.goal ~= nil then serverOptions.goal = msg.goal end
    -- Relayer l'objectif au script joueur
    local pl = getPlayer()
    if pl then
      pcall(function() pl:sendEvent('AP_Config', { goals = serverOptions.goals, goal = serverOptions.goal }) end)
    end
    -- Propager death_link (YAML) vers le stockage global pour player.lua
    if serverOptions.death_link ~= nil then
      pcall(function()
        storage.globalSection(SETTINGS_KEY):set('deathlink', serverOptions.death_link)
      end)
    end
  elseif msg.t == 'deathlink' then
    local dl = serverOptions.death_link
    if dl == nil then dl = setting('deathlink', config.deathlink) end
    if dl and msg.from ~= setting('slot', config.slot) then
      local player = getPlayer()
      if player then
        pcall(function() player:sendEvent('AP_DeathLink', {}) end)
        pcall(function()
          types.Actor.stats.dynamic.health(player).current = 0
        end)
        print('AP: DeathLink recu de ' .. tostring(msg.from))
      end
    end
  elseif msg.t == 'sync' then
    -- Nouvelle session du bridge : le fichier a deja ete remplace et lu
    -- depuis le debut par ap.poll(). On ne remet pas lastIdx a zero, sinon
    -- les items deja appliques seraient donnes une seconde fois.
    print('AP: bridge synchronise')
  end
end

-- Liste des objectifs (cles de goals.lua) : quete principale + maison /
-- guilde / faction choisies. Ancien format : goal = 'main_quest' ou 0.
local function goalKeys()
  local out = {}
  local g = serverOptions.goals
  if type(g) == 'table' then
    for _, k in ipairs(g) do out[#out + 1] = tostring(k):lower() end
  elseif serverOptions.goal ~= nil then
    local gk = serverOptions.goal
    if type(gk) == 'number' then
      if gk == 0 then out[1] = 'main_quest' end
    else
      out[1] = tostring(gk):lower()
    end
  end
  return out
end

-- Tant que la config du serveur n'est pas arrivee, on ne connait pas les
-- objectifs choisis. On bloque prudemment les sanctuaires daedriques : ils
-- seront liberes si la seed n'inclut pas l'objectif daedric_quests.
local function goalsKnown()
  return serverOptions.goals ~= nil or serverOptions.goal ~= nil
end

local function lockApplies(goal)
  if not goalsKnown() then return true end
  for _, k in ipairs(goalKeys()) do
    if k == goal then return true end
  end
  return false
end

-- Verrouillage des sanctuaires daedriques AVANT l'action vanilla. Les scripts
-- MWScript (DaedraAzura, ...) testent `OnActivate == 1` ; ce flag n'est pose
-- que par l'action d'activation standard. Annuler l'activation via l'interface
-- Activation empeche donc le script de parler, de modifier le journal et
-- d'activer ses creatures. Un simple reset de journal apres coup est trop tard.
local activationRegistered = false

local function ensureActivationHandler()
  if activationRegistered then return end
  if not (I.Activation and I.Activation.addHandlerForType) then return end
  local ok = pcall(function()
    I.Activation.addHandlerForType(types.Activator, function(obj, actor)
      local locked
      local pok = pcall(function()
        local record = types.Activator.record(obj)
        locked = activationLock.blockedLock(ACTIVATORS, {
          id = obj.recordId,
          mwscript = record and record.mwscript,
        }, owned, lockApplies)
      end)
      if pok and locked then
        print('AP: activation verrouillee : ' .. tostring(locked.quest))
        local pl = getPlayer()
        if pl and actor and actor.type == types.Player then
          pcall(function()
            pl:sendEvent('AP_LockedActivation', { name = locked.name, quest = locked.quest })
          end)
        end
        return false
      end
    end)
  end)
  if ok then activationRegistered = true end
end

local function suppressKeyItems(player)
  -- Les objets 'misc' (quetes secondaires) sont toujours supprimes,
  -- independamment des objectifs choisis dans la seed : ils ne dependent
  -- pas d'un goal et leur item AP est toujours dans le pool.
  local goals = goalKeys()
  table.insert(goals, 'misc')
  local suppress = items.suppressFor(goals)
  if next(suppress) == nil then return end
  local inv = types.Actor.inventory(player)
  -- Ne pas supprimer le package dans le Census Office : la porte de sortie
  -- (MWScript) l'exige pour laisser passer. On le retire apres la sortie.
  local inCensus = false
  pcall(function()
    if player.cell and player.cell.name == 'Seyda Neen, Census and Excise Office' then
      inCensus = true
    end
  end)
  for apId, records in pairs(suppress) do
    if not owned[apId] then
      -- Garder le package dans le Census Office pour passer la porte.
      if items.keepInCensus(records, inCensus) then
        -- Accorder temporairement le package s'il manque (pour la porte).
        pcall(function()
          if inv:countOf(items.CENSUS_PACKAGE) == 0 then
            local o = world.createObject(items.CENSUS_PACKAGE, 1)
            o:moveInto(inv)
          end
        end)
      else
        for _, recordId in ipairs(records) do
          local ok, objects = pcall(function() return inv:findAll(recordId) end)
          if ok and objects then
            for _, obj in ipairs(objects) do
              pcall(function() obj:remove() end)
            end
          end
        end
      end
    end
  end
end

return {
  eventHandlers = {
    -- Le joueur demande la config (chargement de sauvegarde / nouvelle partie).
    AP_RequestConfig = function()
      local pl = getPlayer()
      if pl and (serverOptions.goals ~= nil or serverOptions.goal ~= nil) then
        pcall(function() pl:sendEvent('AP_Config', { goals = serverOptions.goals, goal = serverOptions.goal }) end)
      end
      sendOwned()
    end,
    -- Mort de Dagoth Ur (actor.lua) -> script joueur.
    AP_DagothDead = function()
      local pl = getPlayer()
      if pl then pcall(function() pl:sendEvent('AP_DagothDead', {}) end) end
    end,
  },
  engineHandlers = {
    onActivate = function(object, actor)
      if object and object.recordId == 'chargen exit door' then
        -- Forcer l'ouverture de la porte sans le package de Caius Cosades.
        pcall(function() object:activateBy(actor) end)
      end
    end,

    onInit = function()
      -- (Re)enregistrer le groupe au cas ou le chargement au niveau module
      -- n'a pas eu lieu (interface non disponible au demarrage).
      pcall(function()
        if I.Settings and I.Settings.registerGroup then
          I.Settings.registerGroup {
            key = SETTINGS_KEY,
            page = 'Archipelago',
            l10n = 'Archipelago',
            name = 'groupName',
            description = '',
            permanentStorage = true,
            order = 0,
            settings = {
              { key = 'host', renderer = 'textLine', name = 'hostName', description = 'hostDesc', default = config.host or '127.0.0.1' },
              { key = 'port', renderer = 'number', name = 'portName', description = 'portDesc', default = config.port or 38281, argument = { integer = true, min = 1, max = 65535 } },
              { key = 'slot', renderer = 'textLine', name = 'slotName', description = 'slotDesc', default = config.slot or 'TestMW' },
              { key = 'password', renderer = 'textLine', name = 'passwordName', description = 'passwordDesc', default = config.password or '' },
              { key = 'deathlink', renderer = 'checkbox', name = 'deathlinkName', description = 'deathlinkDesc', default = config.deathlink ~= false },
              { key = 'notifications', renderer = 'checkbox', name = 'notificationsName', description = 'notificationsDesc', default = true },
            }
          }
        end
      end)
      startBridge()
      ensureActivationHandler()
    end,

    onUpdate = function(dt)
      timer = timer + dt
      ensureActivationHandler()
      local interval = tonumber(config.poll_interval) or 1.0
      if interval < 0.2 then interval = 0.2 end
      if timer >= interval then
        timer = 0
        for _, line in ipairs(ap.poll()) do
          local ok, msg = pcall(json.decode, line)
          if ok and msg then
            local hok, herr = pcall(handle, msg)
            if not hok then print('AP: message invalide: ' .. tostring(herr)) end
          end
        end
      end

      processPending()
      processNotify()
      checkSettingsChange()

      local player = getPlayer()
      if player then
        suppressKeyItems(player)

        -- Heartbeat pour le bridge (detecte l'arret du jeu)
        local now = core.getRealTime()
        if now - (lastHeartbeat or 0) >= 10 then
          lastHeartbeat = now
          ap.send('{"t":"heartbeat"}')
        end

        -- Si le bridge meurt pendant la partie (crash, kill, heartbeat
        -- perime), le relancer sans attendre un rechargement de sauvegarde.
        -- On laisse 20 s au bridge qui vient d'etre lance pour ecrire son
        -- premier heartbeat.
        if config.auto_start_bridge and now - lastBridgeCheck >= 10 then
          lastBridgeCheck = now
          if now - bridgeStartedAt >= 20 and not isBridgeAlive() then
            print('AP: bridge inactif, relance')
            startBridge()
          end
        end

        dbgCounter = dbgCounter + 1
        if dbgCounter % 30 == 0 then
          local n = 0
          for _ in pairs(owned) do n = n + 1 end
          print(('AP: lastIdx=%d items_recus=%d'):format(lastIdx, n))
        end
      end
    end,

    onSave = function()
      return {
        lastIdx = lastIdx,
        owned = owned,
        serverOptions = serverOptions,
        lastNotify = lastNotify,
      }
    end,

    onLoad = function(d)
      if d then
        lastIdx = tonumber(d.lastIdx)
        if lastIdx == nil then lastIdx = -1 end
        lastNotify = tonumber(d.lastNotify) or 0
        owned = d.owned or {}
        serverOptions = d.serverOptions or {}
        -- Ancienne sauvegarde : lastIdx valait 0 et l'item d'index 0 n'a
        -- jamais ete applique.
        if lastIdx == 0 and next(owned) == nil then lastIdx = -1 end
      end
      -- Relancer le bridge s'il est mort (sinon le garder).
      startBridge()
    end,
  },
}
