"""Prepare versioned advisory criteria/decision seeds for the native registers."""
import argparse
import hashlib
import json
from pathlib import Path


def records(raw):
    definitions = json.loads(raw)
    version = definitions['criteriaVersion']
    if not isinstance(version, str) or not version.strip():
        raise ValueError('Criteria version required')
    if definitions['status'] != 'draft-for-pilot':
        raise ValueError('This seed route only supports draft advisory definitions')
    criteria = definitions['criteria']
    ids = [c['criterionId'] for c in criteria]
    options = definitions['decisionOptions']
    responses = definitions['responseOptions']
    for values in [ids, options, responses]:
        if not values or any(not isinstance(v, str) or not v.strip() for v in values) or len(values) != len(set(values)):
            raise ValueError('Missing or ambiguous definition identifiers/options')
    digest = hashlib.sha256(raw).hexdigest()
    result = []
    for criterion in criteria:
        if criterion.get('mandatory') is not False:
            raise ValueError('Mandatory rules need a separately verified authority route')
        fields = {'Title': 'title', 'CriterionId': 'criterionId', 'Question': 'question',
                  'Applicability': 'applicability', 'EvidenceRequired': 'evidenceRequired',
                  'AuthorityBasis': 'basis'}
        row = {key: criterion[value] for key, value in fields.items()}
        if any(not isinstance(v, str) or not v.strip() for v in row.values()):
            raise ValueError('Incomplete criterion definition')
        row.update(CriterionKey=version+':'+criterion['criterionId'], CriteriaVersion=version,
                   DefinitionStatus=definitions['status'],
                   RuleAuthority='Advisory; mandatory authority not verified',
                   ResponseOptions=json.dumps(responses, separators=(',', ':')),
                   DefinitionSHA256=digest)
        result.append(dict(list='PPG Review Criteria', key='CriterionKey', record=row))
    result.extend(dict(list='PPG Review Decision Options', key='DecisionKey', record=dict(
        Title=code.replace('_', ' '), DecisionKey=version+':'+code, DecisionCode=code,
        VocabularyVersion=version, DefinitionStatus=definitions['status'])) for code in options)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('definitions', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    seeds = records(args.definitions.read_bytes())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(seeds, stream, indent=2)
    print(json.dumps({'records': len(seeds), 'nativeWrites': 0}))
