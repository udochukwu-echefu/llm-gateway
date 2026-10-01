# Gateway threat model (through step 14 providers)

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
| Admin CLI misuse | Plausible / high | Database account access required; changes share the audited service | Protect shell history and operator access |
| Stolen admin key | Plausible / high | Distinct 256-bit admin keys stored as HMAC hashes; private listener; scoped org role and audit actor | The key works until revoked/expired; restrict storage, rotate after theft and protect the private network |
| Idempotency replay or database leak reveals a client key | Plausible / high | The replay row stores only resource IDs and non-secret metadata; only the first create response contains the key; expired rows are purged on keyed writes | A lost first response requires revoking that key and issuing another; protect the live HTTP response and admin credential |
| Admin IDOR (changing an org ID in a URL) | Plausible / high | Every scoped operation checks the verified key's organization UUID; other-org access returns 404; complete route-role test matrix | Incorrect future queries still need review; timing is not a formal existence-hiding guarantee |
| Admin endpoint exposed on public port | Unlikely / high | Separate FastAPI app and loopback listener; public app has no admin routes; route isolation tests | Deployment proxy or container port publication can expose the private listener; restrict network and add TLS |
| Dashboard database credential stolen | Plausible / medium | Dedicated read-only role reads organization, team and usage tables plus a budget-only view; password supplied outside repo | It exposes spending patterns until rotated; protect Grafana config, connection and backups |
| Malicious base-URL override | Unlikely / high | Strict HTTP(S) URL validation, no embedded credentials/query/fragment | An operator with config access can still send provider keys to a hostile endpoint; lock down deployment config |
| Tampered catalogue | Plausible / high | Reviewed git changes; strict startup validation of prices and model IDs | A compromised reviewer or deployment can still approve a wrong price; compare with provider invoices |
| Trial costs mistaken for free usage | Plausible / high | NVIDIA has explicit unpriced catalogue periods, NULL-cost receipts and separate CLI counts; never fabricate zero prices | USD budgets cannot account for unknown trial credit consumption; review paid endpoint rates before production |
| Budget bypass via unpriced models | Plausible / high | Operators use model policy to allow only reviewed priced models for budget-limited teams; do not allow `nvidia/*` | Budgets cannot limit an unpriced model because its cost is unknown; RPM, TPM and concurrency limits are not money caps |
| NVIDIA trial receives confidential data or production traffic | Plausible / high | Trial-only README/ADR warning; no automatic alias/fallback traffic; existing model/region policies | Trial terms prohibit production and confidential/sensitive inputs; default PII actions do not enforce the whole contract; use synthetic nonsensitive data |
| Queue flooding or writer outage | Plausible / high | Bounded non-blocking queue, retry, error logs and drop counts | Lost records on overflow, failed batches, shutdown timeout or abrupt kill; monitor and reconcile bills |
| Usage records disclose business activity | Plausible / medium | Store only IDs, model, counts, cost and timings; never content or vectors | Model and spending patterns remain sensitive; restrict Postgres/report access and retention |
| Retry storm amplifies a provider outage | Plausible / high | Bounded retries, full jitter, 20% per-provider rolling retry budget, one overall deadline and local breakers | Replicas learn independently; restarting loses history; even a retryable 5xx might already have been billed |
| Queued NVIDIA job outlives the client or is submitted twice | Plausible / medium | Nonstreaming Kimi polls one accepted job on the same authenticated host; UUID-only paths; one total deadline; local disconnect cancellation; poll/result-read failures prohibit inference retries | No remote cancellation API is documented; unknown queued GLM/streaming modes return retryable errors and bounded resubmissions may create extra jobs; usage without a result remains unknown |
| Fallback discloses prompts to an unapproved company | Plausible / high | Empty-by-default reviewed alternatives, no transitive expansion, capability checks, opt-out and transparent model; org/team model and residency policies filter every target | Reviewers must still assess contracts, subprocessors and deployment endpoints |
| Client forces a cheaper or weaker fallback | Plausible / medium | Client can only disable fallback; destination and order come exclusively from the reviewed catalogue, never a client-selected header | A client can induce load or request an explicitly catalogued model; org/team model access policies now limit concrete targets |
| Exposed metrics | Plausible / high | Separate loopback metrics socket; no public API route; no published metrics port in local profile | Traffic, models and spend remain sensitive; restrict scrape-network and Grafana access in production |
| Audit tampering | Plausible / high | UPDATE/DELETE trigger; serialized same-transaction hash chain; verification CLI | Owner can disable triggers, rewrite the whole chain or remove the tail; external trusted checkpoints/backups are required to detect that |
| Spoofed audit actor | Plausible / medium | HTTP mutations use the verified `admin:<key_id>` identity; CLI records explicit operator label or OS user plus hostname | Stolen admin keys impersonate their holder; CLI labels remain claims; SSO is out of scope |
| Trace IDs or content leaking to providers | Plausible / medium | Manual metadata-only spans; no headers, content or exception events; outgoing trace propagation defaults off | Opt-in propagation shares correlation IDs; protect collector/UI access and retention; incoming parent context can influence sampling |
| Alias hides a forbidden destination | Plausible / high | Resolve aliases and check concrete model permissions and region before budget/rate admission; provider_options cannot override model | Catalogue reviewers must verify actual endpoint processing commitments |
| Weighted trial selects a forbidden provider | Plausible / high | Remove forbidden targets before the draw and rescale remaining weights; all forbidden returns 403 | Actual trial proportions differ by each team's permissions and configured providers |
| Outage fallback bypasses team access | Plausible / high | Filter every direct fallback by org intersection team; an open primary with no permitted fallback returns 503 without contacting the forbidden provider | Approved providers still require contractual and residency review |
| Policy restriction delayed by cache | Expected / medium | Both policies share the bounded verified-key TTL; cache hits never extend it; CLI states the delay | Restrictions take up to the configured TTL per replica, normally 30 seconds |
| Cross-team cache leakage | Plausible / high | Team UUID in key; AES-GCM ciphertext authenticated against the full key; copied values fail authentication | Operators with both Redis and the encryption secret can read data; restrict both |
| Cache poisoning | Plausible / high | Only complete successful requested-model responses are stored; invalid ciphertext misses | An attacker controlling both Redis and the encryption key can forge an entry |
| Redis snapshot exposes responses | Plausible / high | Every cached value is encrypted with a fresh nonce and secret-store AES-256-GCM key | Key loss makes entries unreadable; metadata and request timing remain visible |
| Stale answers after model change | Expected / medium | Reviewed catalogue version in fingerprint, TTL at most seven days, audited purge | Unannounced upstream changes may remain cached until TTL/purge |
| Cache timing reveals a hit | Expected / low | Team-only keys; only authenticated team keys can observe a team's entries | Team members can infer another request within their own team from speed; acceptable within that trust boundary; no cross-team timing probe |
| PII reaches a provider | Plausible / high | Input patterns scan every message role, tool arguments and embedding strings before cache/admission; cards/IBANs redact by default, configurable stricter PII actions | Other PII defaults allow; names, addresses, files, images, audio, integer token inputs and contextual identification remain outside deterministic detection |
| Secrets pasted into prompts | Plausible / high | Known API key prefixes (including lgw_) and full private-key blocks block by default; values never enter errors or telemetry | Unknown formats, incomplete blocks and obfuscated secrets may evade matching; rotate a leaked credential regardless |
| Preserved reasoning bypasses inspection | Plausible / high | Typed assistant reasoning_content is scanned/redacted before Z.ai/NVIDIA forwarding and included in cache fingerprints | Encoded or obfuscated text and contextual identification remain outside deterministic detection; reasoning is sensitive content, not metadata |
| Obfuscated PII bypasses patterns | Likely / high | Tool argument JSON escapes are decoded; adversarial regex tests bound known attack cases | Base64, lookalikes, split values and “at/dot” spellings are not reliably recognized; no claim of complete DLP |
| User placeholder injection | Plausible / medium | Reserve input placeholder literals, request-only mapping, non-recursive restore, separate output-mask namespace | A model can guess or misuse an assigned code within the same request; pseudonymised context can still identify someone |
| Residency bypass through routing | Plausible / high | Concrete model-policy check also enforces org intersection team regions for direct/alias/weighted/fallback routes and model listing | Cached identity delays changes by TTL; catalogue or base-URL administrators can misdeclare deployment location; policies are not legal certification |
| Sensitive restore mapping in memory | Plausible / high | Per-request lifetime only, cleared on finalization; never cached, traced, logged or persisted | Python strings are not securely erased; process compromise, debugging or crash dumps can disclose them |
| Model generates new secrets/PII | Plausible / high | Nonstreaming output masks or blocks before cache/restore; stream findings counted at completion/close | Streams are detect-only because sent bytes cannot be recalled; incomplete/obfuscated patterns can escape |
| Stream detection memory growth | Plausible / medium | Delivery hold-back bounded by placeholder length; detection copies released at close, including disconnect | End-of-stream detection retains generated text per channel in memory; very long outputs increase memory use; incremental detectors remain future work |
| Restored originals contaminate cache | Plausible / high | Cache key uses redacted input; stored output precedes restore; each hit restores using its own mapping; no-leak test inspects decrypted entries | Allowed, unredacted PII and other confidential output can still be cached encrypted; policy changes require appropriate retention/purge decisions |
| Load test calls a real provider | Unlikely / high | Runner ignores `.env` and inherited gateway settings; explicit fake base URLs; fake provider and replicas have only an internal Docker network | Do not manually replace benchmark URLs/networks with production configuration |
| Benchmark credentials leak into reports/builds | Plausible / medium | CLI output captured; private 0700 directory and 0600 files; git and Docker context ignore state; only synthetic metric output is collected | Docker administrators can inspect generated container credentials; protect the local machine and do not archive `.state` |
| Profiling permissions reused in production | Plausible / high | Optional separate py-spy image joins only the fake-key replica's PID namespace; network disabled; no locals captured; normal gateways get no extra capabilities | SYS_PTRACE/disabled seccomp are debugging privileges, never a production deployment default |

