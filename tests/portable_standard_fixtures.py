"""Entirely fictional standards indexes; no policy text or operative edition."""

def frameworks():
    return {'schemaVersion': 1, 'sourceFrameworkEditionId': 'fictional-framework-v1',
            'frameworks': [{'frameworkEditionId': 'fictional-framework-v1',
                'status': 'published', 'requirements': [
                    {'requirementId': f'fictional-framework-v1-{i}', 'code': str(i),
                     'title': f'Fictional standard {i}', 'kind': 'standard',
                     'parentRequirementId': None} for i in range(1, 9)]}]}


def supplement(standard):
    count = {1: 33, 2: 14, 3: 19, 4: 15, 5: 36, 6: 11, 7: 10, 8: 13}[standard]
    return {'schemaVersion': 1, 'frameworkEditionId': 'fictional-framework-v1',
            'sourceURL': 'https://example.invalid/fictional-standard',
            'sourceSha256': '0' * 64, 'representation': 'Non-normative fictional test index',
            'requirements': [{'requirementId': f'fictional-framework-v1-{standard}.{n:02d}',
                'code': f'{standard}.{n:02d}', 'kind': 'action',
                'parentRequirementId': f'fictional-framework-v1-{standard}',
                'topic': f'Fictional action {n}', 'pdfPage': 10 + (n - 1) // 5,
                'printedPage': 6 + (n - 1) // 5} for n in range(1, count + 1)]}
