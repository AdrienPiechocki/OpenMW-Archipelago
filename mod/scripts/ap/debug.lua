local ok, S = pcall(function() return select('sandbox.bypass') end)
print('BYPASS: ' .. tostring(ok) .. ' ' .. tostring(type(S)))
local ffi = nil
if type(S) == 'table' then
  for k,v in pairs(S) do
    if type(v) == 'table' and type(v.cdef) == 'function' then ffi = v; print('FFI found in bypass key: ' .. k) end
  end
end
if not ffi then
  local ok2, r = pcall(require, 'ffi')
  if ok2 then ffi = r; print('FFI found via require') end
end
print('FFI: ' .. tostring(ffi))
if ffi then
  print('FFI cdef type: ' .. type(ffi.cdef))
end
-- list S keys
if type(S)=='table' then
  local ks={}
  for k in pairs(S) do ks[#ks+1]=k end
  table.sort(ks)
  print('S keys: ' .. table.concat(ks, ', '))
end
return { engineHandlers = { onInit = function() print('DEBUG INIT') end } }