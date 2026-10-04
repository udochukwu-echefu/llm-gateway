# Security policy

## Report a vulnerability

Please report suspected vulnerabilities privately through GitHub's
[Report a vulnerability](https://github.com/udochukwu-echefu/llm-gateway/security/advisories)
button on the repository's Advisories page. Include the affected component, impact,
reproduction steps and a minimal proof of concept. Do not post exploit details,
credentials or private data in a public issue.

Private vulnerability reporting is currently **disabled** (checked 2026-10-04).
The repository owner needs to enable it under **Settings → Security and quality →
Advanced Security → Private vulnerability reporting** before that button works.
Until then, open a public issue asking the maintainer for a private contact channel,
without including vulnerability details.

## Scope

Security reports about the gateway, private admin API, admin console and demo
appliance are in scope. The public demo is a synthetic, read-only tour. It contains
no real provider keys and sends its traffic only to a fake provider.

## Known accepted development dependency advisory

[`braces` stack-exhaustion denial of service](https://github.com/advisories/ghsa-vfj7-8cjw-p6xm)
is a high-severity advisory affecting `braces` 3.0.3. It reaches this project only
through the lint tool chain:

`eslint-config-next → @next/eslint-plugin-next → fast-glob → micromatch → braces`.

This dependency is used during development linting and is never included in the
production console build or appliance runtime. The risk is accepted for this
development-only path. As of 2026-10-04, 3.0.3 is the latest release and the
advisory lists no patched version; review the finding again when a fix is released.
