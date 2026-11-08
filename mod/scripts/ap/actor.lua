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

-- Trap (summon scamp): the creature immediately attacks the player.
local function onAttack(data)
  if type(data) ~= 'table' or not data.target then return end
  local ok, err = pcall(function()
    local I = require('openmw.interfaces')
    I.AI.startPackage({ type = 'Combat', target = data.target })
  end)
  if not ok then print('AP: AP_Attack failed: ' .. tostring(err)) end
end

return {
  engineHandlers = {
    onUpdate = onUpdate,
  },
  eventHandlers = {
    AP_Attack = onAttack,
  },
}
