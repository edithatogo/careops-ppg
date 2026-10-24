# External catalogue execution context

Read `docs/external-catalogue-implementation.md`, the selected EC task and its
exact private manifest/receipt. Do not load unrelated archives or choose inputs
by globbing `.local`. Existing native/source/flow writers retain their objects.

Use the existing M365 SDK and saved connection; never copy credentials, reset
shared auth or introduce another authentication client. Native configuration and
source records remain private. `native.mjs` accepts a private binding and one
explicit mode; it does not select sources or grant write authority.

Use a repo-local Python 3.15.1 profile with the hash-locked external catalogue
dependencies. Verify its actual version and JSON Schema format checkers. The base
stdlib environment and another owner's running environment are not replaced.
Python preparation uses Beautiful Soup and JSON Schema; retain the small custom
identity, provenance, coverage, preservation and replay rules.

Sequence: pinned sources -> library/schema validation -> native difference ->
serial create-only persistence -> exact readback -> unchanged replay -> downloaded
export/reconstruction. Changed existing records and unknown mutation outcomes
stop that path for reconciliation. Never automatically retry a mutation, delete
an output, relax a pin or change human state to clear a failure.

Run affected unittest modules and Node tests. Existing fixture-only tests need no
tenant credentials; CI must not call `connect`, run a native flow or send mail.
No schedules, new recipients, permission changes or clinical applicability follow
from successful catalogue ingestion.
