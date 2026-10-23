"""QW3 source-only reconciliation preparation (standard library only).

QW1 supplies persistent UUIDs, source-qualified exact aliases, approved fields and
the frozen snapshot. Unknown/version-changed aliases are exceptions, never fuzzy
matches or automatically minted identities. No native client is bound here.

Target adapter contract: read(uid) -> (fields, etag), patch(uid, source_patch,
etag) with conditional concurrency, then read(uid). Target must restrict itself
to the assigned catalogue; it must never expose create/delete or case writes.
Native binding additionally requires QW1 resource/schema/baseline handoff.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from decimal import Decimal


class SyncError(ValueError):
    pass


SUMMARY_NOTE_FIELDS = frozenset({"sourceDocumentId", "sourceTitle", "sourceCustodian",
                                 "sourceStatus", "sourceRisk"})


def source_equal(field: str, actual, expected) -> bool:
    """SharePoint Note blank codec only; never normalize the raw envelope."""
    if field in SUMMARY_NOTE_FIELDS:
        actual = None if actual == "" else actual
        expected = None if expected == "" else expected
    if field == "sourceNextReviewDateRaw" and isinstance(actual, str) and isinstance(expected, str):
        try:
            decoded_actual = json.loads(actual, parse_float=Decimal, parse_int=Decimal)
            decoded_expected = json.loads(expected, parse_float=Decimal, parse_int=Decimal)
        except (ValueError, TypeError):
            return actual == expected
        if isinstance(decoded_actual, Decimal) and isinstance(decoded_expected, Decimal):
            return decoded_actual == decoded_expected
    return actual == expected


class Target(Protocol):
    def read(self, uid: str) -> tuple[dict, str]: ...
    def patch(self, uid: str, fields: dict, etag: str) -> None: ...


def cadence(now: datetime, last_metadata_check: datetime | None,
            last_successful_reconciliation: datetime | None,
            current_version: str | None, last_successful_version: str | None) -> dict:
    """Decision contract for the assigned native flow; does not enable a schedule.

    Version means exact source-file metadata (e.g. ETag), never catalogue metadata.
    Pass current_version only after a successful exact-source metadata read. Failed
    attempts do not update last-successful dates/version. Hourly checks do not fetch
    content; unchanged content is read only when daily reconciliation is due.
    """
    for moment in (now, last_metadata_check, last_successful_reconciliation):
        if moment is not None and (moment.tzinfo is None or moment.utcoffset() is None):
            raise SyncError("timezone_required")
        if moment is not None and moment > now:
            raise SyncError("future_checkpoint")
    poll_due = last_metadata_check is None or now - last_metadata_check >= timedelta(hours=1)
    daily_due = (last_successful_reconciliation is None or
                 now - last_successful_reconciliation >= timedelta(days=1))
    if current_version is None or not current_version:
        return {"metadataCheckDue": poll_due or daily_due, "reconcileDue": False,
                "reason": "source_metadata_required"}
    changed = current_version != last_successful_version
    return {"metadataCheckDue": poll_due, "reconcileDue": changed or daily_due,
            "reason": "source_changed" if changed else "daily_due" if daily_due else "unchanged"}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalogue_projection(snapshot: dict, dates: list[dict], snapshot_ref: str,
                         as_of: str, records_ref: str) -> dict:
    """Project the QW1 summary field types without changing the raw envelope.

    References and source as-of come from the frozen owner handoff, never now().
    Exact field/resource qualification and writer transfer are still required.
    """
    import copy
    if not snapshot_ref or not as_of or not records_ref:
        raise SyncError("provenance_required")
    date_rows = {}
    for date in dates:
        if date["column"] == 6:
            if date["row"] in date_rows:
                raise SyncError("duplicate_date_sidecar")
            date_rows[date["row"]] = date
    projected = copy.deepcopy(snapshot)
    for row in projected["records"]:
        raw = row["fields"]
        date = date_rows.get(row["sourceRow"])
        if (date is None or date["raw"] != raw["sourceNextReviewDateRaw"] or
                date["precision"] != "month" or not date["normalised"]):
            raise SyncError("unqualified_review_month")
        def native_scalar(value):
            return int(value) if isinstance(value, float) and value.is_integer() else value
        def text(value):
            if value is None:
                return ""
            if isinstance(value, bool):
                return "true" if value else "false"
            return str(native_scalar(value))
        row["projectedFields"] = {key: text(raw[key]) or None for key in SUMMARY_NOTE_FIELDS}
        row["projectedFields"].update({
            "sourceNextReviewDateRaw": json.dumps(native_scalar(raw["sourceNextReviewDateRaw"]), ensure_ascii=False, separators=(",", ":"), allow_nan=False),
            "sourceNextReviewMonth": date["normalised"], "sourceSnapshotRef": snapshot_ref,
            "sourceAsOfUtc": as_of, "sourceRowNumber": row["sourceRow"],
            "rawSourceRecordRef": records_ref + "#sourceRow=" + str(row["sourceRow"])})
    return projected


def importer_field(name: str) -> bool:
    return name.startswith("source") or name == "rawSourceRecordRef"


def save(path: Path, value) -> None:
    """Atomic durable file replacement; checkpoint is always the last write."""
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load_frozen(main: Path, raw: Path, main_sha256: str, source_sha256: str,
                mapping: Path, expected_rows: int) -> dict:
    """Consume, never regenerate, the owner's frozen extraction and raw bytes."""
    if file_hash(main) != main_sha256 or file_hash(raw) != source_sha256:
        raise SyncError("frozen_hash_mismatch")
    data = json.loads(main.read_text(encoding="utf-8"))
    with mapping.open(newline="", encoding="utf-8") as stream:
        columns = list(csv.DictReader(stream))
    if data["sourceSha256"] != source_sha256 or len(data["records"]) != expected_rows:
        raise SyncError("baseline_accounting_mismatch")
    expected = [(int(c["source_column"]), c["source_header"], c["mirror_field"]) for c in columns]
    actual = [(h["column"], h["actual"], h["mirrorField"]) for h in data["headers"]]
    if actual != expected or not all(h["matches"] for h in data["headers"]):
        raise SyncError("ordinal_header_mismatch")
    records = []
    for row in data["records"]:
        values = row["values"]
        if not isinstance(values, list) or len(values) != len(columns):
            raise SyncError("row_width_mismatch")
        fields = {c["mirror_field"]: values[i] for i, c in enumerate(columns)}
        records.append({"sourceRow": row["sourceRow"], "fields": fields})
    if file_hash(main) != main_sha256 or file_hash(raw) != source_sha256:
        raise SyncError("source_changed_during_read")
    return {"sourceSha256": source_sha256, "sourceSheet": data["sourceSheet"],
            "records": records, "mainSha256": main_sha256,
            "rawSnapshotRef": str(raw.resolve()), "mainRecordsRef": str(main.resolve())}


