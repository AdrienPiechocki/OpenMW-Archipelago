-- Global script: item reception, bridge launch, effect application
-- and removal of vanilla copies of key items.
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

-- Register the settings group in global storage (so the global script can
-- read the values at startup).
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
  -- silent in production; uncomment for debugging
end

-- Index of the last applied item. -1 = no item (the Archipelago index
-- starts at 0).
local lastIdx = -1
local firstPollDone = false  -- the 1st poll after a load replays the whole in.jsonl
local owned = {}          -- AP item id -> true
local pending = {}        -- "item" messages waiting for a loaded player
local lastNotify = 0      -- last notification id relayed to the player
local pendingNotify = {}  -- notifications waiting for a loaded player
local serverOptions = {}  -- options sent in slot_data
local timer = 0
-- (transportTimer removed)
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

-- The bridge writes a Unix timestamp to bridge.heartbeat. We compare it
-- only with os.time(): core.getRealTime() has a different origin (time
-- since boot) and made every heartbeat file valid forever, even after
-- the bridge died.
local function isBridgeAlive()
  local ok, res = pcall(function()
    return liveness.isBridgeAlive(ap.expand(config.data_dir), os.time(), readFile, 15)
  end)
  return ok and res == true
end

-- Connection settings signature: if it changes while the bridge is already
-- running, it is killed and restarted with the new values.
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
    -- Bridge already running with the correct settings.
    activeSig = sig
    bridgeStarted = true
    return
  end
  if alive then
    -- Settings changed: stop the old bridge then restart.
    local pid = tonumber((ap.readFile('bridge.lock') or ''):match('%d+'))
    if pid then killPrefix = ('kill %d 2>/dev/null; sleep 1; '):format(pid) end
  end
  -- Server change (host, port or slot): start from scratch. Completed checks
  -- are in state.json (already sent checks) and out.jsonl (which the bridge
  -- replays on every start), so both are deleted once the old bridge is
  -- stopped.
  local function conn(x) return x and x:match('^([^|]*|[^|]*|[^|]*)') end
  if oldSig and conn(oldSig) ~= conn(sig) then
    local d = ap.dir()
    killPrefix = killPrefix .. ('rm -f %s %s %s; '):format(
      shq(d .. 'state.json'), shq(d .. 'out.jsonl'), shq(d .. 'in.jsonl'))
    print('AP: server changed, completed checks cleared')
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

  -- The bridge enforces its own uniqueness (flock on bridge.lock).
  local cmd = ('( %snohup env %s %s %s ) >/dev/null 2>&1 </dev/null &'):format(
    killPrefix, env, shq(python), shq(bridge)
  )
  local ok = ap.exec(cmd)
  print(('AP: bridge launch exec=%s -> %s:%s (slot %s)'):format(
    tostring(ok), tostring(host), tostring(port), tostring(slot)))
end

-- Restart the bridge when settings change (stable for 3 s, so it does not
-- restart on every keystroke).
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

-- Relay the list of received AP items to the player (quest unlocking).
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
    -- Mark before giving: removing key items must not remove the item
    -- that was just granted.
    owned[itemId] = true
    sendOwned()
    local ok, applied, effect = pcall(items.apply, player, itemId, idx)
    if not ok then
      print('AP: error applying item ' .. tostring(itemId) .. ': ' .. tostring(applied))
    elseif applied and effect and effect.type == 'level_up' then
      -- Stats can only be modified from openmw.self: the player script
      -- applies the level progression.
      pcall(function()
        player:sendEvent('AP_LevelUp', { levels = effect.levels })
      end)
    elseif applied and effect and effect.type == 'damage' then
      pcall(function()
        player:sendEvent('AP_Damage', { amount = effect.amount })
      end)
    elseif applied and effect and effect.type == 'skill' then
      pcall(function()
        player:sendEvent('AP_SkillBoost', { skill = effect.skill, amount = effect.amount })
      end)
    end
    print(('AP item received: %s (idx %d)'):format(tostring(itemId), idx))
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

-- Relay item notifications (received / sent) to the player script.
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
    -- Relay the goal to the player script
    local pl = getPlayer()
    if pl then
      pcall(function() pl:sendEvent('AP_Config', { goals = serverOptions.goals, goal = serverOptions.goal, expansionGroups = serverOptions.expansion_groups, startingLevel = serverOptions.starting_level }) end)
    end
    -- Propagate death_link (YAML) to global storage for player.lua
    if serverOptions.death_link ~= nil then
      pcall(function()
        storage.globalSection(SETTINGS_KEY):set('deathlink', serverOptions.death_link)
      end)
    end
  elseif msg.t == 'deathlink' then
    -- Ignore DeathLinks replayed from in.jsonl when a save is loaded
    -- (otherwise: death loop on every reload).
    if msg._replay then return end
    local okT, nowT = pcall(os.time)
    local ts = tonumber(msg.ts)
    if okT and ts and (nowT - ts) > 30 then return end
    local dl = serverOptions.death_link
    if dl == nil then dl = setting('deathlink', config.deathlink) end
    if dl and msg.from ~= setting('slot', config.slot) then
      local player = getPlayer()
      if player then
        pcall(function() player:sendEvent('AP_DeathLink', { from = msg.from, cause = msg.cause }) end)
        print('AP: DeathLink received from ' .. tostring(msg.from))
      end
    end
  elseif msg.t == 'sync' then
    -- New bridge session: the file has already been replaced and read
    -- from the start by ap.poll(). We do not reset lastIdx to zero, otherwise
    -- already applied items would be given a second time.
    print('AP: bridge synchronized')
  end
