# Technical assurance report

Use `.venv/bin/python scripts/ppg_assurance_report.py --help`. Supply retained
receipts/journals and an absent private output path. Successful, incomplete and
refused operations remain distinct; hashes and exact output identities bind the
reported evidence. A local stage cannot establish native readback or operational
acceptance. Human readiness, policy decisions and actual benefit measurements
remain unmeasured unless separately evidenced.

For a runnable first example, use the [operator walkthrough](guided-cli.md#first-run-an-offline-fictional-reference).
Repeat `--input` for each explicitly selected receipt; the report does not discover
omitted operations or inspect Microsoft services.

Single-step `command-exited` receipts are successful only with exit code 0.
Guided plans record their total stage count; every declared stage must have a
sequential started/completed pair before the whole plan is successful. A clean
intermediate stage boundary remains incomplete for the plan. Older plan journals
without a total count remain incomplete in this summary; inspect the original
plan and retained outputs rather than rewriting historical receipts.

Report generation exit 0 means the report was saved, including when it contains
refused or incomplete operations. Inspect the outcome counts and explicit
qualification flags. The report hashes its input receipts; current output-byte
verification belongs to guided resume or the owning native readback procedure.