def prepare(snapshot: dict, source: str, aliases: list[dict], allowed: set[str]) -> dict:
    """Fail closed before any write for duplicate, unknown or ambiguous identity."""
    if not source or "sourceDocumentId" not in allowed or any(not importer_field(f) for f in allowed):
        raise SyncError("source_field_contract_invalid")
    lookup = {}
    for item in aliases:
        UUID(item["DocumentUID"])
        key = (item["source"], item["alias"])
        if key in lookup:
            raise SyncError("duplicate_alias_contract")
        lookup[key] = item["DocumentUID"]
    operations, exceptions, seen, row_numbers = [], [], set(), set()
    for row in snapshot["records"]:
        fields = row["fields"]
        projection = row.get("projectedFields", fields)
        if any(not f.startswith("source") for f in fields) or not allowed <= set(projection):
            raise SyncError("unowned_or_missing_field")
        if row["sourceRow"] in row_numbers:
            raise SyncError("duplicate_row_ordinal")
        row_numbers.add(row["sourceRow"])
        alias = fields["sourceDocumentId"]
        uid = lookup.get((source, alias)) if isinstance(alias, str) else None
        if uid is None:
            exceptions.append({"code": "unknown_alias", "row": row["sourceRow"]})
            continue
        if uid in seen:
            exceptions.append({"code": "duplicate_identity", "row": row["sourceRow"]})
            continue
        seen.add(uid)
        operations.append({"DocumentUID": uid, "fields": {k: projection[k] for k in sorted(allowed)},
                           "sourceRow": row["sourceRow"]})
    expected = {uid for (namespace, _), uid in lookup.items() if namespace == source}
    missing = sorted(expected - seen)
    return {"source": source, "sourceSha256": snapshot["sourceSha256"],
            "inputCount": len(snapshot["records"]), "operations": operations,
            "exceptions": exceptions, "missingUIDs": missing,
            "allowed": sorted(allowed), "contractHash": digest(aliases),
            "rawRecords": snapshot["records"],
            "provenance": {k: snapshot[k] for k in ("mainSha256", "sourceSheet",
                           "rawSnapshotRef", "mainRecordsRef") if k in snapshot}}


