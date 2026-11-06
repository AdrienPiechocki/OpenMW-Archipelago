-- Script local attache a la porte de sortie du Census Office.
-- Permet de sortir sans le package de Caius Cosades.
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
