"""Offline Power Automate structural profile. No network, writes or runtime claims.

Independently shipped in RIMS, PPG and Clinical Hub; CareOps owns the shared
contract. Diagnostics omit definition values and use numeric action positions.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PROFILE_SHA256 = 'ce2957f9afb1a808113028976bf620386b198d0c058925490b33a56c6992f0f4'
PROFILE_PATH = Path(__file__).with_name('schemas') / 'power-automate-profile.json'
PARAMETER = re.compile(r"(?<![\w])parameters\(\s*'((?:[^']|'')+)'\s*\)", re.I)


def loads(raw):
    """Reject duplicate keys and non-JSON numeric constants before any mutation."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('non_json_number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def finding(check, path, outcome='fail', scope='offline-structure'):
    return {'check': check, 'component': path, 'severity': 'error' if outcome == 'fail' else 'info',
            'evidence_scope': scope, 'outcome': outcome}


def report(checks, **extra):
    return {'status': 'FAIL' if any(c['outcome'] == 'fail' for c in checks) else 'PASS',
            'checks': checks, 'deploymentReady': False, **extra}


def executable_segments(value):
    """Select WDL expressions, excluding interpolation text and escaped at signs."""
    if value.startswith('@') and not value.startswith(('@{', '@@')):
        return [value[1:]]
    segments = []
    index = 0
    while index < len(value):
        if value.startswith('@@', index):
            index += 2
        elif value.startswith('@{', index):
            start = index + 2
            index = start
            quoted = False
            while index < len(value):
                if value[index] == "'":
                    if quoted and value[index:index+2] == "''":
                        index += 2
                        continue
                    quoted = not quoted
                elif value[index] == '}' and not quoted:
                    segments.append(value[start:index])
                    break
                index += 1
            index += 1
        else:
            index += 1
    return segments


