-- Actor script: detection of Dagoth Ur's death (victory goal)
local self = require('openmw.self')
local types = require('openmw.types')
local core = require('openmw.core')

local reported = false

local function onUpdate(dt)
  if reported then return end
  if self.recordId ~= 'dagoth_ur_2' then return end
  if types.Actor.isDead(self) then
    reported = true
    pcall(function() core.sendGlobalEvent('AP_DagothDead', {}) end)
  end
end

return {
  engineHandlers = {
    onUpdate = onUpdate,
  },
}