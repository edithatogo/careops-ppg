# SharePoint property-bound cover probe

`scripts/ppg_sharepoint_cover.py` provides a manual qualification graph and an
independent DOCX inspector. It does not deploy a flow or generate Word body text.
Use an existing qualified Standard SharePoint connection. No premium document
generation action, new connection, schedule or delivery action is included.

Keep the library's maintained Forms/content-type template and its association.
For execution, select a separately versioned ordinary library DOCX with the same
property bindings. Establish the destination schema before pinning the template;
schema changes can alter Office metadata. Download and inspect the selected file,
then retain its native identity, ETag, template revision and source provenance in
private evidence. A Forms file is not an eligible execution source for this probe.

`build_qualification_flow` copies the ordinary template through the Standard
`GetFileMetadataByPath` and `CopyFileAsync` operations. The destination folder must
already exist. The copy preserves the source filename; use a fresh revision folder
instead of renaming through an unsupported copy parameter. Conflict behavior is
Fail, and automatic connector retries are disabled. The original template is
never populated or overwritten.

The serial graph checks the frozen template identity/ETag, copies it and checks
the source pin again before using the copy. Source drift leaves a preserved
partial output and refuses metadata writes. It then reads the copied file's list
item and requires the actual response-header ETag before a conditional
metadata MERGE. It reads back all seven accepted scalar values and fails on any
mismatch. An HTTP 200 alone is not a semantic success criterion. This manually
triggered graph has no modification trigger that could loop on its own updates.

After a run, independently download the output. Check ZIP integrity, all seven
native properties and all seven saved visible controls separately. A successful
metadata write does not refresh cached Word text. Retain manual entry or a
qualified native refresh/save route when the selected client leaves placeholders.
Verify the actual body, layout, editing and saved download in each selected client
before admitting the exact output hash. `admit_cover` refuses metadata-only,
changed or mismatched revisions; it does not establish visual or human acceptance.

For an interrupted or failed operation, capture the run/actions and reconcile the
destination before taking another action. An existing destination is a refusal,
not automatic resume: read its identity, ETag, bytes and metadata, preserve human
edits and follow the privately qualified recovery route. Never delete a partial
file or choose overwrite to make a rerun pass. Verify an unchanged replay does not
add another file or revision. Wider package recovery, repeating tables, optional
sections, narrative generation and issued-document workflows require their own
qualification.

Keep actual bindings, runs, outputs and acceptance receipts outside portable Git.
Fictional tests verify graph construction and admission behavior only.
