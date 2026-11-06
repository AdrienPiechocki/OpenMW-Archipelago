local S = select('sandbox.bypass')
local ffi = S.ffi
ffi.cdef[[
void *curl_easy_init(void);
int curl_easy_setopt(void *curl, int option, ...);
int curl_easy_perform(void *curl);
void curl_easy_cleanup(void *curl);
char *curl_easy_strerror(int code);
size_t curl_ws_send(void *curl, const void *buffer, size_t buflen, size_t *sent, unsigned int frags);
size_t curl_ws_recv(void *curl, void *buffer, size_t buflen, size_t *recv, struct curl_ws_frame **meta);
]]

local CURLOPT_URL = 10002
local CURLOPT_CONNECT_ONLY = 141
local CURLOPT_WS_OPTIONS = 320
local CURLOPT_TIMEOUT = 13
local CURLOPT_NOSIGNAL = 99
local CURLWS_TEXT = 1

local libcurl = ffi.load('libcurl.so.4')
local curl = libcurl.curl_easy_init()
print('curl handle: ' .. tostring(curl))

local url = 'wss://archipelago.gg:59470'
libcurl.curl_easy_setopt(curl, CURLOPT_URL, url)
libcurl.curl_easy_setopt(curl, CURLOPT_CONNECT_ONLY, 2) -- 2 = websocket
libcurl.curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10)
libcurl.curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1)
print('before perform')
local okp, r = pcall(function() return libcurl.curl_easy_perform(curl) end)
print('perform pcall: ' .. tostring(okp) .. ' ' .. tostring(r))
if okp then print('perform: ' .. tostring(r) .. ' ' .. ffi.string(libcurl.curl_easy_strerror(r))) end

if r == 0 then
  -- send a websocket text frame
  local msg = '{"cmd":"Connect","game":"Morrowind OpenMW","name":"TestMW","password":"","uuid":"123","version":{"major":0,"minor":6,"build":8,"class":"Version"},"items_handling":7,"tags":[]}'
  local sent = ffi.new('size_t[1]')
  local sr = libcurl.curl_ws_send(curl, msg, #msg, sent, 0, CURLWS_TEXT)
  print('ws_send: ' .. tostring(sr) .. ' sent=' .. tostring(sent[0]))
  -- recv
  local buf = ffi.new('char[8192]')
  local recv = ffi.new('size_t[1]')
  local meta = ffi.new('struct curl_ws_frame *[1]')
  local rr = libcurl.curl_ws_recv(curl, buf, 8192, recv, meta)
  print('ws_recv: ' .. tostring(rr) .. ' recv=' .. tostring(recv[0]))
  if recv[0] > 0 then
    print('DATA: ' .. ffi.string(buf, recv[0]))
  end
end

libcurl.curl_easy_cleanup(curl)
print('CURLTEST DONE')

return { engineHandlers = { onInit = function() print('CURLTEST INIT') end } }