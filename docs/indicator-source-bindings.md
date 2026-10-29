# Bind indicator definitions to retained sources

Use the source-binding CLI after the catalogue records and framework have been
saved and read back through your qualified native adapter:

```sh
.venv/bin/python -m scripts.ppg_accreditation_indicator_bindings \
  --prepared /private/path/prepared-indicators.json \
  --catalogue /private/path/catalogue-readback.json \
  --framework /private/path/framework-readback.json \
  --output /private/path/new-bound-indicators.json
```

The catalogue input is an array of native rows containing item IDs, record keys,
kinds, exact `RecordJSON` and `PayloadSHA256`. The framework input is its native
row, optionally wrapped in a `row` property. The prepared input contains
`records`, `qualityStatements` and `summary` from indicator source preparation.

The command checks payload digests and unique identities, resolves each exact
source hash and URL, and requires its publication, edition and explicit framework
membership. Missing or ambiguous captures stop the operation. It preserves unknown
publisher lineage and statement relationships. The output is private and
create-only; an existing output is never overwritten.

This command binds source identities only. It makes no native requests and leaves
`nativePersistenceVerified` false. Actual persistence requires the exact target,
field contract, conditional/create-only safeguards and native readback. Catalogue
metadata alone does not verify the stored capture bytes; verify those separately.

For source retention, Office libraries can add package metadata to uploaded Word
files. Compare the uploaded bytes with the original digest. When exact retention
requires binary storage, keep the original filename and media type in the capture
metadata and use a distinct binary object. Preserve the altered upload without
binding it as the exact original. This does not imply that a binary download has
the same preview behavior as a native Word or PDF document.
