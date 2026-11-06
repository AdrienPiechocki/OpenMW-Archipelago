-- Filtre des checks de completion de quetes d'objectif.
--
-- Les quetes Miscellaneous donnent toujours un check. Les quetes d'un groupe
-- d'objectif (main, hlaalu, ..., daedric) ne donnent un check que si l'option
-- Goal Quest Checks n'est pas "off" ET que l'objectif correspondant est choisi :
-- le serveur n'a cree la location que dans ce cas (sinon il rejetterait l'ID).
local M = {}

-- Groupe de quetes -> cle d'objectif (goals.lua). Les groupes de maisons /
-- guildes / factions portent le nom de leur objectif.
M.GROUP_GOALS = { main = 'main_quest', daedric = 'daedric_quests' }

function M.goalOfGroup(group)
  return M.GROUP_GOALS[group] or group
end

-- goalList : liste des cles d'objectif choisies (nil tant que le serveur n'a pas repondu)
function M.allowed(group, goalList)
  if group == nil or group == 'misc' then return true end
  if type(goalList) ~= 'table' then return false end
  local key = M.goalOfGroup(group)
  for _, k in ipairs(goalList) do
    if k == key then return true end
  end
  return false
end
