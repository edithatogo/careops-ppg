"""Create native action-index payloads from a verified official source supplement."""
import hashlib
from scripts.ppg_standards_contract import validate


def records(framework_definitions, supplement, source_bytes):
    if hashlib.sha256(source_bytes).hexdigest() != supplement['sourceSha256']:
        raise ValueError('Official source bytes differ from checked supplement')
    frameworks = framework_definitions['frameworks']
    requirements = [{**r, 'frameworkEditionId': f['frameworkEditionId']}
                    for f in frameworks for r in f['requirements']]
    extra = [{**r, 'frameworkEditionId': supplement['frameworkEditionId']}
             for r in supplement['requirements']]
    validate(frameworks, requirements+extra, [], [])
    rows = []
    for r in extra:
        if r['kind'] != 'action' or r['pdfPage'] < 1 or r['printedPage'] < 1:
            raise ValueError('Invalid action/page')
        locator = supplement['sourceURL']+'#page='+str(r['pdfPage'])
        if len(locator) > 255 or not r['topic'].strip():
            raise ValueError('Unusable source locator/topic')
        rows.append({'list': 'PPG Standard Requirements', 'key': 'RequirementKey', 'record': {
            'Title': r['code']+' — '+r['topic'], 'RequirementKey': r['requirementId'],
            'FrameworkKey': r['frameworkEditionId'], 'RequirementCode': r['code'],
            'RequirementKind': 'Action', 'ParentRequirementKey': r['parentRequirementId'],
            'SourceLocator': locator, 'RequirementText': supplement['representation']+'\n'+r['topic']+
            '\nSource SHA256: '+supplement['sourceSha256']+'; printed page '+str(r['printedPage'])}})
    return rows
