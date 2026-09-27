-- Extend only an existing lease; a released/crashed holder cannot recreate it.
if redis.call('ZADD', KEYS[1], 'XX', 'CH', tonumber(ARGV[1]) + tonumber(ARGV[3]), ARGV[2]) == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]) + 1)
  return 1
end
return 0
