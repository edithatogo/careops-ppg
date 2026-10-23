# Python 3.15 migration and qualification

## Objective and acceptance

The user's 24 October clarification supersedes the earlier mandatory-version rule:
prefer the latest suitable dependency/runtime, but another version is permitted
when needed. Keep the working Python 3.15.1 default for development, builds,
core tests and CI. Inventory every active use and any explicit compatibility
profile; verify actual repo-local interpreters and align constraints, hash locks,
dependencies and current instructions. Record the concrete reason and scope of
each exception, qualify its real behavior and preserve working latest-version
environments/in-flight operations. Do not introduce an implicit older default.

Reuse [merged runtime evidence](https://github.com/edithatogo/careops-ppg/pull/25);
test gaps and changed behavior. Require affected structure/privacy checks,
current-head qualification and post-merge main verification. Necessary scoped
version exceptions are not policy blockers; functionality/security gates remain.

## Preservation

Retain private history, uncommitted work, identities, bindings and active operations. Handover environments only at terminal points. No native, consent, licensing, email or external communication changes. Source CI does not establish native acceptance.

## Durable goal

Continue the existing full-repository goal with runtime and integration evidence
under the clarified dependency preference. Do not create a replacement goal or
shrink acceptance to completed work. Goal state belongs to the chat; no separate
per-module goal is claimed. Preserve the unfinished objective until all required
implementation and verification is complete.
