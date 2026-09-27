-- KEYS: month spend, alert marker. ARGV: limit picos, delta picos, threshold picos, TTL.
local function at_least(a, b)
  return #a > #b or (#a == #b and a >= b)
end
local spent = redis.call('GET', KEYS[1]) or '0'
local allowed = ARGV[1] == '0' or not at_least(spent, ARGV[1])
local alert = 0
if tonumber(ARGV[2]) > 0 then
  redis.call('INCRBY', KEYS[1], ARGV[2])
  spent = redis.call('GET', KEYS[1])
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
  if ARGV[3] ~= '0' and at_least(spent, ARGV[3]) then
    if redis.call('SET', KEYS[2], '1', 'NX', 'EX', tonumber(ARGV[4])) then alert = 1 end
  end
end
return {allowed and 1 or 0, spent, alert}
