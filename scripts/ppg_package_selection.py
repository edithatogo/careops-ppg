"""Freeze one explicitly selected existing case through the qualified M365 CLI.

Reads only: no authentication changes, source/case writes or Word generation.
selection.json is committed last in a new private directory. Failed reads retain
partial evidence but never produce a selection manifest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID
import zipfile

MAX_SOURCE_BYTES = 2_000_000
CASE_FIELDS = ("Id", "CaseUID", "OData__UIVersionString", "odata.etag",
               "linkedDocumentUIDs", "sourceBaselineRef", "evidenceDraftLink")
FILE_FIELDS = ("UniqueId", "ETag", "UIVersionLabel", "Length", "ServerRelativeUrl")
CATALOGUE_FIELDS = ("Id", "DocumentUID", "sourceDocumentId", "sourceSnapshotRef",
                    "rawSourceRecordRef", "odata.etag")


class SelectionError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise SelectionError(code)


def guid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise SelectionError("invalid_identity") from None


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def opaque_etag(value):
    # Check the token; never trim or reconstruct an accepted opaque ETag.
    match = re.fullmatch(r'(?:W/)?"([^"\r\n]+)"', value) if isinstance(value, str) else None
    return match is not None and bool(match.group(1).strip())


def file_pin(value):
    require(isinstance(value, dict) and all(k in value for k in FILE_FIELDS), "source_pin_missing")
    guid(value["UniqueId"])
    require(opaque_etag(value["ETag"]) and nonblank(value["UIVersionLabel"]) and
            nonblank(value["ServerRelativeUrl"]), "source_pin_invalid")
    size = value["Length"]
    require((type(size) is int and size >= 0) or
            (isinstance(size, str) and re.fullmatch(r"[0-9]+", size) is not None),
            "source_length_invalid")
    return value


def case_pin(value):
    require(isinstance(value, dict) and all(k in value for k in CASE_FIELDS), "case_pin_missing")
    guid(value["CaseUID"])
    require(type(value["Id"]) is int and value["Id"] > 0 and
            opaque_etag(value["odata.etag"]) and nonblank(value["OData__UIVersionString"]) and
            all(nonblank(value[k]) for k in ("linkedDocumentUIDs", "sourceBaselineRef", "evidenceDraftLink")),
            "case_pin_invalid")
    return {k: value[k] for k in CASE_FIELDS}


def catalogue_pins(rows):
    require(isinstance(rows, list), "catalogue_response_invalid")
    result = []
    for row in rows:
        require(isinstance(row, dict) and all(k in row for k in CATALOGUE_FIELDS), "catalogue_pin_missing")
        guid(row["DocumentUID"])
        require(type(row["Id"]) is int and row["Id"] > 0 and opaque_etag(row["odata.etag"]) and
                all(nonblank(row[k]) for k in ("sourceDocumentId", "sourceSnapshotRef", "rawSourceRecordRef")),
                "catalogue_pin_invalid")
        # odata.id is a response annotation that can vary between identical reads.
        # Stable native item ID, opaque ETag and every selected source field remain pinned.
        result.append({k: row[k] for k in CATALOGUE_FIELDS})
    require(len({row["Id"] for row in result}) == len(result), "duplicate_catalogue_item")
    return sorted(result, key=lambda row: (row["DocumentUID"], row["Id"]))


def write_json(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


class Client:
    def call(self, args):
        try:
            result = subprocess.run(["m365", "request", "--method", "get", *args, "--output", "json"],
                                    capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise SelectionError("native_read_timeout") from None
        require(result.returncode == 0, "native_read_failed")
        return result.stdout

    def get(self, url):
        try:
            return json.loads(self.call(["--url", url, "--accept", "application/json;odata=minimalmetadata"]))
        except json.JSONDecodeError:
            raise SelectionError("invalid_native_json") from None

    def download(self, url, destination):
        self.call(["--url", url, "--accept", "application/octet-stream",
                   "--filePath", str(destination)])
        destination.chmod(0o600)


def source_path(site, value):
    require(isinstance(value, str), "source_link_missing")
    base, link = urlsplit(site), urlsplit(value)
    path = unquote(link.path)
    require(link.scheme == "https" and link.netloc == base.netloc and
            not link.query and not link.fragment and not link.username and
            path.startswith(base.path.rstrip("/") + "/") and
            all(part not in (".", "..") for part in path.split("/")),
            "source_outside_bound_site")
    return path


def checked_zip(path, word=False):
    try:
        with zipfile.ZipFile(path) as archive:
            require(sum(x.file_size for x in archive.infolist()) <= 100_000_000,
                    "archive_expansion_limit")
            require(archive.testzip() is None, "archive_crc_failed")
            if word:
                require({"[Content_Types].xml", "word/document.xml"}.issubset(archive.namelist()),
                        "word_document_parts_missing")
    except zipfile.BadZipFile:
        raise SelectionError("invalid_source_archive") from None


def fetch_source(client, site, link, role, output):
    path = source_path(site, link)
    suffix = ".zip" if role == "recorded-baseline" else ".docx"
    require(path.lower().endswith(suffix), "unsupported_selected_shape")
    encoded = quote(path.replace("'", "''"), safe="/")
    query = "?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl,TimeLastModified"
    before = file_pin(client.get(site + "/_api/web/GetFileByServerRelativePath(decodedurl='" + encoded + "')" + query))
    require(before["ServerRelativeUrl"] == path, "source_path_changed")
    require(0 <= int(before["Length"]) <= MAX_SOURCE_BYTES, "source_size_limit")
    uid = guid(before["UniqueId"])
    endpoint = site + "/_api/web/GetFileById('" + uid + "')"
    destination = output / (role + suffix)
    client.download(endpoint + "/$value", destination)
    after = file_pin(client.get(endpoint + query))
    write_json(output / (role + "-before.json"), before)
    write_json(output / (role + "-after.json"), after)
    require(all(before[k] == after.get(k) for k in FILE_FIELDS), "source_pin_changed")
    require(destination.stat().st_size == int(after["Length"]), "source_length_mismatch")
    checked_zip(destination, word=role == "existing-manual-draft")
    return {"role": role, "sourceReference": link, "nativePin": after,
            "file": destination.name, "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "zipCRCVerified": True}


def freeze(deployment, case_id, expected_case_uid, output, client=None):
    client = client or Client()
    require(type(case_id) is int and case_id > 0, "invalid_case_item")
    expected_case_uid = guid(expected_case_uid)
    binding = deployment["destination"]
    site = binding["siteUrl"].rstrip("/")
    parsed = urlsplit(site)
    require(parsed.scheme == "https" and parsed.hostname and
            parsed.hostname.endswith(".sharepoint.com") and not parsed.query and
            not parsed.fragment and not parsed.username, "invalid_bound_site")
    case_list, catalogue_list = guid(binding["reviewQueueListId"]), guid(binding["catalogueListId"])
    output = Path(output)
    require(output.parent.is_dir() and not output.is_symlink(), "output_parent_required")
    try:
        output.mkdir(mode=0o700)
    except FileExistsError:
        raise SelectionError("output_exists_requires_new_revision") from None
    try:
        case_url = site + "/_api/web/lists(guid'" + case_list + "')/items(" + str(case_id) + ")"
        case = case_pin(client.get(case_url))
        require(guid(case.get("CaseUID")) == expected_case_uid, "case_identity_mismatch")
        require(case["Id"] == case_id, "case_item_mismatch")
        write_json(output / "case-before.json", case)
        linked = json.loads(case["linkedDocumentUIDs"])
        require(isinstance(linked, list) and 0 < len(linked) <= 200, "linked_identity_missing")
        uids = [guid(x) for x in linked]
        require(len(set(uids)) == len(uids), "duplicate_linked_identity")
        # Validate both existing links before making any binary download.
        for key in ("sourceBaselineRef", "evidenceDraftLink"):
            source_path(site, case[key])
        where = " or ".join("DocumentUID eq '" + uid + "'" for uid in sorted(uids))
        catalogue_url = (site + "/_api/web/lists(guid'" + catalogue_list +
                         "')/items?$select=Id,DocumentUID,sourceDocumentId,sourceSnapshotRef,rawSourceRecordRef&$filter=" +
                         quote(where, safe="='") + "&$orderby=DocumentUID")
        raw_catalogue = client.get(catalogue_url)
        write_json(output / "catalogue-before-raw.json", raw_catalogue)
        catalogue = catalogue_pins(raw_catalogue["value"])
        require(len(catalogue) == len(uids) and
                {guid(x["DocumentUID"]) for x in catalogue} == set(uids),
                "linked_catalogue_identity_unresolved")
        require(all(x.get("sourceSnapshotRef") == case["sourceBaselineRef"] for x in catalogue),
                "catalogue_baseline_mismatch")
        write_json(output / "catalogue-before.json", catalogue)
        sources = [fetch_source(client, site, case[key], role, output) for key, role in
                   [("sourceBaselineRef", "recorded-baseline"), ("evidenceDraftLink", "existing-manual-draft")]]
        require(sum(x["bytes"] for x in sources) <= MAX_SOURCE_BYTES, "selected_sources_size_limit")
        current_raw_catalogue = client.get(catalogue_url)
        write_json(output / "catalogue-after-raw.json", current_raw_catalogue)
        current_catalogue = catalogue_pins(current_raw_catalogue["value"])
        current_case = case_pin(client.get(case_url))
        write_json(output / "catalogue-after.json", current_catalogue)
        write_json(output / "case-after.json", current_case)
        require(catalogue == current_catalogue, "catalogue_changed_during_selection")
        require(case == current_case, "case_changed_during_selection")
        result = {"schemaVersion": 1, "kind": "existing-case-artifact-selection",
                  "caseBinding": {"site": site, "listId": case_list, "itemId": case_id, **case},
                  "catalogueBinding": {"listId": catalogue_list, "records": catalogue},
                  "sources": sources, "status": "DRAFT / HUMAN CHECK REQUIRED",
                  "sourceWrites": False, "caseWrites": False, "wordGenerationPerformed": False,
                  "nativeWordGenerationReceiptLinked": False,
                  "authoringProvenance": {"status": "unknown", "generationReceipt": None},
                  "packageAssemblyQualified": False, "operativeCurrencyAssessed": False,
                  "businessReviewPerformed": False}
        write_json(output / "selection.json", result)
        return result
    except Exception as error:
        code = str(error) if isinstance(error, SelectionError) else "selection_read_or_validation_failed"
        write_json(output / "failure.json", {"status": "NOT SELECTED", "code": code,
                                             "sourceWrites": False, "caseWrites": False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--case-id", type=int, required=True)
    parser.add_argument("--case-uid", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = freeze(json.loads(args.deployment.read_text()), args.case_id, args.case_uid, args.output)
    except (SelectionError, OSError, ValueError, KeyError):
        print("Selection failed; no source/case writes. Retain partial evidence and inspect failure.json.")
        return 1
    print("Frozen existing case selection:", len(result["sources"]), "sources; no Word generation or business review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
