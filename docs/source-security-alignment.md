# Source-security alignment

This toolkit follows the parent security boundary while retaining independent
source checks and single-maintainer delivery. See [the security policy](../SECURITY.md).

| Boundary | Required behaviour |
|---|---|
| Source | Reusable code and fictional fixtures; no private working history or deployment records. |
| Local checks | Staged-index portable-content and Gitleaks checks; preserve existing hooks. |
| Inventory | Maintain an explicit tracked-path inventory once the privacy gate is adopted; an inventory addition is not content approval. |
| Documents and binaries | Exact-byte review is additional to, and cannot override, the existing portable-content format restrictions. |
| CI | Verify final-head privacy, full-history secrets, portable-content, source tests and actual package recovery. |
| Settings | Strict checks and admin enforcement; no force/delete; preserve enabled secret scanning and push protection. |
| Delivery | Scoped PR, every required check green, protected merge and merged-main verification before temporary branch/worktree cleanup. |
| Runtime | Source checks do not establish native operation, permissions, real authority or user acceptance. |

Use existing permissions without new premium services, paid enablement or AI
processing. Preserve stronger controls when host features differ between public
and private repositories. If a feature is unavailable, retain the exact limitation
and the supported local/CI route rather than silently weakening protection.

Shared-workflow references and the selected policy revision must resolve to the
same qualified source. Private parent visibility is not a reason to add a token
or copy credentials into this repository. Local source copies need exact commit
provenance, file hashes and original third-party licences, plus their own checks.

The privacy rollout and this policy change are separate source increments.
Neither claims that every legacy file was manually reviewed. Maintain explicit
review findings and preserve existing source and histories during remediation.

The portable source archive retains the committed security policy, privacy-check
sources and inherited licences, local hooks, scanner configuration and dependency
update configuration when present. Packaging preserves exact committed bytes;
it does not include private evidence or execute the hooks during extraction.
