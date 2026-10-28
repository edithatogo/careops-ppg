# Security and source publication policy

## Allowed material

This repository contains reusable project code, contracts, maintained templates
and explicitly fictional fixtures. It must not contain patient, employee,
applicant, clinical, workforce, operational, authentication, tenant-secret or
other confidential information. This applies regardless of repository visibility.
External documents, policy text and datasets require their own distribution rights;
the project code licence does not grant those rights.

Deployment bindings, native exports, run receipts, private evidence and real
correspondence belong in their authorised storage outside this Git history.
Port code through reviewed source changes; never merge private working history
into this repository. A file inventory proves tracked-path continuity, not that
its contents have been approved for publication.

## Required checks

Before a source change is pushed, inspect its staged content and proposed history
using the existing portable-content validator and pinned Gitleaks configuration.
Use the repository hooks where installed; CI remains required for other clones.
The privacy gate additionally maintains the tracked-file inventory and exact-byte
review requirements for documents and binaries when that gate is available on
the selected branch. Do not treat a passing scanner as exhaustive privacy review.
Do not weaken the existing portable-content restrictions to admit a file merely
because a separate checker accepts it.

Run affected tests using the verified repo-local Python version, then the relevant
package and clean-extraction checks at a coherent release milestone. Preserve
private artifacts and avoid publishing sensitive text through logs or reports.
Reports should identify a rule and path rather than reproduce matched content.

Use a scoped pull request and verify every required check on its final revision.
Retain strict freshness, administrator enforcement, no force pushes and no branch
deletions on the protected default branch. Re-read settings after a change;
installation, a workflow file or an earlier green revision is insufficient proof.
Keep Actions tokens read-only except for specifically qualified provenance or
security-result uploads. Never introduce cross-repository secrets to repair a
private shared-workflow dependency. Preserve exact qualified source provenance
and inherited licences if tooling must be copied into this repository.

## Reporting and response

Report suspected exposure privately to the repository owner through an existing
approved route. Never include sensitive evidence in a public issue, PR comment,
workflow log or artifact. This policy does not authorise sending a message.
Keep raw findings in authorised private storage. Credential rotation and sensitive
history removal require the relevant service owner and an approved incident
process; do not perform an ad-hoc force push or delete the retained evidence.

Repository visibility changes cannot recall earlier public clones, forks or
copies. Changing visibility also does not authorise storing confidential data.
Native deployment, substantive review, approval and operational acceptance remain
separate from source-security and package qualification.
