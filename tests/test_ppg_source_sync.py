"""Fictional data only; checks the data-loss and checkpoint boundaries."""
import copy
import csv
from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "ppg_source_sync.py"
spec = importlib.util.spec_from_file_location("sync", MODULE)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
UIDS = ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"]
FIELDS = {"sourceDocumentId", "sourceTitle", "sourceAuditApproach1", "sourceAuditApproach2"}


class FakeTarget:
    def __init__(self):
        self.items = {u: {"localOwner": "reviewer", "decision": "pending"} for u in UIDS}
        self.version = {u: 1 for u in UIDS}
        self.calls = []
        self.fail_uid = None
        self.bad_readback = False

    def read(self, uid):
        return copy.deepcopy(self.items[uid]), str(self.version[uid])

    def patch(self, uid, fields, etag):
        if uid == self.fail_uid:
            raise RuntimeError("fictional failure")
        if etag != str(self.version[uid]):
            raise RuntimeError("concurrent update")
        assert set(fields) <= FIELDS
        self.calls.append(uid)
        self.items[uid].update(copy.deepcopy(fields))
        if self.bad_readback:
            self.items[uid]["sourceTitle"] = "wrong"
        self.version[uid] += 1


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name)
        self.target = FakeTarget()
        self.aliases = [{"source": "fictional-register", "alias": f"A{i}", "DocumentUID": u}
                        for i, u in enumerate(UIDS)]
        self.snapshot = {"sourceSha256": "fictional-hash", "records": [
            {"sourceRow": i + 2, "fields": {"sourceDocumentId": f"A{i}",
             "sourceTitle": f"Title {i}", "sourceAuditApproach1": "first",
             "sourceAuditApproach2": "second"}} for i in range(2)]}

    def plan(self):
        return sync.prepare(self.snapshot, "fictional-register", self.aliases, FIELDS)

    def run_sync(self):
        return sync.reconcile(self.plan(), self.target, self.state)

    def test_replay_reorder_and_local_edit(self):
        self.assertEqual(self.run_sync()["writeCount"], 2)
        self.target.items[UIDS[0]]["decision"] = "local edit"
        self.snapshot["records"].reverse()
        for i, row in enumerate(self.snapshot["records"]):
            row["sourceRow"] = i + 2
        self.assertEqual(self.run_sync()["writeCount"], 0)
        self.assertEqual(self.target.items[UIDS[0]]["decision"], "local edit")
        self.assertEqual(self.target.items[UIDS[0]]["sourceAuditApproach2"], "second")

    def test_changed_row_updates_source_only(self):
        self.run_sync()
        self.snapshot["records"][0]["fields"]["sourceTitle"] = "changed"
        self.assertEqual(self.run_sync()["writeCount"], 1)
        self.assertEqual(self.target.items[UIDS[0]]["localOwner"], "reviewer")

    def test_partial_failure_checkpoint_and_retry(self):
        self.run_sync()
        checkpoint = (self.state / "last-successful.json").read_bytes()
        for row in self.snapshot["records"]:
            row["fields"]["sourceTitle"] = "new"
        self.target.fail_uid = UIDS[1]
        with self.assertRaises(RuntimeError):
            self.run_sync()
        self.assertEqual((self.state / "last-successful.json").read_bytes(), checkpoint)
        receipts = [json.loads(p.read_text()) for p in self.state.glob("*.json")]
        failed = next(r for r in receipts if r["status"] == "failed")
        self.assertEqual((failed["writeCount"], failed["readbackCount"]), (1, 1))
        self.target.fail_uid = None
        self.assertEqual(self.run_sync()["writeCount"], 1)

    def test_duplicate_identity_is_zero_write_failure(self):
        duplicate = copy.deepcopy(self.snapshot["records"][0])
        duplicate["sourceRow"] = 5
        self.snapshot["records"].append(duplicate)
        with self.assertRaisesRegex(sync.SyncError, "identity_exceptions"):
            self.run_sync()
        self.assertEqual(self.target.calls, [])
        self.assertFalse((self.state / "last-successful.json").exists())

    def test_version_changed_alias_is_exception(self):
        self.snapshot["records"][0]["fields"]["sourceDocumentId"] = "A0-v2"
        with self.assertRaises(sync.SyncError):
            self.run_sync()
        self.assertEqual(self.target.calls, [])

    def test_local_field_rejected_before_writes(self):
        self.snapshot["records"][0]["fields"]["decision"] = "overwrite"
        with self.assertRaisesRegex(sync.SyncError, "unowned"):
            self.run_sync()
        self.assertEqual(self.target.calls, [])

    def test_missing_row_never_retires_or_advances_checkpoint(self):
        self.run_sync()
        checkpoint = (self.state / "last-successful.json").read_bytes()
        self.snapshot["records"].pop()
        result = self.run_sync()
        self.assertEqual(result["status"], "completed_with_missing_exceptions")
        self.assertIn(UIDS[1], self.target.items)
        self.assertEqual((self.state / "last-successful.json").read_bytes(), checkpoint)

    def test_readback_mismatch_never_checkpoints(self):
        self.target.bad_readback = True
        with self.assertRaisesRegex(sync.SyncError, "readback_mismatch"):
            self.run_sync()
        self.assertFalse((self.state / "last-successful.json").exists())

    def test_worker_lock_blocks_second_writer(self):
        (self.state / "worker.lock").touch()
        with self.assertRaises(FileExistsError):
            self.run_sync()
        self.assertEqual(self.target.calls, [])

    def test_source_qualified_aliases(self):
        self.aliases[0]["source"] = "another-register"
        with self.assertRaises(sync.SyncError):
            self.run_sync()
        self.assertEqual(self.target.calls, [])

    def test_frozen_loader_preserves_ordinal_headers_and_raw_values(self):
        raw, main, mapping = [self.state / n for n in ("raw.bin", "main.json", "map.csv")]
        raw.write_bytes(b"fictional raw snapshot")
        columns = [(1, "Document ID\n", "sourceDocumentId"),
                   (2, "Audit Approach", "sourceAuditApproach1"),
                   (3, "Audit Approach", "sourceAuditApproach2")]
        with mapping.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["source_column", "source_header", "mirror_field"])
            writer.writerows(columns)
        data = {"sourceSha256": sync.file_hash(raw), "sourceSheet": "Fictional",
                "headers": [{"column": n, "actual": h, "mirrorField": f, "matches": True}
                            for n, h, f in columns],
                "records": [{"sourceRow": 2, "values": ["A0", 123.5, "ambiguous history"]}]}
        main.write_text(json.dumps(data))
        frozen = sync.load_frozen(main, raw, sync.file_hash(main), sync.file_hash(raw), mapping, 1)
        self.assertEqual(frozen["records"][0]["fields"]["sourceAuditApproach1"], 123.5)
        self.assertEqual(frozen["records"][0]["fields"]["sourceAuditApproach2"], "ambiguous history")
        original_hash = sync.file_hash(raw)
        raw.write_bytes(b"changed bytes")
        with self.assertRaisesRegex(sync.SyncError, "frozen_hash_mismatch"):
            sync.load_frozen(main, raw, sync.file_hash(main), original_hash, mapping, 1)

    def test_hourly_unchanged_poll_does_not_fetch_content(self):
        now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        result = sync.cadence(now, now - timedelta(hours=1), now - timedelta(hours=2), "v1", "v1")
        self.assertEqual(result, {"metadataCheckDue": True, "reconcileDue": False, "reason": "unchanged"})
        result = sync.cadence(now, now, now - timedelta(hours=2), "v2", "v1")
        self.assertTrue(result["reconcileDue"])
        self.assertEqual(result["reason"], "source_changed")

    def test_daily_reconciliation_and_failed_retry_remain_due(self):
        now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        last_success = now - timedelta(days=1)
        self.assertEqual(sync.cadence(now, now, last_success, "v1", "v1")["reason"], "daily_due")
        # A failed attempt advances neither the last-successful time nor version.
        self.assertTrue(sync.cadence(now + timedelta(minutes=5), now, last_success, "v1", "v1")["reconcileDue"])
        result = sync.cadence(now, now, last_success, None, "v1")
        self.assertFalse(result["reconcileDue"])
        self.assertTrue(result["metadataCheckDue"])

    def test_cadence_rejects_ambiguous_or_future_times(self):
        with self.assertRaisesRegex(sync.SyncError, "timezone_required"):
            sync.cadence(datetime(2026, 10, 15), None, None, "v1", None)
        now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        with self.assertRaisesRegex(sync.SyncError, "future_checkpoint"):
            sync.cadence(now, now + timedelta(hours=1), None, "v1", None)

    def test_catalogue_projection_keeps_raw_date_and_qualified_month(self):
        fields = self.snapshot["records"][0]["fields"]
        fields.update({"sourceNextReviewDateRaw": 45000.0, "sourceCustodian": None,
                       "sourceStatus": "current", "sourceRisk": "low"})
        self.snapshot["records"] = self.snapshot["records"][:1]
        dates = [{"row": 2, "column": 6, "raw": 45000.0,
                  "precision": "month", "normalised": "2023-03"}]
        projected = sync.catalogue_projection(self.snapshot, dates, "fictional-snapshot",
                                              "2026-10-15T00:00:00Z", "fictional-records")
        values = projected["records"][0]["projectedFields"]
        self.assertEqual(values["sourceNextReviewDateRaw"], "45000")
        self.assertEqual(values["sourceNextReviewMonth"], "2023-03")
        self.assertIsNone(values["sourceCustodian"])
        plan = sync.prepare(projected, "fictional-register", self.aliases, set(values))
        self.assertEqual(plan["rawRecords"][0]["fields"]["sourceNextReviewDateRaw"], 45000.0)
        self.assertEqual(plan["operations"][0]["fields"]["sourceNextReviewDateRaw"], "45000")
        dates[0]["raw"] = 45001.0
        with self.assertRaisesRegex(sync.SyncError, "unqualified_review_month"):
            sync.catalogue_projection(self.snapshot, dates, "snapshot", "asof", "records")

    def test_blank_note_replay_and_null_readback_preserve_raw_envelope(self):
        row = self.snapshot["records"][0]
        row["fields"].update({"sourceCustodian": "", "sourceStatus": None,
                              "sourceRisk": "low", "sourceNextReviewDateRaw": 45000.0})
        self.snapshot["records"] = [row]
        dates = [{"row": 2, "column": 6, "raw": 45000.0,
                  "precision": "month", "normalised": "2023-03"}]
        projected = sync.catalogue_projection(self.snapshot, dates, "snapshot", "asof", "records")
        values = projected["records"][0]["projectedFields"]
        allowed = {"sourceDocumentId", "sourceTitle", "sourceCustodian", "sourceStatus", "sourceRisk"}
        plan = sync.prepare(projected, "fictional-register", self.aliases[:1], allowed)
        self.target.items[UIDS[0]].update({k: values[k] for k in allowed})
        # Either API blank representation is unchanged, including readback.
        self.target.items[UIDS[0]]["sourceStatus"] = ""
        self.assertEqual(sync.reconcile(plan, self.target, self.state)["writeCount"], 0)
        self.assertEqual(self.target.calls, [])
        self.assertEqual(plan["rawRecords"][0]["fields"]["sourceCustodian"], "")
        self.assertIsNone(plan["rawRecords"][0]["fields"]["sourceStatus"])
        self.assertEqual(plan["rawRecords"][0]["fields"]["sourceNextReviewDateRaw"], 45000.0)
        self.assertFalse(sync.source_equal("sourceNextReviewDateRaw", "", None))
        self.assertFalse(sync.source_equal("decision", "", None))

    def test_raw_date_decimal_text_codec_preserves_typed_distinctions(self):
        self.assertTrue(sync.source_equal("sourceNextReviewDateRaw", "45000.0", "45000"))
        self.assertFalse(sync.source_equal("sourceNextReviewDateRaw", '"45000"', "45000"))
        self.assertFalse(sync.source_equal("sourceNextReviewDateRaw", "true", "1"))
        self.assertFalse(sync.source_equal("sourceNextReviewDateRaw", "", None))
        self.assertFalse(sync.source_equal("sourceTitle", "45000.0", "45000"))


if __name__ == "__main__":
    unittest.main()
