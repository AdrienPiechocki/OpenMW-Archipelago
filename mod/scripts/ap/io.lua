-- File I/O to the Archipelago bridge (unsandboxed build required).
--
-- The bridge publishes its messages in in.jsonl and reads checks from
-- out.jsonl. in.jsonl starts with a {"t":"sync","id":...} line: when
-- the bridge (re)connects it replaces the file with a new sync,
-- which lets the mod detect a new session without replaying the
-- old messages from another seed.
if _VERSION ~= 'Lua 5.1-DW' then error('Requires unsandboxed OpenMW build (LuaJIT)') end

local S = nil
local ok, res = pcall(function() return select('sandbox.bypass') end)
if ok and type(res) == 'table' then
  S = res
else
  error('Sandbox bypass refused: ' .. tostring(res))
end

-- Retrieve the io module from the bypass.
local io = _G.io or (S and S.io) or S
if type(io) ~= 'table' or type(io.open) ~= 'function' then
  if S then
    for _, v in pairs(S) do
      if type(v) == 'table' and type(v.open) == 'function' then
        io = v
        break
      end
    end
  end
end
if type(io) ~= 'table' or type(io.open) ~= 'function' then
  error('io module unavailable via sandbox bypass')
end
_G.io = io

local os = _G.os or (S and S.os)
local config = require('scripts.ap.config')
local M = {}

local function shq(s)
  return "'" .. tostring(s):gsub("'", "'\\''") .. "'"
end

function M.expand(path)
  if type(path) ~= 'string' then return path end
  if path:sub(1, 1) ~= '~' then return path end
  local home = nil
  if os and os.getenv then home = os.getenv('HOME') end
  if (not home or home == '') and io.popen then
    local f = io.popen('printf %s "$HOME"')
    if f then
      home = f:read('*l')
      f:close()
    end
  end
  if not home or home == '' then home = '/tmp' end
  if path == '~' then return home end
  return home .. path:sub(2)
end

local function ensureDir(dir)
  if io.popen then
    local f = io.popen('mkdir -p ' .. shq(dir))
    if f then f:close() end
  end
end

local DIR = nil
local offset = 0
local pendingChunk = ''
local syncLine = nil

function M.setDir(dir)
  DIR = M.expand(dir or config.data_dir)
  if DIR:sub(-1) ~= '/' then DIR = DIR .. '/' end
  ensureDir(DIR)
  offset = 0
  pendingChunk = ''
  syncLine = nil
  return DIR
end

function M.dir()
  if not DIR then M.setDir(config.data_dir) end
  return DIR
end

function M.send(line)
  local f = io.open(M.dir() .. 'out.jsonl', 'a')
  if not f then return false end
  f:write(line, '\n')
  f:flush()
  f:close()
  return true
end

-- Reads only the complete lines that arrived since the last call.
-- Handles the file being replaced by the bridge (new sync) and
-- partially written lines.
function M.poll()
  local f = io.open(M.dir() .. 'in.jsonl', 'r')
  if not f then return {} end

  f:seek('set', 0)
  local first = f:read('*l') or ''
  if first:sub(1, 11) == '{"t":"sync"' and first ~= syncLine then
    syncLine = first
    offset = 0
    pendingChunk = ''
  end

  local size = f:seek('end') or 0
  if size < offset then
    offset = 0
    pendingChunk = ''
  end

  local base = offset
  f:seek('set', base)
  local data = f:read('*a') or ''
  offset = base + #data
  f:close()

  local buf = pendingChunk .. data
  local out = {}
  local start = 1
  while true do
    local nl = buf:find('\n', start, true)
    if not nl then break end
    local line = buf:sub(start, nl - 1)
    if line ~= '' then out[#out + 1] = line end
    start = nl + 1
  end
  pendingChunk = buf:sub(start)
  return out
end

function M.exec(cmd)
  if io and io.popen then
    -- Launch without closing the pipe: keeping the pipe open lets the
    -- background process survive (otherwise OpenMW kills it on close).
    local f = io.popen(cmd)
    -- Do not close f: intentional file descriptor leak to keep the
    -- child process alive for the whole session.
    _G._ap_bridge_pipe = f
    return true
  end
  return false
end

function M.readFile(name)
  local f = io.open(M.dir() .. name, 'r')
  if not f then return nil end
  local d = f:read('*a')
  f:close()
  return d
end

function M.writeFile(name, content)
  local f = io.open(M.dir() .. name, 'w')
  if not f then return false end
  f:write(content)
  f:close()
  return true
end

function M.shquote(s)
  return shq(s)
end

return M
