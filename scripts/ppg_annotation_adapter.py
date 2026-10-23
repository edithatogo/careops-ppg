"""Normalise verified native annotation fields without assuming internal names."""
import copy


def field_binding(expected, native):
    result = {}
    for field in expected:
        matches = [f for f in native if f.get('StaticName') == field['name']]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous annotation field')
        actual = matches[0]
        if actual['TypeAsString'] != field['type'] or actual['Required'] != field['required']:
            raise ValueError('Annotation schema drift')
        result[field['name']] = actual['InternalName']
    return result


def normalise_annotation(item, binding, original_text, list_identity):
    """Original text is supplied from verified first-version history, not latest note."""
    state = item[binding['ReviewState']]
    valid = {'Received','Triaged','Deferred','Accepted','Rejected','Incorporated','Superseded'}
    if state not in valid or not original_text:
        raise ValueError('Unknown status or unavailable original history')
    if not item[binding['DocumentUID']] or not item[binding['DocumentVersion']]:
        raise ValueError('Missing document binding')
    result = {'annotationId': list_identity+':'+str(item['Id']),
            'documentUID': item[binding['DocumentUID']],
            'documentVersion': item[binding['DocumentVersion']],
            'sectionId': item.get(binding['SectionId']), 'status': state.lower(),
            'originalText': original_text, 'latestAddition': item.get(binding['OriginalSuggestion']),
            'createdAt': item['Created'], 'contributorId': item['AuthorId'],
            'evidenceRef': item.get(binding['EvidenceRef']),
            'decisionRationale': item.get(binding['DecisionRationale']),
            'incorporatedVersion': item.get(binding['IncorporatedVersion'])}
    if 'DispositionSummary' in binding:
        result['dispositionSummary'] = item.get(binding['DispositionSummary'])
    return result


def annotations_from_export(export):
    """Require complete first-version history; preserve every addition in the pack."""
    def complete(page):
        if any(page.get(k) for k in ('odata.nextLink', '@odata.nextLink', 'nextLink', '__next')):
            raise ValueError('Incomplete annotation export')
        return page['value']
    binding = export['binding']
    histories = {}
    for history in export['histories']:
        if history['id'] in histories:
            raise ValueError('Duplicate annotation history')
        histories[history['id']] = complete(history['versions'])
    result = []
    for item in complete(export['annotationItems']):
        versions = histories.get(item['Id'], [])
        versions = sorted(versions, key=lambda v: v['VersionId'])
        if not versions or versions[0]['VersionLabel'] != '1.0':
            raise ValueError('Original annotation history unavailable')
        def field(version, name):
            matches = [v for k,v in version.items() if k.replace('_x005f_', '_') == binding[name]]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous version field')
            return matches[0]
        annotation = normalise_annotation(item, binding, field(versions[0], 'OriginalSuggestion'), export['listId'])
        if len({v['VersionId'] for v in versions}) != len(versions) or len({v['VersionLabel'] for v in versions}) != len(versions):
            raise ValueError('Duplicate annotation version')
        history = []
        context_fields = {'status': 'ReviewState', 'documentUID': 'DocumentUID',
                          'documentVersion': 'DocumentVersion', 'sectionId': 'SectionId',
                          'incorporatedVersion': 'IncorporatedVersion'}
        if 'DispositionSummary' in binding:
            context_fields['dispositionSummary'] = 'DispositionSummary'
        for version in versions:
            entry = dict(version=version['VersionLabel'], createdAt=version['Created'],
                         suggestion=field(version, 'OriginalSuggestion'),
                         evidenceRef=field(version, 'EvidenceRef'),
                         rationale=field(version, 'DecisionRationale'))
            missing = []
            for output, source in context_fields.items():
                matches = [v for k, v in version.items()
                           if k.replace('_x005f_', '_') == binding[source]]
                if len(matches) > 1:
                    raise ValueError('Ambiguous version context field')
                value = matches[0] if matches else None
                if not matches:
                    missing.append(source)
                if output == 'status' and matches:
                    if value not in {'Received','Triaged','Deferred','Accepted','Rejected','Incorporated','Superseded'}:
                        raise ValueError('Unknown historical annotation status')
                    value = value.lower()
                entry[output] = copy.deepcopy(value)
            for output, source in [('author', 'Author'), ('editor', 'Editor'), ('modifiedAt', 'Modified')]:
                entry[output] = copy.deepcopy(version.get(source))
                if source not in version:
                    missing.append(source)
            entry['missingHistoryFields'] = missing
            history.append(entry)
        annotation['versionHistory'] = history
        result.append(annotation)
    return result
