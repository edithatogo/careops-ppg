import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ppg_package_selection import freeze, SelectionError

SITE = "https://example.sharepoint.com/sites/ppg"
CASE = "11111111-1111-4111-8111-111111111111"
DOC = "22222222-2222-4222-8222-222222222222"
BASE = "33333333-3333-4333-8333-333333333333"
DRAFT = "44444444-4444-4444-8444-444444444444"
DEPLOYMENT = {"destination": {"siteUrl": SITE, "reviewQueueListId": CASE,
                              "catalogueListId": DOC}}


def archive(parts):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return output.getvalue()


class FakeClient:
    def __init__(self):
        self.case_reads = 0
        self.catalogue_reads = 0
        self.downloads = []
        self.changed_case = False
        self.changed_source = False
        self.wrong_length = False
        self.source_overrides = {}
        self.catalogue_change = None
        self.reorder_catalogue = False
        self.case = {"Id": 1, "CaseUID": CASE, "OData__UIVersionString": "1.0",
                     "odata.etag": '"1"', "linkedDocumentUIDs": json.dumps([DOC]),
                     "sourceBaselineRef": SITE + "/Evidence/baseline.zip",
                     "evidenceDraftLink": SITE + "/Evidence/draft.docx"}
        self.catalogue = [{"Id": 1, "DocumentUID": DOC, "sourceDocumentId": "existing-doc",
                           "sourceSnapshotRef": self.case["sourceBaselineRef"],
                           "rawSourceRecordRef": "existing-record", "odata.etag": '"1"'}]
        self.data = {BASE: archive({"source.xlsb": b"retained bytes"}),
                     DRAFT: archive({"[Content_Types].xml": b"types",
                                     "word/document.xml": b"unchanged draft bytes"})}

    def metadata(self, uid):
        result = {"UniqueId": uid, "ETag": '"opaque-1"', "UIVersionLabel": "1.0",
                "Length": str(len(self.data[uid]) + (1 if self.wrong_length else 0)),
                "ServerRelativeUrl": "/sites/ppg/Evidence/" +
                    ("baseline.zip" if uid == BASE else "draft.docx")}
        result.update(self.source_overrides)
        return result

    def get(self, url):
        assert url.startswith(SITE + "/_api/"), url
        if "/items(1)" in url:
            self.case_reads += 1
            result = copy.deepcopy(self.case)
            if self.changed_case and self.case_reads > 1:
                result["odata.etag"] = '"2"'
            return result
        if "/items?" in url:
            self.catalogue_reads += 1
            rows = copy.deepcopy(self.catalogue)
            if self.catalogue_reads > 1 and self.catalogue_change:
                field, value = self.catalogue_change
                rows[0][field] = value
            if self.catalogue_reads > 1 and self.reorder_catalogue:
                rows.reverse()
            for row in rows:
                row["odata.id"] = "response-annotation-" + str(self.catalogue_reads)
            return {"value": rows}
        if "GetFileByServerRelativePath" in url:
            return self.metadata(BASE if "baseline.zip" in url else DRAFT)
        for uid in self.data:
            if uid in url:
                result = self.metadata(uid)
                if self.changed_source:
                    result["ETag"] = '"opaque-2"'
                return result
        raise AssertionError("Unexpected native read")

    def download(self, url, destination):
        self.downloads.append(url)
        uid = next(uid for uid in self.data if uid in url)
        destination.write_bytes(self.data[uid])