def validate_flow(document, *, component='workflow', require_bindings=False):
    """Accept a raw definition, definition envelope or Flow API properties envelope."""
    checks = []
    def fail(code, path):
        checks.append(finding(code, path))
    raw = PROFILE_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROFILE_SHA256:
        return report([finding('profile_hash_mismatch', component)])
    profile = loads(raw)
    if not isinstance(document, dict):
        return report([finding('invalid_envelope', component)])
    properties = document.get('properties', document)
    if not isinstance(properties, dict):
        return report([finding('invalid_envelope', component)])
    definition = properties.get('definition', properties)
    if not isinstance(definition, dict):
        return report([finding('invalid_definition', component)])
    bindings = properties.get('connectionReferences')
    if 'connectionReferences' in properties and (not isinstance(bindings, dict) or any(not isinstance(v, dict) for v in bindings.values())):
        return report([finding('invalid_connection_references', component)])
    parameters = definition.get('parameters', {})
    if not isinstance(parameters, dict):
        return report([finding('invalid_parameters', component)])
    for index, parameter in enumerate(parameters.values()):
        if not isinstance(parameter, dict) or parameter.get('type') not in profile['parameterTypes']:
            fail('invalid_parameter_declaration', f'{component}/parameters/{index}')
    def expressions(value, path):
        if isinstance(value, str):
            for segment in executable_segments(value):
                # Quoted expression arguments are data, not function calls.
                clean = re.sub(r"'(?:[^']|'')*'", lambda m: ' ' * len(m[0]), segment)
                for match in PARAMETER.finditer(segment):
                    if clean[match.start():match.start()+10].lower() != 'parameters':
                        continue
                    if match[1].replace("''", "'") not in parameters:
                        fail('undeclared_parameter', path)
        elif isinstance(value, dict):
            for index, item in enumerate(value.values()):
                expressions(item, f'{path}/{index}')
        elif isinstance(value, list):
            for index, item in enumerate(value):
                expressions(item, f'{path}/{index}')
    connectors = 0
    def graph(actions, path, *, triggers=False):
        nonlocal connectors
        if not isinstance(actions, dict):
            fail('invalid_action_map', path)
            return
        dependencies = {}
        for index, (name, node) in enumerate(actions.items()):
            here = f'{path}/{index}'
            if not name or not isinstance(node, dict) or not isinstance(node.get('type'), str) or not node['type']:
                fail('invalid_action', here)
                continue
            after = node.get('runAfter', {})
            if not isinstance(after, dict):
                fail('invalid_run_after', here)
                after = {}
            dependencies[name] = set()
            for dep, statuses in after.items():
                if dep == name:
                    fail('self_dependency', here)
                if dep not in actions:
                    fail('non_sibling_dependency', here)
                elif dep != name:
                    dependencies[name].add(dep)
                if not isinstance(statuses, list) or not statuses or any(s not in profile['dependencyStatuses'] for s in statuses):
                    fail('invalid_dependency_status', here)
            kind = node['type']
            if kind in {'OpenApiConnection', 'OpenApiConnectionWebhook'}:
                connectors += 1
                inputs = node.get('inputs', {})
                host = inputs.get('host', {}) if isinstance(inputs, dict) else {}
                if not isinstance(host, dict):
                    fail('invalid_connector_host', here)
                else:
                    alias = host.get('connectionName') or host.get('connectionReferenceName')
                    if not isinstance(alias, str) or not alias:
                        fail('missing_connector_alias', here)
                    elif bindings is not None and alias not in bindings:
                        fail('unbound_connector_host', here)
                    elif bindings is None and require_bindings:
                        fail('missing_connection_references', here)
            if kind in {'Scope','Foreach','Until','If'}:
                graph(node.get('actions'), here+'/actions')
                if kind == 'If':
                    other = node.get('else', {})
                    if not isinstance(other, dict):
                        fail('invalid_else', here)
                    else:
                        graph(other.get('actions', {}), here+'/else')
                if kind == 'Foreach' and 'foreach' not in node:
                    fail('missing_foreach_expression', here)
                if kind in {'If','Until'} and 'expression' not in node:
                    fail('missing_condition_expression', here)
            elif kind == 'Switch':
                if 'expression' not in node:
                    fail('missing_switch_expression', here)
                cases = node.get('cases', {})
                if not isinstance(cases, dict):
                    fail('invalid_cases', here)
                else:
                    for n, branch in enumerate(cases.values()):
                        if not isinstance(branch, dict) or 'case' not in branch:
                            fail('invalid_case', f'{here}/cases/{n}')
                        else:
                            graph(branch.get('actions'), f'{here}/cases/{n}')
                default = node.get('default', {})
                if not isinstance(default, dict):
                    fail('invalid_default', here)
                else:
                    graph(default.get('actions', {}), here+'/default')
            elif any(key in node for key in ('actions','else','cases','default')):
                checks.append(finding('unknown_action_container', here, 'unverified'))
            # Do not treat literal payloads shaped like actions as executable graphs.
            for key in ('inputs','expression','foreach','limit','recurrence','splitOn','conditions'):
                if key in node:
                    expressions(node[key], here+'/'+key)
        # Kahn elimination, local to siblings; loops are container semantics, not cycles.
        pending = {k: set(v) for k,v in dependencies.items()}
        while pending:
            ready = {k for k,v in pending.items() if not (v & pending.keys())}
            if not ready:
                fail('dependency_cycle', path)
                break
            for k in ready:
                del pending[k]
    for key in profile['requiredDefinitionObjects']:
        graph(definition.get(key), component+'/'+key, triggers=key == 'triggers')
    if isinstance(definition.get('triggers'), dict) and not definition['triggers']:
        fail('missing_trigger', component+'/triggers')
    expressions(definition.get('outputs', {}), component+'/outputs')
    if connectors and bindings is None and not require_bindings:
        checks.append(finding('connection_resolution', component, 'unverified'))
    if not any(c['outcome'] == 'fail' for c in checks):
        checks.append(finding('supported_profile_and_graph', component, 'pass'))
    checks.append(finding('connector_expression_and_runtime', component, 'unverified', 'native'))
    return report(checks, profile=profile['profile'], profileSha256=PROFILE_SHA256)


