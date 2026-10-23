# Optional document authoring and validation utility

Evaluate the preferred SharePoint structured-document route for the selected
shape before using a local fallback. This source authors or fills a new detached
DRAFT copy; it supplies no content review, native deployment or issue authority.

The tool-local SDK is pinned to 10.0.402, with a locked Open XML SDK dependency.
From this directory, use an explicitly selected compatible `dotnet` host:

```sh
dotnet restore --locked-mode
dotnet build --no-restore
```

Run `TemplateBuilder.dll` from the repository root with the maintained Markdown
path, expected SHA256 and an absent output DOCX path. `populate-manual` requires
explicit source/template/input binding files and separate absent output/receipt
paths. `validate-docx` checks a detached candidate. Preserve originals, all human
edits, repeated/optional content and issued history. Local schema validation does
not establish native rendering, access or production eligibility.

The portable tests exercise actual generated DOCX packages, repeated groups,
Unicode, links, schema validation, unchanged parts and refusal/recovery behavior.
Inputs are fictional. Native configuration and operational evidence stay outside
this repository. Do not copy a prior deployment's bindings or qualification claims.

## Native structured-document qualification

For SharePoint structured document generation, first verify that the template
creator has an assigned Microsoft Copilot license, Edit access to the target
library, and a maintained Word (.docx) template. Use an isolated fictional
occurrence for qualification; do not enable billing, assign a license, grant
access or change site settings as part of this source workflow.

Treat the case/occurrence identity as the stable parent identity and each
generated document reference as the identity of one immutable output revision.
Every submission creates a new document, and regeneration receives a new
reference number. Retain the earlier file, reference, human edits and issued
history, then link the next reference to the same case/occurrence with its own
source hash, template revision and output revision.

Before replacing this fallback, read back an actual generated output and verify
repeating rows, optional content, links, Word rendering/editing, output access,
revision metadata, and retry/recovery behavior. Verify a human-edited first
output and its history remain unchanged after generating the next revision.
Template publication and document generation do not approve content or authorize
circulation. See Microsoft's [structured document generation prerequisites and
reference behavior](https://learn.microsoft.com/en-us/sharepoint/copilot-in-sharepoint-structured-document-generation).
