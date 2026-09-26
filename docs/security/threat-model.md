# Step 4 threat model

The tenant is an organization; a team owns each virtual key. This protects provider
credits from unauthenticated traffic, not from an abusive holder of a valid key. Risk
ratings are qualitative for this early deployment.

| What could go wrong | Likely / bad | Prevention now | What remains |
|---|---|---|---|
| Stolen client key | Plausible / high | One key per team; revoke it; TLS in deployment | It works until revoked, and up to 30 s longer per replica; no per-key limits yet |
| Database leak | Unlikely / high | Store only HMAC hashes, keep pepper outside DB | DB plus pepper permits offline verification attempts; rotate and reissue if both leak |
| Log leak | Plausible / high | Never log bearer/provider secrets or prompt content; log verified public IDs only | Request metadata still reveals tenant activity; restrict log access |
| Brute-forcing keys | Unlikely with random keys / high | 256-bit random secret; generic 401 | No rate limiting until step 6; online attempts still consume resources |
| Learning which key IDs exist | Plausible / medium | Generic errors, null unverified ID in logs, dummy constant-time comparison | Database lookup and network variance may still differ; no strict timing guarantee |
| Revocation delay | Likely after urgent revocation / medium | 30-second bounded successful-key cache; TTL configurable | A revoked key can work for up to one TTL on **each** replica |
| Leaked provider key | Plausible / high | Resolve via secret store, mask in settings; never send to clients | Rotate it at the provider; an attacker can spend directly until revoked |
| Admin CLI misuse | Plausible / high | Offline CLI; no public admin API; database account access required | No audit log until step 8; protect shell history and operator access |
| Malicious base-URL override | Unlikely / high | Strict HTTP(S) URL validation, no embedded credentials/query/fragment | An operator with config access can still send provider keys to a hostile endpoint; lock down deployment config |
