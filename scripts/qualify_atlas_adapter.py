"""Qualify the fictional Atlas -> PPG package using the repo Python runtime.

Run with .venv-atlas/bin/python scripts/qualify_atlas_adapter.py
--atlas-root ATLAS --atlas-compatibility. The maintained source pin requires
Python >=3.14,<3.15; the explicit compatibility profile preserves that contract
while the default PPG runtime remains Python 3.15.1. Install requirements-atlas.lock
into that repo-local environment. ATLAS/.venv is never selected implicitly.
Atlas code/data are not modified. All fixture DBs and jobs use a temporary folder.
"""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from ppg_atlas_adapter import AdapterError, ATLAS_COMMIT, CONTRACT_SHA256, capture, digest, encoded, supporting_files, query_parameters

ROOT = Path(__file__).resolve().parents[1]

def require_atlas_runtime(metadata, *, atlas_compatibility=False):
    """Refuse unsupported pinned source before importing or executing Atlas."""
    expected = '>=3.14,<3.15' if atlas_compatibility else '>=3.15,<3.16'
    if metadata.get('project', {}).get('requires-python') != expected:
        raise AdapterError('consumer_runtime_constraint_unqualified')

def require_repo_runtime(version=None, executable=None, *, atlas_compatibility=False):
    pin = '.python-version-atlas' if atlas_compatibility else '.python-version'
    environment = '.venv-atlas' if atlas_compatibility else '.venv'
    expected = tuple(int(part) for part in (ROOT / pin).read_text().strip().split('.'))
    actual = tuple(sys.version_info[:3]) if version is None else tuple(version)
    expected_executable = (ROOT / environment / ('Scripts/python.exe' if sys.platform == 'win32'
                                                else 'bin/python')).absolute()
    actual_executable = Path(sys.executable if executable is None else executable).absolute()
    if actual != expected:
        raise RuntimeError(f'Requires repository Python {".".join(map(str, expected))}; got {actual}')
    if actual_executable != expected_executable:
        raise RuntimeError(f'Requires repository interpreter {expected_executable}; got {actual_executable}')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas-root', required=True, type=Path)
    parser.add_argument('--atlas-compatibility', action='store_true',
                        help='Use only the explicit repo-local Atlas compatibility runtime.')
    args = parser.parse_args(); atlas = args.atlas_root.resolve()
    require_repo_runtime(atlas_compatibility=args.atlas_compatibility)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(atlas), *args], text=True).strip()
    if git('rev-parse', 'HEAD') != ATLAS_COMMIT:
        raise AdapterError('consumer_commit_drift')
    if git('status', '--porcelain', '--', 'src', 'tests/test_query_service.py', 'contracts/openapi-readonly-v1.json', 'pyproject.toml'):
        raise AdapterError('consumer_working_source_drift')
    require_atlas_runtime(tomllib.loads((atlas/'pyproject.toml').read_text()),
                          atlas_compatibility=args.atlas_compatibility)
    if digest((atlas/'contracts/openapi-readonly-v1.json').read_bytes()) != CONTRACT_SHA256:
        raise AdapterError('consumer_contract_drift')
    sys.path.insert(0, str(atlas/'src'))
    from fastapi.testclient import TestClient
    from global_medicines_atlas.api import create_app
    from global_medicines_atlas.product_contracts import EvidenceResponse
    from global_medicines_atlas.query_service import ReadOnlyQueryService
    fixture_spec = importlib.util.spec_from_file_location('atlas_existing_fictional_fixture', atlas/'tests/test_query_service.py')
    fixture = importlib.util.module_from_spec(fixture_spec); fixture_spec.loader.exec_module(fixture)
    query = {'concept_id': 'rx:1', 'valid_at': '2026-07-29T00:00:00Z', 'observed_at': '2026-07-29T00:00:00Z'}
    case = 'PPG-ATLAS-FICTIONAL-001'; checks = []
    def adapt(raw):
        return supporting_files(raw, query, case, 'fictional-v1', EvidenceResponse, digest(raw))
    def refuse(raw, code):
        try:
            adapt(raw)
        except AdapterError as exc:
            assert str(exc) == code, (str(exc), code)
        else:
            raise AssertionError('Expected refusal: ' + code)
        checks.append(code)
    with tempfile.TemporaryDirectory(prefix='ppg-atlas-fictional-') as folder:
        tmp = Path(folder); database = fixture._database(tmp/'fictional.duckdb'); before = digest(database.read_bytes())
        with TestClient(create_app(ReadOnlyQueryService(database, cursor_secret=b'fictional-adapter-test-only-secret', allowed_root=tmp))) as client:
            captured = capture(client, query); raw = captured['bytes']
            files = supporting_files(raw, query, case, 'fictional-v1', EvidenceResponse, captured['sha256'])
            missing = capture(client, {**query, 'concept_id': 'fictional-missing-concept'})['bytes']
            refuse(missing, 'no_evidence_no_conclusion')
        value = json.loads(raw)
        assert len(value['evidence']) == 3
        assert {x['dimension'] for x in value['evidence']} == {'regulatory', 'funding'}
        assert files[0]['bytes'] == raw
        def altered(edit):
            v = copy.deepcopy(value); edit(v); return encoded(v)
        refuse(altered(lambda v: v.update(new_schema_field=True)), 'schema_drift')
        refuse(altered(lambda v: v['metadata'].update(evidence_version='999')), 'schema_drift')
        refuse(altered(lambda v: v['metadata']['page'].update(next_cursor='abcdefghijklmnop')), 'incomplete_page')
        refuse(altered(lambda v: v['metadata']['clocks'].update(valid_at='2026-07-30T00:00:00Z')), 'query_clock_mismatch')
        refuse(altered(lambda v: v['evidence'][0].update(concept_id='another-concept')), 'lookup_identity_mismatch')
        refuse(altered(lambda v: v['evidence'][0]['provenance'].update(source_sha256='malformed')), 'schema_drift')
        refuse(b' ' * (1024 * 1024 + 1), 'response_oversize')
        receipt = json.loads(files[1]['bytes'])
        assert len(receipt['sourcePins']) == 3 and any(not p['sourcePinsComplete'] for p in receipt['sourcePins'])
        assert all(p['sourceIntegrity'] == 'unverified' and p['sourceBytesVerified'] is False for p in receipt['sourcePins'])
        assert receipt['sourceBytesVerified'] is False
        assert [p['provenance'] for p in receipt['sourcePins']] == [p['provenance'] for p in value['evidence']]
        try:
            supporting_files(raw + b' ', query, case, 'fictional-v1', EvidenceResponse, captured['sha256'])
        except AdapterError as exc:
            assert str(exc) == 'response_hash_mismatch'
        else:
            raise AssertionError('Tampered response accepted')
        checks.extend(['null_source_pins_preserved_unverified', 'response_hash_mismatch'])
        contradictory = copy.deepcopy(value)
        pinned = next(item for item in value['evidence'] if item['provenance'].get('source_version') and item['provenance'].get('source_sha256'))
        extra = copy.deepcopy(pinned); extra['assertion_id'] += '-contradictory'
        extra['provenance']['source_sha256'] = 'b' * 64
        contradictory['evidence'].append(extra); contradictory['metadata']['page']['returned'] += 1
        refuse(encoded(contradictory), 'contradictory_provenance')
        for bad_query in ({**query, 'CaseUID': case}, {**query, 'assertion_id': 'a-nz-reg'}, {'concept_id': 'rx:1'}):
            try:
                query_parameters(bad_query)
            except AdapterError:
                pass
            else:
                raise AssertionError('Private/ambiguous/incomplete query accepted')
        checks.append('private_ambiguous_incomplete_queries_refused')
        # Unknown is retained as unknown, never inferred into a negative assertion.
        unknown = copy.deepcopy(value); unknown['evidence'][0]['state'] = 'unknown'
        unknown_files = adapt(encoded(unknown)); assert json.loads(unknown_files[0]['bytes'])['evidence'][0]['state'] == 'unknown'
        checks.append('unknown_preserved')
        class DeniedClient:
            base_url = 'http://testserver'
            def get(self, path, **kwargs):
                assert path == '/api/v1/evidence' and kwargs['follow_redirects'] is False
                assert 'CaseUID' not in kwargs['params'] and case not in str(kwargs['params'])
                return type('Denied', (), {'status_code': 403})()
        try:
            capture(DeniedClient(), query)
        except AdapterError as exc:
            assert str(exc) == 'lookup_denied'
        else:
            raise AssertionError('Denied lookup accepted')
        checks.append('lookup_denied')
        class RedirectClient:
            base_url = 'http://testserver'
            def get(self, path, **kwargs):
                assert kwargs['follow_redirects'] is False
                return type('Redirect', (), {'status_code': 302})()
        try:
            capture(RedirectClient(), query)
        except AdapterError as exc:
            assert str(exc) == 'lookup_unavailable'
        else:
            raise AssertionError('Redirect accepted')
        checks.append('redirect_refused')
        class UnqualifiedClient:
            base_url = 'https://unqualified.example.test'
            def get(self, *args, **kwargs):
                raise AssertionError('Unqualified origin contacted')
        try:
            capture(UnqualifiedClient(), query)
        except AdapterError as exc:
            assert str(exc) == 'unqualified_origin'
        else:
            raise AssertionError('Unqualified origin accepted')
        checks.append('unqualified_origin_refused_before_request')
        # Existing immutable explicit-job runner consumes supporting files unchanged.
        source = tmp/'input'; output = tmp/'output'; source.mkdir(); output.mkdir()
        entries = []
        for f in files:
            (source/f['name']).write_bytes(f['bytes'])
            entries.append({key: f[key] for key in ('name', 'role', 'sourceReference')} | {'path': f['name'], 'sha256': digest(f['bytes'])})
        job = {'schemaVersion': 1, 'jobId': 'job-atlas-fictional-v1', 'metadata': {'caseUID': case, 'title': 'Fictional Atlas supporting evidence', 'version': 'fictional-v1', 'sourceBaseline': 'Atlas fictional test database; no real medicine mapping'}, 'attachments': entries}
        jobfile = tmp/'job.json'; jobfile.write_bytes(encoded(job))
        def run():
            return subprocess.run(['node', str(ROOT/'tools/unattended-package/run.cjs'), str(jobfile), str(source), str(output)], capture_output=True, text=True)
        first = run(); assert first.returncode == 0, first.stderr
        package = output/job['jobId']/'package.zip'; package_bytes = package.read_bytes()
        second = run(); assert second.returncode == 0 and json.loads(second.stdout)['state'] == 'replayed', second.stderr
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None
            for i, f in enumerate(files, 1):
                assert archive.read(f"attachments/{i:03d}-{f['name']}") == f['bytes']
            completeness = json.loads(archive.read('completeness.json'))
            assert completeness['missing'] == 13 and completeness['sent'] is False and completeness['sourceWrites'] is False
            manifest = json.loads(archive.read('manifest.json'))
            for entry in manifest['files']:
                assert digest(archive.read(entry['path'])) == entry['sha256']
        package.write_bytes(package_bytes + b'fictional human edit')
        edited = run(); assert edited.returncode != 0 and 'OUTPUT_CHANGED_REQUIRES_NEW_JOB' in edited.stderr
        # A new explicit revision preserves the edited first revision.
        job['jobId'] = 'job-atlas-fictional-v2'; job['metadata']['version'] = 'fictional-v2'
        jobfile.write_bytes(encoded(job)); new = run(); assert new.returncode == 0, new.stderr
        assert package.read_bytes() == package_bytes + b'fictional human edit'
        assert digest(database.read_bytes()) == before
        checks.extend(['actual_api_200_three_records', 'actual_zip_crc_members_hashes', 'unchanged_response_and_receipt', 'same_job_replay', 'edited_output_refused', 'new_revision_preserves_edit', 'fixture_database_unchanged', 'required_evidence_categories_unchanged'])
        # Retain fictional output and raw bytes for independent inspection, never real data.
        evidence = ROOT/'.local/adapters/fictional-qualification'; evidence.mkdir(parents=True, exist_ok=True)
        response_path = evidence/('atlas-response-' + digest(raw) + '.json')
        response_path.write_bytes(raw)
        (evidence/('package-' + digest(package_bytes) + '.zip')).write_bytes(package_bytes)
        proof = {'atlasCommit': ATLAS_COMMIT, 'contractSHA256': CONTRACT_SHA256, 'responseSHA256': digest(raw), 'packageSHA256': digest(package_bytes), 'checks': checks, 'runtimeProfile': 'atlas-compatibility' if args.atlas_compatibility else 'default', 'pythonVersion': '.'.join(map(str,sys.version_info[:3])), 'scope': 'Actual local Atlas API with fictional database -> existing PPG assembler; no hosted/native deployment, real data or clinical acceptance', 'sourceWrites': False, 'caseWrites': False}
        (evidence/('qualification-' + digest(encoded(proof)) + '.json')).write_bytes(encoded(proof))
        print(json.dumps(proof))

if __name__ == '__main__':
    main()
