-- Definition of the Archipelago settings group (connection settings).
-- Shared by settings.lua (MENU: the settings are editable from the main
-- menu, without starting a game) and global.lua (which reads the values).
local config = require('scripts.ap.config')

local M = {}

M.KEY = 'SettingsArchipelago'

function M.group()
  return {
    key = M.KEY,
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
    },
  }
end

return M
