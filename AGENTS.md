# Project guidance

Maintain a portable, organisation-neutral PPG toolkit. Commit reusable source,
contracts and fictional fixtures only. Keep operational records, real policy
content, personal details, tenant/resource bindings and receipts outside Git.
Do not import another project's Git history or delivery records.

Prefer SharePoint structured document generation for maintained structured outputs.
Qualify the exact route and actual output before replacing a working fallback.
Preserve edits, source/template identity, output revisions and issued history.
Technical generation never supplies review, approval or permission to circulate.

Preserve persistent document identity, raw provenance and local review work.
Use serial conditional writes and readback before committing checkpoints.
Unknown aliases and missing rows are exceptions, never automatic identity decisions
or retirement. Native adapters require their own target-specific qualification.

Run affected tests, the content check and Gitleaks before pushing. Do not weaken
secret detection or suppress content findings to publish operational material.

For modular source delivery, read `conductor/suite-delivery.md` and the ordered
queue in `.careops/module.json`. Preserve the portable boundaries above, qualified
CI and current native/file owners. Source guidance does not authorise deployment.

## Required Python execution

All active Python development, build, test, automation and CI execution uses
Python3.15, currently exact patch3.15.1. Use an explicit repo-local interpreter,
verify its version, and align constraints, locks and current setup instructions.
Older runners are not compatibility defaults; preserve only historical evidence
and intentional synthetic version tests. Do not replace a running environment.

PyYAML6.0.3 currently has no Linux CPython3.15 wheel. CI tool qualification permits
its hash-verified source distribution explicitly; other tool dependencies retain
binary-only installation. Keep the Python3.15 interpreter and test actual builds.

## Targeted test execution

Follow the [shared targeted-testing policy](https://github.com/edithatogo/careops/blob/main/docs/targeted-testing.md).
During edits, select exact affected files/nodes or native runner checks and reuse
unchanged evidence. Use an explicitly selected repo-local Python3.15.1 via
REPO_PYTHON where applicable. Do not rerun unchanged whole suites during each edit.
Run broader tests for shared fixtures, schemas, dependencies or uncertain impact;
retain full coverage/security/integration and release gates at coherent milestones.

For pytest, preserve cacheprovider per worktree/environment: --lf together with
--last-failed-no-failures=none never silently runs all tests; empty means no tests
verified. --ff still runs all selected tests; --sw is local debugging only. Do not
set selection flags globally or present partial coverage as full coverage.
Default to no automatic retries. skip/skipif requires a real capability condition
and reason; xfail needs a known issue/reason and strict=True. Neither is for speed.
Never retry native mutations, sends or real external effects through test plugins.
Difftest0.3.0 failed actual3.15.1 qualification (PyO3 maximum3.14); do not install
it with a compatibility override or downgrade Python. Rerunfailures16.7 is opt-in
for bounded, diagnosed fictional/read-only transient cases with first failure
visible; it must not turn flaky outcomes into clean acceptance.

Existing runner example (select the actual changed case, not this example blindly):

```sh
"$REPO_PYTHON" -m unittest discover -s tests -p test_consultation.py -v
```
