"""Validate version-bound standards references before accepting/importing records."""


def unique(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError('Missing or duplicate '+key)
        result[value] = row
    return result


def validate(frameworks, requirements, mappings, crosswalks):
    editions = unique(frameworks, 'frameworkEditionId')
    reqs = unique(requirements, 'requirementId')
    unique(mappings, 'mappingId')
    unique(crosswalks, 'crosswalkId')
    for key, req in reqs.items():
        if req['frameworkEditionId'] not in editions:
            raise ValueError('Unknown framework edition')
        trail = {key}
        parent = req.get('parentRequirementId')
        while parent:
            if parent not in reqs or reqs[parent]['frameworkEditionId'] != req['frameworkEditionId']:
                raise ValueError('Parent missing or belongs to another edition')
            if parent in trail:
                raise ValueError('Requirement hierarchy cycle')
            trail.add(parent)
            parent = reqs[parent].get('parentRequirementId')
    for mapping in mappings:
        if mapping['requirementId'] not in reqs:
            raise ValueError('Mapping requirement missing')
        if not mapping.get('documentUID') or not mapping.get('documentVersion') or not mapping.get('rationale'):
            raise ValueError('Mapping needs document/version/rationale')
        edition = editions[reqs[mapping['requirementId']]['frameworkEditionId']]
        if mapping.get('currentObligation') and edition['status'] != 'published':
            raise ValueError('Nonpublished edition cannot be a current obligation')
        if mapping.get('establishesCompliance') is not False:
            raise ValueError('Mapping is not compliance certification')
        if mapping['status'] not in {'proposed','reviewed','rejected','superseded'}:
            raise ValueError('Unknown mapping state')
        if mapping['status']=='reviewed' and not mapping.get('reviewEvidenceRef'):
            raise ValueError('Reviewed mapping needs decision evidence')
    for row in crosswalks:
        if row['fromRequirementId'] not in reqs or row['toRequirementId'] not in reqs:
            raise ValueError('Crosswalk requirement missing')
        if row['fromRequirementId']==row['toRequirementId']:
            raise ValueError('Self crosswalk')
        if row['correspondence'] not in {'equivalent','partial','related','uncertain'} or not row.get('rationale'):
            raise ValueError('Crosswalk needs explicit correspondence and rationale')
    return True
