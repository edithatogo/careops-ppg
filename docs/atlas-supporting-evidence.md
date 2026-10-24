# Atlas supporting evidence on Python 3.15.1

The optional adapter uses an explicit repo-local Python 3.15.1 environment,
hash-locked dependencies and an exact clean Atlas source/contract pin. It makes
GET requests only through the qualified in-process TestClient. A hosted transport,
real medicine-to-policy identity mapping, original source-byte integrity and
clinical acceptance need their own qualification.

Use two existing API representations for their intended purpose:

- `/api/v1/evidence` supplies status-bearing assertion rows. An assertion with a
  positive or negative status cannot be relabelled unknown. Empty evidence gives
  no conclusion and cannot establish a negative finding.
- `/api/v1/comparisons` supplies conclusions for explicit concept, jurisdictions,
  dimensions and clocks. Its `unknown` and `not_covered` conclusions have null
  status codes and retain the actual availability, uncertainty and explanation.
  A missing combination remains absent; the adapter never fills it in.

This distinction resolves the earlier qualification failure without changing or
weakening the upstream EvidenceItem/OpenAPI contract. The older fixture changed
only an evidence row's state while retaining its status, which is an invalid
absence representation. Keep that failed trial as historical evidence.

Both routes refuse private/extra query fields, unqualified origins, redirects,
denials, oversized responses, schema/version drift, incomplete pagination,
mismatched identities/clocks and contradictory pinned provenance. Comparisons
also require requested jurisdiction/dimension membership and unique conclusion
cells. Raw response bytes remain unchanged in separately named supporting files;
receipts bind their hashes, source/contract pin and explicit local case/revision.
Source hashes in a response remain unverified until original bytes are retrieved.

The qualification invokes the real API against the maintained fictional Atlas
fixture. It proves actual unknown/not-covered conclusions and absence without
coverage, invalid-status refusal, query/response guards, ZIP member hashes/CRCs,
unchanged replay, edited-output refusal, a new revision preserving that edit and
an unchanged fixture database. The four supporting files remain distinct inside
the existing package assembler; no policy approval, send, source/case write or
new service is supplied.

Follow the [current setup commands](../README.md#run-locally). Both `.venv` and
`.venv-atlas` require the same Python pin. Older runtime trials can remain in
immutable historical evidence; no active CI/helper selects Python 3.14.
