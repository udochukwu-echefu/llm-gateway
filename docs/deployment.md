# Production deployment checklist

- Run identical **stateless replicas** behind a load balancer; use shared Postgres and
  Redis. Start with one uvicorn worker per container: metrics registries are per-process.
- Apply `alembic upgrade head` as a reviewed one-off migration **before** starting the
  new replicas. Back up Postgres and rehearse rollback compatibility.
- Use `/healthz` for **liveness** (restart a dead process) and `/readyz` for **readiness**
  (stop routing to a process whose dependencies are unavailable). Redis fail-open can
  remain ready during an outage; choose fail mode according to cost/availability policy.
- Supply credentials through the existing secret store, not images or source control.
  Use unique peppers and cache-encryption keys; plan reissue/invalidation on rotation.
  Restrict database permissions, Redis access, backups and operator shell access.
- Terminate **TLS** at the edge. Prevent direct access around trusted proxies, and set
  trusted proxy hops correctly. Bound body sizes, upstream connections and team limits.
- Keep the admin API (8081) and metrics listener (9464) on private networks. Publish
  neither through the public model API. Use separate administrator credentials.
- Require Grafana authentication/authorization; local anonymous viewing is not a
  production default. Keep Prometheus, collectors and usage dashboards private.
- Alert on gateway availability/overhead, open circuits, Redis errors, receipt drops,
  losses and queue depth. Reconcile best-effort receipts with provider invoices.
- Validate reviewed catalogue prices, fallback data-sharing approvals and actual
  processing regions. A model's company headquarters is not a residency guarantee.
- Re-run capacity/soak tests on target hardware and resource limits. Laptop/fake-provider
  benchmarks are not a production sizing guarantee or a real-provider SLA.

## Kubernetes file secrets — UNVERIFIED

Kubernetes can mount secret volumes with `1777`-style **directory** permissions. The
file secret store rejects group/other access to the directory as well as resolved files;
`defaultMode: 0400` changes file permissions, not necessarily directory permissions.
This may therefore reject Kubernetes mounts even when the files are private. **Verify
in a real cluster before relying on the file backend there.** Symlink containment and
permission unit tests do not establish cluster behavior. Do not weaken the check merely
to make a deployment start; consider the environment backend or a securely staged private
directory only after reviewing the deployment's threat model.
