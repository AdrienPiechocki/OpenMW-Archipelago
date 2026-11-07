-- Notifications en jeu pour les items Archipelago recus / envoyes.
--
-- Le bridge ecrit dans in.jsonl des messages
--   {"t":"notify","id":..,"ts":..,"dir":"recv|send|self","item":..,
--    "player":..,"location":..,"flags":n}
-- global.lua les filtre (accept) puis les relaie au script joueur, qui les
-- met en file et les affiche (format) a intervalle regulier.
local M = {}

M.MAX_AGE = 600   -- secondes : au-dela, une notification est consideree perimee
M.MAX_QUEUE = 30  -- taille maximale de la file d'affichage
M.GAP = 2.0       -- secondes entre deux messages affiches

local function hasBit(flags, n)
  return math.floor(flags / (2 ^ n)) % 2 == 1
end

-- Flags Archipelago : 1 = progression, 2 = utile, 4 = piege.
function M.flagTag(flags)
  flags = tonumber(flags) or 0
  if hasBit(flags, 2) then return ' [Piège]' end
  if hasBit(flags, 0) then return ' [Progression]' end
  if hasBit(flags, 1) then return ' [Utile]' end
  return ''
end

-- Vrai si la notification est nouvelle (id > dernier id vu) et recente.
-- Les ids sont croissants : in.jsonl est relu depuis le debut a chaque
-- chargement de sauvegarde, ce filtre evite de rejouer d'anciens messages.
function M.accept(msg, lastId, now)
  if type(msg) ~= 'table' then return false end
  local id = tonumber(msg.id)
  if not id or id <= (tonumber(lastId) or 0) then return false end
  local ts = tonumber(msg.ts)
  if ts and now and (now - ts) > M.MAX_AGE then return false end
  return true
end

-- Texte affiche pour une notification, nil si le message est inutilisable.
-- Les checks de quete (locations Archipelago) indiquent le nom de la quete
-- entre parentheses et la completion du check ; les autres messages gardent
-- l'ancien format.
function M.format(d)
  if type(d) ~= 'table' then return nil end
  local item = tostring(d.item or '?')
  local tag = M.flagTag(d.flags)
  local who = d.player ~= nil and tostring(d.player) or nil
  local loc = nil
  if d.location ~= nil and tostring(d.location) ~= '' then
    loc = tostring(d.location)
  end

  if d.dir == 'self' then
    if loc then
      return 'Archipelago : ' .. item .. tag .. ' (' .. loc .. ') obtenu [check complété]'
    end
    return 'Archipelago : vous avez trouvé ' .. item .. tag
  elseif d.dir == 'send' then
    if loc then
      return 'Archipelago : ' .. item .. tag .. ' (' .. loc .. ') obtenu [check complété] -> ' .. (who or '?')
    end
    return 'Archipelago : vous envoyez ' .. item .. tag .. ' à ' .. (who or '?')
  elseif d.dir == 'recv' then
    if who then
      return 'Archipelago : ' .. who .. ' vous envoie ' .. item .. tag
    end
    return 'Archipelago : vous recevez ' .. item .. tag
  end
  return nil
end

return M
