-- Regression test for the bridge heartbeat liveness check.
--
-- Run from the repository root:
--   luajit tools/test_liveness.lua
--
-- The bridge writes bridge.heartbeat with a Unix timestamp (Python
-- time.time()). OpenMW's core.getRealTime() has a different origin (time
-- since boot/start), so it must never be compared with that timestamp.
package.path = 'mod/?.lua;' .. package.path

local liveness = require('scripts.ap.liveness')

local failures = 0
local function check(name, actual, expected)
  if actual ~= expected then
    failures = failures + 1
    print(('FAIL %s: got %s, expected %s'):format(name, tostring(actual), tostring(expected)))
  else
    print(('ok   %s'):format(name))
  end
end

-- Build a fake heartbeat reader instead of touching the filesystem.
local function reader(content)
  return function(path)
    if path:match('/bridge%.heartbeat$') then return content end
    return nil
  end
end

local NOW = 1800000000

-- A bridge that wrote its heartbeat 2 seconds ago is alive.
check('fresh heartbeat', liveness.isBridgeAlive('/ap', NOW, reader(tostring(NOW - 2)), 15), true)

-- A heartbeat left behind by a previous (dead) bridge must not be trusted.
-- This is the reported bug: after quitting, the old timestamp kept the mod
-- from ever launching a new bridge.
check('stale heartbeat (1 hour old)', liveness.isBridgeAlive('/ap', NOW, reader(tostring(NOW - 3600)), 15), false)
check('stale heartbeat (1 day old)', liveness.isBridgeAlive('/ap', NOW, reader(tostring(NOW - 86400)), 15), false)

-- No heartbeat file means no live bridge.
check('missing heartbeat', liveness.isBridgeAlive('/ap', NOW, reader(nil), 15), false)

-- Tolerate small clock skew, but not a timestamp far in the future.
check('small clock skew', liveness.isBridgeAlive('/ap', NOW, reader(tostring(NOW + 2)), 15), true)
check('far future timestamp', liveness.isBridgeAlive('/ap', NOW, reader(tostring(NOW + 3600)), 15), false)

-- Trailing newline from the bridge's write_text must be ignored.
check('timestamp with newline', liveness.isBridgeAlive('/ap', NOW, reader(tostring(NOW - 1) .. '\n'), 15), true)

if failures > 0 then
  print(('%d failure(s)'):format(failures))
  os.exit(1)
end
print('all liveness tests passed')
