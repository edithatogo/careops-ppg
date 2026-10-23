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
