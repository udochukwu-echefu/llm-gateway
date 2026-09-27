# Step 4 threat model

The tenant is an organization; a team owns each virtual key. This protects provider
credits from unauthenticated traffic, not from an abusive holder of a valid key. Risk
ratings are qualitative for this early deployment.

| What could go wrong | Likely / bad | Prevention now | What remains |
|---|---|---|---|
| Stolen client key | Plausible / high | One key per team; revoke it; TLS in deployment | It works until revoked, and up to 30 s longer per replica; no per-key limits yet |
| Database leak | Unlikely / high | Store only HMAC hashes, keep pepper outside DB | DB plus pepper permits offline verification attempts; rotate and reissue if both leak |
| Log leak | Plausible / high | Never log bearer/provider secrets or prompt content; log verified public IDs only | Request metadata still reveals tenant activity; restrict log access |
| Brute-forcing keys | Unlikely with random keys / high | 256-bit random secret; generic 401; failed authentications limited per IP before key lookup | Attackers with many IPs can spread attempts; Redis fail-open admits during outages |
| Forged forwarded client IP | Plausible / medium | Ignore X-Forwarded-For unless trusted proxy hops are configured; otherwise use socket IP | Only deploy with the correct proxy hop count and block direct access to the gateway |
| Redis outage | Plausible / high | 50 ms timeout, rate-limited error log, choose fail-open or fail-closed; background spend reconciliation heals persisted budget drift within the configured interval | Open admits uncounted requests until reconciliation; queued or lost receipts may delay or prevent exact spend recovery; closed blocks legitimate traffic |
| Noisy team starving others | Plausible / medium | Per-team concurrency leases cap simultaneous calls and self-heal after crashes | Shared provider pool can still be busy; configure appropriate team limits |
| Learning which key IDs exist | Plausible / medium | Generic errors, null unverified ID in logs, dummy constant-time comparison | Database lookup and network variance may still differ; no strict timing guarantee |
| Revocation delay | Likely after urgent revocation / medium | 30-second bounded successful-key cache; hits never extend the TTL | Revocation takes effect within TTL seconds of revocation, even for a key in continuous use, on **each** replica |
| Leaked provider key | Plausible / high | Resolve via secret store, mask in settings; never send to clients | Rotate it at the provider; an attacker can spend directly until revoked |
| Admin CLI misuse | Plausible / high | Offline CLI; no public admin API; database account access required | No audit log until step 8; protect shell history and operator access |
| Malicious base-URL override | Unlikely / high | Strict HTTP(S) URL validation, no embedded credentials/query/fragment | An operator with config access can still send provider keys to a hostile endpoint; lock down deployment config |
| Tampered catalogue | Plausible / high | Reviewed git changes; strict startup validation of prices and model IDs | A compromised reviewer or deployment can still approve a wrong price; compare with provider invoices |
| Queue flooding or writer outage | Plausible / high | Bounded non-blocking queue, retry, error logs and drop counts | Lost records on overflow, failed batches, shutdown timeout or abrupt kill; monitor and reconcile bills |
| Usage records disclose business activity | Plausible / medium | Store only IDs, model, counts, cost and timings; never content or vectors | Model and spending patterns remain sensitive; restrict Postgres/report access and retention |
