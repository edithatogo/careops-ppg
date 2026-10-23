# Guided portable CLI

Use repo-local Python 3.15.1 and a supported Node runtime. All commands require
explicit inputs; retain private plans, outputs, journals and bindings under
ignored `.local/`. Run `.venv/bin/python scripts/ppg_workbench.py --help` for the
fixed supported stages and plan format. It composes existing source preparation,
evidence lookup/excerpt/validation, case selection, package assembly/publication
and assurance commands. Plans cannot supply arbitrary executables or shell code.

For a guided operation, supply `--plan PLAN.json --state NEW_PRIVATE_JOURNAL.jsonl`.
Resume with the same plan and `--resume` only at a verified completed-stage
boundary. Changed outputs, incomplete writes, changed scope and failed reads
remain holds. Inspect native receipts separately from local completion.

Every native adapter requires an explicitly selected existing target, qualified
current account/client and source pins. Offline checks do not supply native
permission, premium entitlement, authority to send email or clinical approval.
Review the adapter's `--help` and source contract before any live operation.
