-- KEYS: team leases. ARGV: now, limit, ID, TTL seconds.
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local count = redis.call('ZCARD', KEYS[1])
if tonumber(ARGV[2]) > 0 and count >= tonumber(ARGV[2]) then
  return 0
end
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]) + tonumber(ARGV[4]), ARGV[3])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]) + 1)
return 1
