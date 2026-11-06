-- Detection de l'activite du bridge a partir de bridge.heartbeat.
--
-- Le bridge Python ecrit un timestamp Unix (time.time()) dans ce fichier
-- toutes les secondes. OpenMW expose core.getRealTime(), mais son origine
-- n'est pas fixe (temps depuis le demarrage / le boot) : il ne faut donc
-- jamais le comparer au timestamp du fichier. On compare uniquement avec
-- os.time() (epoch Unix).
local M = {}

-- dir      : dossier de donnees du bridge (celui de config.data_dir)
-- now      : heure Unix courante (os.time())
-- readFile : function(path) -> contenu du fichier ou nil
-- maxAge   : age maximal en secondes (15 par defaut)
function M.isBridgeAlive(dir, now, readFile, maxAge)
  if type(dir) ~= 'string' or type(now) ~= 'number' or type(readFile) ~= 'function' then
    return false
  end
  if dir:sub(-1) ~= '/' then dir = dir .. '/' end
  local content = readFile(dir .. 'bridge.heartbeat')
  if not content then return false end
  local ts = tonumber(content:match('^%s*([%d%.]+)'))
  if not ts then return false end
  maxAge = tonumber(maxAge) or 15
  local age = now - ts
  -- Une petite avance d'horloge est toleree ; un timestamp trop vieux ou
  -- trop lointain signifie que le bridge n'est plus celui de cette session.
  return age >= -5 and age <= maxAge
end

return M
