-- Verrouillage des activateurs de quetes (sanctuaires daedriques).
--
-- Module pur (sans dependance OpenMW) pour pouvoir etre teste avec luajit.
-- `ACTIVATORS` est genere par tools/gen_lua.py depuis data/quest_locks.yaml.

local M = {}

local function entryFor(activators, record)
  if not activators or not record then return nil end
  -- Le script MWScript est le critere principal : les sanctuaires vanilla
  -- testent `OnActivate == 1` et partagent leurs scripts entre plusieurs
  -- records (statue, ruine, autel).
  if record.mwscript and activators.by_script then
    local entry = activators.by_script[record.mwscript]
    if entry then return entry end
  end
  -- Repli sur l'ID du record ACTI si un mod renomme le script.
  if record.id and activators.by_record then
    return activators.by_record[record.id]
  end
  return nil
end

-- Retourne l'entree de verrouillage qui doit bloquer cette activation, ou nil
-- si l'activation est autorisee. `owned` : table id d'item AP -> true.
function M.blockedLock(activators, record, owned, goalActive)
  local entry = entryFor(activators, record)
  if not entry then return nil end
  if owned and owned[entry.id] then return nil end
  if goalActive and not goalActive(entry.goal) then return nil end
  return entry
end

return M
