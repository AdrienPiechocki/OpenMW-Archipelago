-- Bridge liveness detection from bridge.heartbeat.
--
-- The Python bridge writes a Unix timestamp (time.time()) to this file
-- every second. OpenMW exposes core.getRealTime(), but its origin
-- is not fixed (time since start / boot): it must therefore
-- never be compared with the timestamp in the file. We compare only
-- with os.time() (Unix epoch).
local M = {}

-- dir: bridge data directory (the one from config.data_dir)
-- now: current Unix time (os.time())
-- readFile: function(path) -> file content or nil
-- maxAge: maximum age in seconds (15 by default)
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
  -- A small clock advance is tolerated; a timestamp that is too old or
  -- too far in the future means the bridge is no longer the one from this
  -- session.
  return age >= -5 and age <= maxAge
end

return M
