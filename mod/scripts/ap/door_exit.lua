-- Local script attached to the Census Office exit door.
-- Allows leaving without Caius Cosades' package.
local self = require('openmw.self')

local activated = false

return {
  engineHandlers = {
    onActivate = function(actor)
      if activated then return end
      activated = true
      self:activateBy(actor)
    end,
  },
}
