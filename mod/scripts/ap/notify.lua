-- In-game notifications for received / sent Archipelago items.
--
-- The bridge writes messages to in.jsonl:
--   {"t":"notify","id":..,"ts":..,"dir":"recv|send|self","item":..,
--    "player":..,"location":..,"flags":n}
-- global.lua filters them (accept) then relays them to the player script,
-- which queues them and displays them (format) at a regular interval.
local M = {}

M.MAX_AGE = 600   -- seconds: beyond this, a notification is considered stale
M.MAX_QUEUE = 30  -- maximum display queue size
M.GAP = 2.0       -- seconds between two displayed messages

local function hasBit(flags, n)
  return math.floor(flags / (2 ^ n)) % 2 == 1
end

-- Archipelago flags: 1 = progression, 2 = useful, 4 = trap.
function M.flagTag(flags)
  flags = tonumber(flags) or 0
  if hasBit(flags, 2) then return ' [Trap]' end
  if hasBit(flags, 0) then return ' [Progression]' end
  if hasBit(flags, 1) then return ' [Useful]' end
  return ''
end

-- True if the notification is new (id > last seen id) and recent.
-- Ids increase: in.jsonl is re-read from the start on every save load,
-- this filter avoids replaying old messages.
function M.accept(msg, lastId, now)
  if type(msg) ~= 'table' then return false end
  local id = tonumber(msg.id)
  if not id or id <= (tonumber(lastId) or 0) then return false end
  local ts = tonumber(msg.ts)
  if ts and now and (now - ts) > M.MAX_AGE then return false end
  return true
end

-- Display text for a notification, nil if the message is unusable.
-- Quest checks (Archipelago locations) show the quest name in parentheses
-- and the check completion; other messages keep the old format.
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
      return 'Archipelago: ' .. item .. tag .. ' (' .. loc .. ') obtained'
    end
    return 'Archipelago: you found ' .. item .. tag
  elseif d.dir == 'send' then
    if loc then
      return 'Archipelago: ' .. item .. tag .. ' (' .. loc .. ') obtained -> ' .. (who or '?')
    end
    return 'Archipelago: you sent ' .. item .. tag .. ' to ' .. (who or '?')
  elseif d.dir == 'recv' then
    if who then
      return 'Archipelago: ' .. who .. ' sends you ' .. item .. tag
    end
    return 'Archipelago: you receive ' .. item .. tag
  end
  return nil
end

return M
