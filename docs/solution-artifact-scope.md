# PPG solution and installation scope

PPG is the overarching product. A source-collection module is one part of it, not
an installer for every workbench feature.

| Artefact | Current delivery boundary |
|---|---|
| Qualified source collectors | Fourteen working collectors covering sixteen channels: nine RSS, three newsletters, one internal structured source and one collector for three hospital datasets |
| Prepared blocked collectors | Commission newsletter guard and METEOR preparation remain stopped; missing genuine sender/sample and API access/signing/allowed connector route are unresolved |
| Source destinations | Source Update Leads, Hospital Dataset Captures, Hospital Facilities, Hospital Current Metrics and Hospital Busyness Trends; five distinct versioned SharePoint lists |
| Capture files | Immutable responses in the bound OneDrive account; the capture list references files rather than containing their bytes |
| Internal source register | External read-only input, not a destination copied or provisioned by installation |
| Broader workbench | Catalogue/review lists, evidence/draft libraries, Word templates, lifecycle/reconciliation and monthly reporting flows retain their existing release/recovery routes |
| Power BI dashboard | Optional roadmap item, not a promised delivered component; existing Lists/CSV and monthly reporting were the selected baseline |
| Custom application or common integration framework | Not required by the current delivery scope |

SharePoint lists, files and templates do not become Dataverse solution components
simply because a flow uses them. Carry their versioned schemas, provisioning,
templates and dependency bindings alongside the solution. Do not call an installed
solution alone a complete restoration of the product's data or documents.

The source installer deliberately starts new flows stopped. Qualification instances
are also stopped after their tests so they cannot become accidental duplicate
collectors. This differs from a blocked preparation: the production qualified
collectors retain their enabled schedule/arrival configuration.

Keep hospital APIs together while schedule, access and ownership are shared;
independent dataset failure scopes already prevent one failed dataset from
blocking the others. Consider a Power BI source-health report only when the
combined question and intended audience are defined; installation qualification
does not require another report, workspace or licence change.

Clean installation creates isolated empty destinations and stopped automation.
Clean recovery restores selected sealed records/files into isolated objects.
Cross-tenant recovery was removed from commissioned scope on 31 October 2026.
Clean recovery remains supported in isolated objects in the existing tenant.
Historical portable mapping work is retained; it does not commission a transfer.
