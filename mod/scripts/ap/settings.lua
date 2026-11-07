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