## Admin console boundary (step 13a)

| Threat | Prevention | Residual risk |
|---|---|---|
| Session theft | Encrypted __Host cookie; Secure, httpOnly, Strict; 8 h absolute / 30 min idle; key revocation checked at the API | Stolen ciphertext is replayable; stateless logout cannot revoke stolen copies; revoke the admin key |
| Admin key in browser responses | server-only BFF client and session; explicit identity DTO; redact credential-shaped strings/errors; scan all browser responses in e2e | Server/process compromise can expose keys; never enable body logging or browser traces for real sessions |
| XSS | React text escaping; fresh nonce CSP; no unsafe-inline scripts, external fonts or third-party scripts; no browser-stored admin key | Same-origin injected code could still invoke actions during a session; CSP is layered protection |
| CSRF | SameSite=Strict plus exact configured Origin on login, logout and every mutation; reject absent Origin | Deployment must configure the public origin correctly; route handlers do not inherit Server Action checks |
| Clickjacking | CSP frame-ancestors 'none' | Deployment proxy must preserve response headers |
| UI-only authorization / org tampering | Gateway verifies key role and organization on each API operation; BFF preserves scope, allowed routes and credential; other-org 404 tests | Future endpoint/BFF changes require matrix and browser isolation tests |
| Tenant secret revealed again | Only first creation response contains secret; dialog state discarded on close/unmount; no reveal control/storage; no-store responses | User must secure their clipboard/secret store; lost first response requires revoke/reissue |
| Cached authenticated pages | Dynamic rendering, no-store pages/BFF responses, full navigation on authentication changes | Browser/device compromise or screenshots can expose public administrative metadata |

