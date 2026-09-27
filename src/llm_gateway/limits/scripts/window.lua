-- KEYS: current and previous window. ARGV: now, limit, delta, update (0 = check only).
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local delta = tonumber(ARGV[3])
local width = 60
local offset = now % width
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local previous = tonumber(redis.call('GET', KEYS[2]) or '0')
local used = current + previous * (1 - offset / width)
local allowed = limit == 0 or used < limit
if allowed and ARGV[4] == '1' and delta > 0 then
  current = redis.call('INCRBY', KEYS[1], delta)
  redis.call('EXPIRE', KEYS[1], 120)
  used = current + previous * (1 - offset / width)
end
local remaining = limit == 0 and -1 or math.max(0, math.ceil(limit - used))
local reset = math.ceil(width - offset)
if not allowed and current < limit and previous > 0 then
  reset = math.max(1, math.floor((used - limit) * width / previous) + 1)
elseif not allowed and current >= limit then
  reset = reset + math.floor((current - limit) * width / current) + 1
end
return {allowed and 1 or 0, remaining, reset}