def validate_members(members):
    """Validate a packed/unpacked solution's XML/JSON byte mapping without writes.

PAC unpacked Workflow XML declarations are siblings of workflow JSON; packed
exports may instead place declarations in customizations.xml. Absent declaration
sections are unverified, not fabricated requirements for every export format.
"""
    checks = []
    lowered = {name.lower(): name for name in members}
    if len(lowered) != len(members):
        return report([finding('duplicate_member_case', 'solution')])
    def xml(name):
        key = lowered.get(name) or lowered.get('other/'+name)
        if key is None:
            raise ValueError('missing_solution_xml')
        return ET.fromstring(members[key])
    try:
        solution, custom = xml('solution.xml'), xml('customizations.xml')
        roots = [n.get('id','').strip('{}').lower() for n in solution.findall('.//RootComponent') if n.get('type') == '29']
        refs = {}
        for n in custom.findall('.//connectionreference'):
            logical = n.get('connectionreferencelogicalname')
            if not logical or logical in refs:
                checks.append(finding('duplicate_or_missing_reference', 'solution'))
            refs[logical] = n.findtext('connectorid','').rsplit('/',1)[-1]
        workflows = {}
        declaration_ids = []
        declarations = list(custom.findall('.//Workflow'))
        for name, raw in members.items():
            if name.lower().startswith('workflows/') and name.lower().endswith('.xml'):
                document = ET.fromstring(raw)
                declarations.extend([document] if document.tag == 'Workflow' else document.findall('.//Workflow'))
        for node in declarations:
            declaration_ids.append((node.get('WorkflowId') or node.get('workflowid') or '').strip('{}').lower())
        for index, (name, raw) in enumerate(members.items()):
            if not name.lower().startswith('workflows/') or not name.lower().endswith('.json'):
                continue
            data = loads(raw)
            location = f'workflow/{len(workflows)}'
            checks.extend(validate_flow(data, component=location, require_bindings=True)['checks'])
            match = re.search(r'-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.json$', name, re.I)
            if not match:
                checks.append(finding('unrecognised_workflow_identity', location))
                continue
            identity = match[1].lower()
            if identity in workflows:
                checks.append(finding('duplicate_workflow_identity', location))
            workflows[identity] = name
            for binding in data.get('properties',{}).get('connectionReferences',{}).values():
                if not isinstance(binding, dict):
                    continue
                logical = binding.get('connection',{}).get('connectionReferenceLogicalName')
                if logical not in refs:
                    checks.append(finding('unresolved_connection_reference', location))
                elif binding.get('api',{}).get('name') != refs[logical]:
                    checks.append(finding('connector_mismatch', location))
        if len(roots) != len(set(roots)):
            checks.append(finding('duplicate_root_workflow', 'solution'))
        if set(roots) != set(workflows):
            checks.append(finding('root_workflow_mismatch', 'solution'))
        if declarations:
            if len(declaration_ids) != len(set(declaration_ids)) or set(declaration_ids) != set(workflows):
                checks.append(finding('customization_workflow_mismatch', 'solution'))
        else:
            checks.append(finding('workflow_declaration_section_absent', 'solution', 'unverified'))
        if not workflows:
            checks.append(finding('empty_scaffold_not_deployable', 'solution', 'unverified'))
        if not any(c['outcome'] == 'fail' for c in checks):
            checks.append(finding('solution_cross_references', 'solution', 'pass'))
    except (ValueError, TypeError, AttributeError, KeyError, ET.ParseError):
        checks.append(finding('invalid_solution_member', 'solution'))
    return report(checks)


