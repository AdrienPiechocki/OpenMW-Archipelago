-- Registration of the mod settings in the OpenMW menu.
local I = require('openmw.interfaces')
local core = require('openmw.core')
local l10n = core.l10n('Archipelago')

I.Settings.registerPage {
    key = 'Archipelago',
    l10n = 'Archipelago',
    name = 'pageName',
    description = 'Archipelago multiworld connection',
}

-- Connection settings group: registered here (MENU script) so that host /
-- port / slot... can be edited from the main menu, before any game is
-- started. global.lua reads the same section (same key, permanent storage).
pcall(function()
  I.Settings.registerGroup(require('scripts.ap.settings_def').group())
end)

-- The options page values are mirrored into connection.cfg whenever they
-- differ from it, from the main menu or in game. The bridge launcher
-- (global.lua) and player.lua read that file, so what is shown in this page is
-- what the mod uses. (Values edited in the main menu are not visible from the
-- global script's own storage, which is why a file is used.)
-- The page is the reference: a hand edit of connection.cfg is overwritten.
-- Storage is only readable once the menu is up, so it is accessed lazily from
-- onFrame (never at script load) and every access is protected.
local KEYS = { 'host', 'port', 'slot', 'password', 'deathlink', 'notifications' }
local FILE = 'connection.cfg'
local mirror = { last = -1e9, lastTxt = nil, lastDiag = nil, ap = nil, tried = false }

local function readSection(kind)
  local ok, res = pcall(function()
    local storage = require('openmw.storage')
    local def = require('scripts.ap.settings_def')
    local sec = (kind == 'player') and storage.playerSection(def.KEY) or storage.globalSection(def.KEY)
    local t, any = {}, false
    for _, k in ipairs(KEYS) do
      t[k] = sec:get(k)
      if t[k] ~= nil then any = true end
    end
    return { values = t, any = any }
  end)
  if ok then return res end
  return nil, tostring(res)
end

local function boolStr(v, default)
  if v == nil then return tostring(default) end
  return tostring(v == true or v == 'true')
end

local function render(v)
  local config = require('scripts.ap.config')
  local port = tonumber(v.port) or tonumber(config.port) or 38281
  local function nz(x, d) if x == nil then return d end return x end
  return table.concat({
    '# Archipelago connection (read by the OpenMW mod).',
    '# Written by the options page (main menu > Options > Scripts > Archipelago).',
    'host = ' .. tostring(nz(v.host, config.host or '127.0.0.1')),
    'port = ' .. tostring(math.floor(port)),
    'slot = ' .. tostring(nz(v.slot, config.slot or 'TestMW')),
    'password = ' .. tostring(nz(v.password, config.password or '')),
    'deathlink = ' .. boolStr(v.deathlink, config.deathlink ~= false),
    'notifications = ' .. boolStr(v.notifications, true),
    '',
  }, '\n')
end

local function step()
  if not mirror.ap then
    if mirror.tried then return end
    mirror.tried = true
    local okIo, ap = pcall(require, 'scripts.ap.io')
    if not okIo then
      print('AP: menu cannot write connection.cfg (io unavailable): ' .. tostring(ap))
      return
    end
    mirror.ap = ap
    print('AP: menu options script active, io ok')
  end

  local ap = mirror.ap
  local pl, perr = readSection('player')
  local gl, gerr = readSection('global')
  local src, kind = nil, nil
  if pl and pl.any then src, kind = pl.values, 'player'
  elseif gl and gl.any then src, kind = gl.values, 'global' end

  local function brief(r, e)
    if not r then return 'unreadable (' .. tostring(e) .. ')' end
    return 'port=' .. tostring(r.values.port) .. ' host=' .. tostring(r.values.host)
  end
  local diag = ('player: %s | global: %s | using: %s'):format(brief(pl, perr), brief(gl, gerr), tostring(kind))
  if diag ~= mirror.lastDiag then
    mirror.lastDiag = diag
    print('AP: menu storage -> ' .. diag)
  end
  if not src then return end

  local txt = render(src)
  if txt == mirror.lastTxt then return end
  mirror.lastTxt = txt
  if ap.readFile(FILE) == txt then return end
  if ap.writeFile(FILE, txt) then
    print(('AP: connection.cfg written from %s storage: host=%s port=%s slot=%s'):format(
      kind, tostring(src.host), tostring(src.port), tostring(src.slot)))
  else
    print('AP: menu cannot write ' .. FILE)
  end
end

local function guarded()
  local ok, err = pcall(step)
  if not ok then
    local e = tostring(err)
    if e ~= mirror.lastErr then
      mirror.lastErr = e
      print('AP: menu options script error: ' .. e)
    end
  end
end

return {
  engineHandlers = {
    -- Throttled on REAL time: the dt given to menu scripts is game time, which
    -- stays at 0 in the main menu (that is why nothing was written there).
    onFrame = function()
      local now = core.getRealTime()
      if now - mirror.last < 0.5 then return end
      mirror.last = now
      guarded()
    end,
    -- Last sync right when a game is started / loaded.
    onStateChanged = function() guarded() end,
  },
}