def retention_contract(plan: dict, checkpoint: dict, catalogue: list[dict] | None = None) -> dict:
    """Validate committed active/retained accounting; never authorise new absence.

    Native callers must obtain the checkpoint through their qualified reader.
    Local exports are checked for consistency, not authenticated by this function.
    """
    import copy
    for record, keys in ((plan, ('inputCount',)), (checkpoint, ('readbackCount', 'catalogueReadbackCount', 'retainedAbsentReadbackCount'))):
        for key in keys:
            if key in record and (type(record[key]) is not int or record[key] < 0):
                raise SyncError('invalid_retention_count')
    if (checkpoint.get('status') != 'completed' or plan.get('exceptions')
            or plan.get('sourceSha256') != checkpoint.get('sourceSha256')
            or plan.get('contractHash') != checkpoint.get('identityContractHash')
            or plan.get('inputCount') != checkpoint.get('readbackCount')):
        raise SyncError('committed_retention_baseline_mismatch')
    def identities(values):
        if not isinstance(values, list) or any(not isinstance(u, str) or str(UUID(u)) != u for u in values):
            raise SyncError('invalid_retention_identity')
        if len(values) != len(set(values)):
            raise SyncError('duplicate_retention_identity')
        return set(values)
    active = identities([op['DocumentUID'] for op in plan['operations']])
    if len(active) != plan['inputCount']:
        raise SyncError('active_identity_accounting_mismatch')
    missing = identities(plan.get('missingUIDs', []))
    acknowledged = identities(plan.get('acknowledgedMissingUIDs', []))
    retained = identities(checkpoint.get('retainedAbsentUIDs', []))
    if missing != acknowledged or missing != retained or active & retained:
        raise SyncError('unacknowledged_or_conflicting_source_absence')
    ledger = checkpoint.get('identityLedger')
    all_ids = active | retained
    acknowledgements = []
    if ledger:
        if ledger.get('sourceSystemId') != plan.get('source'):
            raise SyncError('retention_source_namespace_mismatch')
        aliases = []
        seen_aliases = set()
        for a in ledger['aliases']:
            uid = a.get('documentUID', a.get('DocumentUID'))
            alias = a.get('sourceDocumentId', a.get('alias'))
            if (not isinstance(alias, str) or not alias or alias in seen_aliases
                    or a.get('source', ledger['sourceSystemId']) != ledger['sourceSystemId']):
                raise SyncError('invalid_retention_alias')
            identities([uid]);seen_aliases.add(alias)
            aliases.append({'source': ledger['sourceSystemId'], 'alias': alias, 'DocumentUID': uid})
        if digest(aliases) != plan['contractHash'] or {a['DocumentUID'] for a in aliases} != all_ids:
            raise SyncError('retention_contract_or_uid_set_mismatch')
        seen_ack = set()
        for ack in ledger.get('sourceAbsenceAcknowledgements', []):
            uid = ack.get('DocumentUID')
            if uid not in all_ids or uid in seen_ack:
                raise SyncError('unknown_or_duplicate_absence_acknowledgement')
            seen_ack.add(uid)
            # Returned identities keep history; they consume no current absence authority.
            if uid not in retained:
                continue
            if (ack.get('sourceSha256') != plan['sourceSha256']
                    or ack.get('effect') != 'retain_unchanged'
                    or any(not isinstance(ack.get(k), str) or not ack[k].strip()
                           for k in ('actor', 'evidenceReference', 'decisionEvidence', 'baseContractHash'))):
                raise SyncError('stale_or_invalid_absence_acknowledgement')
            acknowledgements.append(copy.deepcopy(ack))
        if {a['DocumentUID'] for a in acknowledgements} != retained:
            raise SyncError('explicit_absence_acknowledgement_missing')
    elif retained:
        raise SyncError('committed_retention_ledger_required')
    if retained and (not checkpoint.get('runId') or not checkpoint.get('lastIdentityApplicationHash')
            or checkpoint.get('retainedAbsentUnchanged') is not True
            or checkpoint.get('retainedAbsentReadbackCount') != len(retained)):
        raise SyncError('complete_native_retention_readback_required')
    if checkpoint.get('catalogueReadbackCount', checkpoint['readbackCount']) != len(all_ids):
        raise SyncError('complete_catalogue_accounting_required')
    if catalogue is not None and identities([r['DocumentUID'] for r in catalogue]) != all_ids:
        raise SyncError('catalogue_retention_uid_set_mismatch')
    return {'activeUIDs': sorted(active), 'retainedUIDs': sorted(retained),
            'catalogueUIDs': sorted(all_ids), 'acknowledgements': acknowledgements}


