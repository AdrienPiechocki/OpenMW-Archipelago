-- Offline test of the filler / trap items of items.lua (mocked openmw.* modules).
-- Usage (from the mod folder, any Lua 5.3/5.4):  lua ../tools/test_filler_traps.lua
package.path = './?.lua;' .. package.path
print = function() end
local function out(...) io.write(string.format(...), '\n') end
local created, teleported, attacked, unknown = {}, 0, 0, { ['bad_record'] = true }
local inv = {}
package.preload['openmw.types'] = function() return { Actor = { inventory = function() return inv end }, Player = {} } end
package.preload['openmw.util'] = function() return { vector3 = function(x, y, z) return { x = x, y = y, z = z } end } end
package.preload['openmw.world'] = function()
  return { createObject = function(rec, n)
    if unknown[rec] then error('unknown record') end
    created[#created + 1] = { rec = rec, n = n }
    return { moveInto = function() end, teleport = function() teleported = teleported + 1 end,
             sendEvent = function(_, ev) if ev == 'AP_Attack' then attacked = attacked + 1 end end }
  end }
end
local items = dofile('scripts/ap/items.lua')
local player = { cell = 'c', position = { x = 0, y = 0, z = 0 }, rotation = { apply = function(_, v) return v end } }
-- vector add for position + offset
local mt = { __add = function(a, b) return a end }
setmetatable(player.position, mt)
local failures = 0
local function check(name, got, want)
  if got ~= want then failures = failures + 1; out('FAIL %s: got %s, want %s', name, tostring(got), tostring(want))
  else out('ok   %s', name) end
end

for id = 7701001, 7701016 do
  created = {}
  check('filler ' .. id .. ' handled', items.apply(player, id, 1), true)
  check('filler ' .. id .. ' creates one stack', #created, 1)
end
created = {}; items.apply(player, 7701005, 1)
check('Gold (250) gives 250 gold', created[1].rec .. ':' .. created[1].n, 'gold_001:250')

for id, n in pairs({ [7701202] = 1, [7701204] = 1, [7701205] = 1, [7701206] = 3 }) do
  created, teleported, attacked = {}, 0, 0
  check('summon ' .. id .. ' handled', items.apply(player, id, 1), true)
  check('summon ' .. id .. ' spawns ' .. n, #created, n)
  check('summon ' .. id .. ' hostile', attacked, n)
end
local ok, eff = items.apply(player, 7701207, 1)
check('drain fatigue effect', eff and eff.type .. ':' .. eff.stat, 'drain:fatigue')
ok, eff = items.apply(player, 7701208, 1)
check('drain magicka effect', eff and eff.type .. ':' .. eff.stat, 'drain:magicka')
ok, eff = items.apply(player, 7701200, 1)
check('damage trap unchanged', eff and eff.type, 'damage')
out(failures == 0 and 'all filler / trap Lua tests passed' or (failures .. ' FAILED'))