end

-- List of goals (keys from goals.lua): main quest + chosen house /
-- guild / faction. Old format: goal = 'main_quest' or 0.
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

-- Until the server config arrives, the chosen goals are unknown. Daedric
-- shrines are blocked as a precaution: they will be released if the seed
-- does not include the daedric_quests goal.
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

-- Locking of Daedric shrines BEFORE the vanilla action. MWScript scripts
-- (DaedraAzura, ...) test `OnActivate == 1`; this flag is only set by the
-- standard activation action. Cancelling the activation through the
-- Activation interface therefore prevents the script from speaking, editing
-- the journal and activating its creatures. A simple journal reset afterwards
-- is too late.
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
        print('AP: locked activation: ' .. tostring(locked.quest))
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
  -- 'misc' items (secondary quests) are always suppressed, regardless of
  -- the goals chosen in the seed: they do not depend on a goal and their AP
  -- item is always in the pool.
  local goals = goalKeys()
  table.insert(goals, 'misc')
  local suppress = items.suppressFor(goals)
  if next(suppress) == nil then return end
  local inv = types.Actor.inventory(player)
  -- Do not remove the package in the Census Office: the exit door
  -- (MWScript) requires it to let the player through. It is removed after
  -- leaving.
  local inCensus = false
  pcall(function()
    if player.cell and player.cell.name == 'Seyda Neen, Census and Excise Office' then
      inCensus = true
    end
  end)
  for apId, records in pairs(suppress) do
    if not owned[apId] then
      -- Keep the package in the Census Office to pass through the door.
      if items.keepInCensus(records, inCensus) then
        -- Temporarily grant the package if it is missing (for the door).
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
    -- The player requests the config (save load / new game).
    AP_RequestConfig = function()
      local pl = getPlayer()
      if pl and (serverOptions.goals ~= nil or serverOptions.goal ~= nil) then
        pcall(function() pl:sendEvent('AP_Config', { goals = serverOptions.goals, goal = serverOptions.goal, expansionGroups = serverOptions.expansion_groups, startingLevel = serverOptions.starting_level }) end)
      end
      sendOwned()
    end,
    -- Death of Dagoth Ur (actor.lua) -> player script.
    AP_DagothDead = function()
      local pl = getPlayer()
      if pl then pcall(function() pl:sendEvent('AP_DagothDead', {}) end) end
    end,
  },
  engineHandlers = {
    onActivate = function(object, actor)
      if object and object.recordId == 'chargen exit door' then
        -- Force the door open without Caius Cosades' package.
        pcall(function() object:activateBy(actor) end)
      end
    end,

    onInit = function()
      -- (Re)register the group in case loading at module level did not
      -- happen (interface unavailable at startup).
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
        local replay = not firstPollDone
        firstPollDone = true
        for _, line in ipairs(ap.poll()) do
          local ok, msg = pcall(json.decode, line)
          if ok and msg then
            if replay then msg._replay = true end
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

        -- Heartbeat for the bridge (detects the game stopping)
        local now = core.getRealTime()
        if now - (lastHeartbeat or 0) >= 10 then
          lastHeartbeat = now
          ap.send('{"t":"heartbeat"}')
        end

        -- If the bridge dies during the game (crash, kill, stale
        -- heartbeat), restart it without waiting for a save reload.
        -- The bridge that was just started is given 20 s to write its
        -- first heartbeat.
        if config.auto_start_bridge and now - lastBridgeCheck >= 10 then
          lastBridgeCheck = now
          if now - bridgeStartedAt >= 20 and not isBridgeAlive() then
            print('AP: bridge inactive, restarting')
            startBridge()
          end
        end

        dbgCounter = dbgCounter + 1
        if dbgCounter % 30 == 0 then
          local n = 0
          for _ in pairs(owned) do n = n + 1 end
          print(('AP: lastIdx=%d items_received=%d'):format(lastIdx, n))
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
        -- Old save: lastIdx was 0 and item index 0 was never
        -- applied.
        if lastIdx == 0 and next(owned) == nil then lastIdx = -1 end
      end
      -- Restart the bridge if it died (otherwise keep it).
      startBridge()
    end,
  },
}
