-- KEYS: team theoretical arrival time. ARGV: RPM, burst requests, update.
-- Redis time is shared by replicas. A request books the next free slot.
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local rpm = tonumber(ARGV[1])
if rpm == 0 then return {1, -1, 0} end
local interval = 60 / rpm
local burst = tonumber(ARGV[2])
local tolerance = (burst - 1) * interval
local tat = math.max(now, tonumber(redis.call('GET', KEYS[1]) or '0'))
local allowed = now >= tat - tolerance
if allowed and ARGV[3] == '1' then
  tat = tat + interval
  redis.call('SET', KEYS[1], string.format('%.9f', tat), 'PX', math.max(1, math.ceil((tat - now) * 1000)))
end
local remaining = math.max(0, math.floor((now + tolerance - tat) / interval + 0.000001) + 1)
local retry = math.max(0, math.ceil(tat - tolerance - now))
return {allowed and 1 or 0, remaining, retry, math.floor(now * 1000000)}
