# ADR 0029: Observable demo failures and committed source deployment

- **Status:** Accepted
- **Date:** 2026-10-01

## Context

The first owner deployment exposed an incompatible cache-key alphabet and discarded
child diagnostics. The working deployment path used a staged source directory rather
than an owner-published registry image. Local setup also introduced agent tooling.

## Decision

Generate 32 cache-key bytes with standard base64. Test provisioning against the gateway's
startup validation (pepper and cache cipher) and the console's shared session schema.
Keep the stdlib appliance preflight aligned with standard base64.

Forward each child stdout/stderr line to the matching supervisor stream, with a child
name prefix. Two reader threads per process avoid pipe deadlocks. Mask `lgw_`/`lgwa_`
shapes and Postgres/Redis URL user information before printing; retain useful error text.
Drain readers before reporting exits or finishing shutdown, with a shared two-second
bound per process in case a descendant keeps a pipe open. Boot helpers use this same
filter; boot keys retain their separate anonymous pipe and never enter log output.

Use an owner-run staging helper that refuses dirty trees, archives HEAD into a temporary
directory, copies the archived appliance Dockerfile to the root, then runs InstaCloud's
build and deploy commands with port 3000. Leave the CLI's deployment URL visible and
remove the context on exit. Keep local `.insta/`, `.claude/` and `.codex/` ignored.

## Consequences

Failures retain diagnostic context, including the final lines before a crash. This filter
is defence in depth, not permission to log credentials or conversation content: arbitrary
secret formats, encoded secrets and multiline fragments are outside its pattern coverage.
Stdout/stderr each retain line order; their relative order is not guaranteed.

A source context represents committed code only and excludes ignored local secret files
and agent tooling. Owners must commit changes before deploying and select a compatible
previous commit for rollback. Deployment does not undo database migrations. The helper
uses the CLI's existing project binding from the repository, without uploading it.

## Alternatives considered

- Discard child logs: prevents diagnosis of real startup failures.
- Forward raw pipes: removes the extra credential filter.
- Read one pipe at a time: can deadlock if the other fills.
- Stage the working tree: can upload ignored secrets or unreviewed edits.
- Publish registry images manually: unnecessary for the source path the owner verified.
