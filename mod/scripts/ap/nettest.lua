local ffi = select('sandbox.bypass').ffi
ffi.cdef[[
typedef unsigned int uint32_t;
typedef unsigned short uint16_t;
int socket(int domain, int type, int protocol);
int connect(int sockfd, const void *addr, unsigned int addrlen);
ssize_t send(int sockfd, const void *buf, size_t len, int flags);
ssize_t recv(int sockfd, void *buf, size_t len, int flags);
int close(int fd);
unsigned int inet_addr(const char *cp);
uint16_t htons(uint16_t hostshort);
]]

local AF_INET = 2
local SOCK_STREAM = 1

local function test()
  local fd = ffi.C.socket(AF_INET, SOCK_STREAM, 0)
  print('socket fd: ' .. tostring(fd))
  if fd < 0 then return end

  -- sockaddr_in
  local addr = ffi.new('char[16]')
  -- zero
  for i=0,15 do addr[i]=0 end
  addr[0] = AF_INET  -- sin_family (little endian? actually first 2 bytes)
  -- sin_family is uint16 at offset 0
  ffi.cast('uint16_t*', addr)[0] = AF_INET
  -- port 38281
  ffi.cast('uint16_t*', addr)[1] = ffi.C.htons(38281)
  -- ip 127.0.0.1
  ffi.cast('uint32_t*', ffi.cast('char*', addr) + 4)[0] = ffi.C.inet_addr('127.0.0.1')

  local r = ffi.C.connect(fd, addr, 16)
  print('connect: ' .. tostring(r))
  if r == 0 then
    local msg = 'hello\n'
    ffi.C.send(fd, msg, #msg, 0)
    print('sent')
    local buf = ffi.new('char[256]')
    local n = ffi.C.recv(fd, buf, 256, 0)
    print('recv n: ' .. tostring(n))
    if n > 0 then
      print('recv: ' .. ffi.string(buf, n))
    end
  end
  ffi.C.close(fd)
end

local ok, err = pcall(test)
if not ok then print('NETTEST ERROR: ' .. tostring(err)) end

return { engineHandlers = { onInit = function() print('NETTEST INIT') end } }