class SelectionTests(unittest.TestCase):
    def run_selection(self, client, output):
        return freeze(DEPLOYMENT, 1, CASE, output, client=client)

    def test_exact_existing_bytes_and_explicit_unknown_authoring(self):
        with tempfile.TemporaryDirectory() as root:
            out, client = Path(root) / "frozen", FakeClient()
            result = self.run_selection(client, out)
            self.assertEqual((out / "recorded-baseline.zip").read_bytes(), client.data[BASE])
            self.assertEqual((out / "existing-manual-draft.docx").read_bytes(), client.data[DRAFT])
            self.assertEqual(result["authoringProvenance"], {"status": "unknown", "generationReceipt": None})
            self.assertFalse(result["wordGenerationPerformed"])
            self.assertFalse(result["caseWrites"])
            self.assertNotIn("odata.id", result["catalogueBinding"]["records"][0])
            self.assertTrue((out / "selection.json").exists())
            saved = (out / "selection.json").read_bytes()
            with self.assertRaisesRegex(SelectionError, "output_exists"):
                self.run_selection(client, out)
            self.assertEqual((out / "selection.json").read_bytes(), saved)

    def test_wrong_site_refused_before_download(self):
        client = FakeClient()
        client.case["evidenceDraftLink"] = "https://other.example/draft.docx"
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "frozen"
            with self.assertRaisesRegex(SelectionError, "outside_bound_site"):
                self.run_selection(client, out)
            self.assertEqual(client.downloads, [])
            self.assertFalse((out / "selection.json").exists())

    def test_unsafe_decoded_path_refused(self):
        client = FakeClient()
        client.case["evidenceDraftLink"] = SITE + "/Evidence/%2e%2e/draft.docx"
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(SelectionError, "outside_bound_site"):
                self.run_selection(client, Path(root) / "frozen")

    def test_missing_duplicate_or_wrong_baseline_catalogue_refused(self):
        for mode in ("missing", "duplicate", "wrong-baseline"):
            client = FakeClient()
            if mode == "missing":
                client.catalogue = []
            elif mode == "duplicate":
                client.catalogue *= 2
            else:
                client.catalogue[0]["sourceSnapshotRef"] = "another baseline"
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                out = Path(root) / "frozen"
                with self.assertRaises(SelectionError):
                    self.run_selection(client, out)
                self.assertEqual(client.downloads, [])
                self.assertFalse((out / "selection.json").exists())

    def test_drift_or_wrong_length_never_commits_selection(self):
        for field in ("changed_case", "changed_source", "wrong_length"):
            client = FakeClient()
            setattr(client, field, True)
            with self.subTest(field=field), tempfile.TemporaryDirectory() as root:
                out = Path(root) / "frozen"
                with self.assertRaises(SelectionError):
                    self.run_selection(client, out)
                self.assertFalse((out / "selection.json").exists())
                self.assertEqual(json.loads((out / "failure.json").read_text())["status"], "NOT SELECTED")

    def test_unusable_case_pins_refused(self):
        for field in ("odata.etag", "OData__UIVersionString", "CaseUID"):
            for value in (None, "", " ", 7, [], {}):
                client = FakeClient()
                client.case[field] = value
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as root:
                    out = Path(root) / "frozen"
                    with self.assertRaises(SelectionError):
                        self.run_selection(client, out)
                    self.assertFalse((out / "selection.json").exists())

    def test_unusable_source_pins_refused(self):
        for field in ("ETag", "UIVersionLabel", "UniqueId", "ServerRelativeUrl"):
            for value in (None, "", " ", 7, [], {}):
                client = FakeClient()
                client.source_overrides[field] = value
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as root:
                    out = Path(root) / "frozen"
                    with self.assertRaises(SelectionError):
                        self.run_selection(client, out)
                    self.assertFalse((out / "selection.json").exists())

    def test_missing_or_invalid_catalogue_etag_refused(self):
        for value in (None, "", " ", 7, "*"):
            client = FakeClient()
            client.catalogue[0]["odata.etag"] = value
            with self.subTest(value=value), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(SelectionError):
                    self.run_selection(client, Path(root) / "frozen")

    def test_opaque_etags_are_retained_exactly(self):
        client = FakeClient()
        client.case["odata.etag"] = 'W/"case:opaque, 5"'
        client.source_overrides["ETag"] = '"source:opaque, 6"'
        with tempfile.TemporaryDirectory() as root:
            result = self.run_selection(client, Path(root) / "frozen")
            self.assertEqual(result["caseBinding"]["odata.etag"], client.case["odata.etag"])
            self.assertEqual(result["sources"][0]["nativePin"]["ETag"], client.source_overrides["ETag"])

    def test_catalogue_domain_or_etag_drift_refused(self):
        for change in (("sourceDocumentId", "changed"), ("sourceSnapshotRef", "changed"),
                       ("rawSourceRecordRef", "changed"), ("odata.etag", '"2"')):
            client = FakeClient()
            client.catalogue_change = change
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                out = Path(root) / "frozen"
                with self.assertRaisesRegex(SelectionError, "catalogue_changed"):
                    self.run_selection(client, out)
                self.assertFalse((out / "selection.json").exists())

    def test_catalogue_order_and_wrapper_annotation_are_not_domain_drift(self):
        client = FakeClient()
        other = "55555555-5555-4555-8555-555555555555"
        client.case["linkedDocumentUIDs"] = json.dumps([DOC, other])
        row = copy.deepcopy(client.catalogue[0])
        row.update(Id=2, DocumentUID=other, sourceDocumentId="existing-doc-2",
                   rawSourceRecordRef="existing-record-2")
        client.catalogue.append(row)
        client.reorder_catalogue = True
        with tempfile.TemporaryDirectory() as root:
            result = self.run_selection(client, Path(root) / "frozen")
            self.assertEqual(len(result["catalogueBinding"]["records"]), 2)


if __name__ == "__main__":
    unittest.main()