The console's login-failure throttle is per socket-derived client IP, in memory on
each replica: ten failures in a fixed minute, bounded to 10,000 entries. NAT clients
share a quota; replicas/restarts do not share or preserve counters. Authenticated
requests bypass it. The admin API verifies valid keys before its separate failure
counter to prevent the BFF's shared IP from becoming an administrator-wide lockout.

The Node entry points overwrite the internal client-address header before Next
handles requests. Forwarded addresses are ignored unless validated trusted proxy
hops are configured (default zero). Behind a balancer, restrict direct origin access
and require the trusted chain to append real peers. Misconfigured trust lets clients
claim identities, while no trust behind a balancer shares its quota across callers.
Startup validation runs before Next starts for both local and Docker entry points;
a missing or short secret stops only the console container with exit 1 and a clear error.
Database-only compose commands remain usable without the console secret.

## Safe policies and operational overview (step 13b)

| Threat | Prevention | Residual risk |
|---|---|---|
| Policy tampering / cross-org URL changes | Gateway authorization on every read/write; complete role matrix including conditional writes; BFF enums, bounded lists and pattern/version schemas | A stolen authorized admin key can change its scope's policies; protect the private listener and key |
| Lost updates / replaying an old version | Owner-row locks, revision-bearing hash, conditional check + mutation + audit in one transaction; CLI advances versions too; console always supplies If-Match | Authorized unconditional API/CLI writes remain possible by design; inherited policy changes are outside this level's version |
| Accidental deny-all or weakened guardrail | Separate inherit/deny-all choices; pre-save change summary; dangerous-change and named removal confirmations; retain draft on conflict | UI safeguards cannot stop a crafted authorized request; policy changes take up to key-cache TTL |
| Purge abuse / availability impact | Exact typed org/team name in UI; API scope checks and successful-purge audit; Redis errors map to 503 | Authorized repeated purges consume Redis work; UI confirmation is not API authorization or a rate limiter; concurrent writers may refill |
| UI-only checks mistaken for enforcement | Public API intersection/guardrail floors remain authoritative; browser consumes effective results; BFF never expands scope | XSS may perform same-origin actions with the current session; retain CSP, Origin and session defenses |
| Overview hides unknown accounting or another tenant | API-scoped org inventory; complete pagination; exact decimal sums; explicit unpriced and partial-token labels; org-scope e2e test | Receipts are best effort, requests count attempts, snapshots may change while multiple pages load; overview is not an invoice |
| Demo seeder used accidentally | GATEWAY_DEMO_SEED=1 opt-in; clearly named synthetic org; refuse pre-existing non-demo org; deterministic IDs and seed lock; print only names/IDs | An operator can deliberately opt into the wrong database; application secrets are discarded; rotated demo admin secrets stay in a mode-0600 ignored local file; use a disposable database |