def dependency_checks(records, root):
    """Validate declared external dependency bytes; absent native proof stays open."""
    checks=[]
    if not records:
        return [finding('external_dependencies_not_declared', 'release', 'unverified')]
    seen=set()
    for i,item in enumerate(records):
        here=f'external/{i}'
        if not isinstance(item,dict) or not item.get('role') or not item.get('path') or not item.get('sha256'):
            checks.append(finding('invalid_external_dependency',here)); continue
        path=Path(item['path'])
        if path.is_absolute() or '..' in path.parts or path.as_posix() in seen:
            checks.append(finding('unsafe_or_duplicate_dependency',here)); continue
        seen.add(path.as_posix())
        target=root/path
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()) or not target.is_file():
            checks.append(finding('missing_external_dependency',here)); continue
        outcome='pass' if hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256'] else 'fail'
        checks.append(finding('external_dependency_hash',here,outcome))
        checks.append(finding('external_dependency_native_version',here,'unverified','native'))
    return checks


def component_map(document):
    """Compact map; callers keep maps of native inputs private."""
    properties = document.get('properties', document)
    definition = properties.get('definition', properties)
    refs = properties.get('connectionReferences', {})
    return {'definitionSha256': hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
            'connectionReferences': [{'alias': alias, 'logicalName': (value.get('connection') or {}).get('connectionReferenceLogicalName') if isinstance(value.get('connection'), dict) else None} for alias, value in sorted(refs.items()) if isinstance(value, dict)],
            'declaredParameters': sorted(definition.get('parameters', {})),
            'environmentVariableResolution': 'unverified; parameter declarations are not proof of environment variables',
            'nativeAcceptance': False}


def inspect_zip(path, settings_path=None):
    from zipfile import ZipFile, BadZipFile
    try:
        with ZipFile(path) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)) or archive.testzip() is not None:
                return report([finding('duplicate_or_corrupt_archive', 'solution')])
            members = {n:archive.read(n) for n in names}
            result = validate_members(members)
            if settings_path is not None:
                result = report(result['checks'] + deployment_settings_checks(loads(Path(settings_path).read_bytes()), members))
            else:
                result['checks'].append(finding('deployment_settings_not_supplied', 'settings', 'unverified'))
            return result
    except (OSError, BadZipFile, ValueError):
        return report([finding('invalid_solution_archive', 'solution')])


def deployment_settings_checks(settings, members):
    """Check standard PAC settings completeness, not permission or connection health."""
    try:
        if not isinstance(settings, dict):
            raise ValueError('invalid_settings')
        refs, envs = set(), set()
        for name, raw in members.items():
            if not name.lower().endswith('.xml'):
                continue
            tree = ET.fromstring(raw)
            nodes = list(tree.iter())
            refs.update(n.get('connectionreferencelogicalname') for n in nodes if n.tag.lower() == 'connectionreference')
            envs.update(n.get('schemaname') for n in nodes if n.tag.lower() == 'environmentvariabledefinition')
        checks=[]
        for key, expected, id_key, value_key in [('ConnectionReferences',refs,'LogicalName','ConnectionId'),('EnvironmentVariables',envs,'SchemaName','Value')]:
            rows=settings.get(key, [])
            if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
                raise ValueError('invalid_settings')
            supplied=[row.get(id_key) for row in rows]
            if any(not isinstance(name,str) or not name for name in supplied):
                raise ValueError('invalid_settings')
            if len(supplied)!=len(set(supplied)) or set(supplied)!=expected:
                checks.append(finding('deployment_settings_identity_mismatch',key))
            if any(value_key not in row or (key=='ConnectionReferences' and (not isinstance(row[value_key], str) or not row[value_key])) or row.get(value_key) is None for row in rows):
                checks.append(finding('deployment_settings_value_missing',key))
        if not checks:
            checks.append(finding('deployment_settings_complete','settings','pass'))
        checks.append(finding('target_binding_access','settings','unverified','native'))
        return checks
    except (ValueError,TypeError,ET.ParseError):
        return [finding('invalid_deployment_settings','settings')]
