# Python 3.15 migration and qualification

## Objective and acceptance

The latest supplied project instructions require Python 3.15 at the newest
qualified patch, currently 3.15.1, for every active repository use, including
optional compatibility runners. Explicitly select and verify repo-local
interpreters; align constraints, locks, dependencies, CI, containers and current
setup guidance. Qualify changes in isolation and preserve in-flight operations
until terminal handover. Older active runners remain migration work; historical
qualification does not make them current exceptions. Preserve historical/version
fixtures and report genuine blockers without downgrading or claiming completion.

Reuse unchanged merged runtime evidence, then qualify changed behavior and gaps.
Follow the current requirements checklist in [the plan](plan.md#current-user-requirements--plan-amendment-24-october-2026),
including structured-output preservation and targeted testing. Require affected
structure/privacy checks and exact-head hosted results. Native acceptance and
runtime migration remain separate from a planning PR's successful CI.

## Preservation

Retain private history, uncommitted work, identities, bindings and active operations. Handover environments only at terminal points. No native, consent, licensing, email or external communication changes. Source CI does not establish native acceptance.

## Durable goal

Continue the existing full-repository goal with runtime and integration evidence
under the clarified dependency preference. Do not create a replacement goal or
shrink acceptance to completed work. Goal state belongs to the chat; no separate
per-module goal is claimed. Preserve the unfinished objective until all required
implementation and verification is complete.