def reconcile(plan: dict, target: Target, state: Path) -> dict:
    """One serial worker; receipt survives partial failure, checkpoint stays last-good.

    Read every intended field back. Conditional patch preserves concurrent local
    edits; never post an entire item. Missing source rows are retained exceptions.
    """
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "worker.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    receipt_path = state / (str(uuid4()) + ".json")
    receipt = {"status": "running", "startedUtc": datetime.now(timezone.utc).isoformat(),
               "sourceSha256": plan["sourceSha256"], "contractHash": plan["contractHash"],
               "inputCount": plan["inputCount"], "readbackCount": 0, "writeCount": 0,
               "exceptions": plan["exceptions"], "missingUIDs": plan["missingUIDs"]}
    try:
        save(state / (receipt_path.stem + ".plan"), plan)
        save(receipt_path, receipt)
        if plan["exceptions"]:
            raise SyncError("identity_exceptions")
        if len(plan["operations"]) != plan["inputCount"]:
            raise SyncError("plan_accounting_mismatch")
        for operation in plan["operations"]:
            fields = operation["fields"]
            if not set(fields) <= set(plan["allowed"]) or any(not importer_field(k) for k in fields):
                raise SyncError("unowned_field")
            uid = operation["DocumentUID"]
            before, etag = target.read(uid)
            patch = {k: v for k, v in fields.items() if k not in before or not source_equal(k, before[k], v)}
            if patch:
                target.patch(uid, patch, etag)
                receipt["writeCount"] += 1
                save(receipt_path, receipt)
            after, _ = target.read(uid)
            if any(k not in after or not source_equal(k, after[k], v) for k, v in fields.items()):
                raise SyncError("readback_mismatch")
            receipt["readbackCount"] += 1
            save(receipt_path, receipt)
        receipt["status"] = "completed_with_missing_exceptions" if plan["missingUIDs"] else "completed"
        receipt["completedUtc"] = datetime.now(timezone.utc).isoformat()
        save(receipt_path, receipt)
        if receipt["status"] == "completed":
            save(state / "last-successful.json", {"receipt": receipt_path.name,
                                                  "planHash": digest(plan), **receipt})
        return receipt
    except Exception as error:
        receipt["status"] = "failed"
        receipt["errorCode"] = str(error) if isinstance(error, SyncError) else type(error).__name__
        save(receipt_path, receipt)
        raise
    finally:
        lock.unlink()
