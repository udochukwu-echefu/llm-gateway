-- Conservative correction: never erase spend recorded while the SQL snapshot ran.
local current = redis.call('GET', KEYS[1])
local candidate = ARGV[1]
if not current or #candidate > #current or (#candidate == #current and candidate > current) then
  redis.call('SET', KEYS[1], candidate, 'EX', tonumber(ARGV[2]))
  return candidate
end
return current
