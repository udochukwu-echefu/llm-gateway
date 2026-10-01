# ADR 0030: Bound demo traffic and remove idle storage activity

- **Status:** Accepted for local implementation; live sleep verification pending
- **Date:** 2026-10-01

## Context

The owner observed the scale-to-zero demo continuously resident after deployment.
InstaCloud's operate reference says regional settings may count outbound activity toward
idle. Infinite loopback traffic still generates outbound accounting, and the production
300-second budget reconciler collides with the five-minute idle window. ADR 0028's router-only
reasoning was insufficient; this decision supersedes its unbounded traffic/any-child-exit policy.

## Decision

Keep the three-request burst, then minute-scale jitter for one fixed, configurable window
(positive `DEMO_TRAFFIC_WINDOW_S`, default 600 seconds). Stop permanently afterward, including
on provider errors. A successful traffic exit is expected; all failed exits and server exits
still fail the appliance. No visitor-triggered restart or cron is added.

Fix the appliance reconciliation and usage idle intervals to 3600 seconds, not production's
300/1 seconds. Set demo batch size to one so receipts remain immediate rather than waiting
an hour. Empty queues never perform database I/O. Use NullPool only in demo-deployment mode
to close Postgres sockets after use; explicitly clamp Redis health checks and TCP keepalives
to off after URL parsing. Production defaults and URL-option behavior remain unchanged.

## Consequences

An unvisited demo has no continuing synthetic requests; its only autonomous storage job is
hourly reconciliation after its initial startup run. In-flight requests are cancelled at the
traffic deadline; cleanup/receipt finalization can drain afterward. Hourly budget repair is
acceptable for synthetic, fake-only accounting.
Per-receipt connections lose batching/pooling efficiency, deliberately limited to the demo.

Boots show fresh receipts. RAM-preserving suspension does not reboot a finished traffic
child; fresh-on-every-resume is not guaranteed. Verify status and zero memory in the live
region after deployment. No measured sleep or savings is claimed by offline/local gates.

## Alternatives considered

- Increase the flush interval without reducing batch size: delays “just now” receipts.
- Merely disable pre-ping: pre-ping is checkout-only and leaves idle socket keepalives possible.
- Slow the infinite traffic loop: still produces unnecessary data and can prevent idle.
- Keepalive tuning alone: more fragile than retaining no idle Postgres socket.
- Restart traffic on browsing/resume: adds a new trigger and conflicts with one bounded boot loop.