## Provider residency (step 14)

Step 14 residency values are `us`, `eu`, `cn`, `sg`, `global`, `unknown`.
`sg` reflects Z.ai's API DPA statement that Customer Data is **generally** processed
in Singapore; NVIDIA's Kimi page states Global. Neither label certifies physical
processing location on each call. Changing a base URL requires source/region review.
The admin identity and catalogue endpoints expose the authoritative region list to either admin
role, but no tenant policies or credentials beyond its existing identity metadata.

## Console completeness (step 15)

| Threat | Prevention | Residual risk |
|---|---|---|
| Spreadsheet formula injection | Server CSV generator quotes cells and prefixes =, +, -, @ after optional whitespace/control characters; unit and break tests | Spreadsheet tools may interpret other exotic formats; exports still contain sensitive metadata |
| Settings disclosure | Platform-only route built from explicit fields; booleans for key presence, host-only URLs; negative secret and full-dump mutation tests | Authorized operators can see deployment topology; server compromise still exposes environment secrets |
| Cross-org global search | SQL org predicate before name/ID matching and limit; unchanged credential forwarding; role-matrix, HTTP and browser tests | Authorized platform admins intentionally search all orgs; client filtering alone is insufficient |
| Request metadata IDOR | Scoped list and detail queries, strict filters, tied-timestamp cursor, isolation mutation test | Receipts expose operational activity; retain private-network/database controls |
| Demo seeding a production DB | Opt-in plus verification of the actual bound database host before I/O; only localhost/127.0.0.1/::1/postgres; mode-0600 ignored rotated demo keys | A local tunnel or deliberately misnamed compose service can reach a remote database; operators must keep the demo on a disposable local stack |
