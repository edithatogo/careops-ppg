#!/usr/bin/env python3
"""Presentation-only document navigation over existing case and library fields."""
import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from ppg_followup_views import compile_views, validate_paths, verify_views
from ppg_guided_workspace import formatter_json

ROOT = Path(__file__).resolve().parents[1]


def authority_label(row):
    """Recorded evidence completeness, never an issuance/current-policy decision."""
    if row.get('PPGCaptureKind') == 'Supporting source page':
        return 'Supporting source page — not policy authority'
    currency = row.get('PPGCurrency') or 'Unconfirmed'
    if currency == 'Unconfirmed':
        return 'Captured reference — authority unconfirmed'
    if currency not in ['Verified current', 'Verified superseded', 'Verified withdrawn']:
        return 'Unknown currency value — check evidence'
    if not all(row.get(k) for k in ['PPGAuthorityLink', 'PPGCurrencyChecked', 'PPGCurrencyEvidence']):
        return 'Recorded finding incomplete — authority unresolved'
    if currency == 'Verified current':
        return 'Recorded current-authority finding — verify issued source'
    return 'Recorded historical/withdrawn finding — reference only'


def authority_expression():
    return ("=if([$PPGCaptureKind] == 'Supporting source page','Supporting source page — not policy authority',"
            "if([$PPGCurrency] == '' || [$PPGCurrency] == 'Unconfirmed','Captured reference — authority unconfirmed',"
            "if([$PPGCurrency] != 'Verified current' && [$PPGCurrency] != 'Verified superseded' && [$PPGCurrency] != 'Verified withdrawn','Unknown currency value — check evidence',"
            "if([$PPGAuthorityLink] == '' || [$PPGCurrencyChecked] == '' || [$PPGCurrencyEvidence] == '','Recorded finding incomplete — authority unresolved',"
            "if([$PPGCurrency] == 'Verified current','Recorded current-authority finding — verify issued source','Recorded historical/withdrawn finding — reference only')))))")


def compile_navigation(bindings, library_fields, case_fields):
    config = json.loads((ROOT / 'config/document-navigation.json').read_text())
    case_bindings = {k: bindings[k] for k in ['site', 'queue_path', 'readiness_path', 'assurance_path']}
    validate_paths(bindings['site'], [bindings[k] for k in ['library_path', 'current_view_path', 'historical_view_path']])
    drafts = compile_views(**case_bindings, fields=case_fields)[0]
    drafts['create']['parameters']['Title'] = config['caseViewTitle']
    draft_formatter = json.loads(drafts['formatter']['CustomFormatter'])
    draft_children = draft_formatter['rowFormatter']['children']
    draft_children[0]['txtContent'] = config['draftGuidance']
    draft_row = next(row for row in draft_children[1:] if row.get('children', [{}])[0].get('txtContent') == 'Draft/evidence reference: ')
    draft_children.remove(draft_row)
    draft_children.insert(1, draft_row)
    drafts['formatter']['CustomFormatter'] = formatter_json(draft_formatter)
    types = {f['InternalName']: f['TypeAsString'] for f in library_fields}
    if set(config['referenceFields']) - types.keys():
        raise ValueError('Missing reference navigation fields')
    required_types = {'PPGCaptureSHA256': 'Text', 'PPGCaptureKind': 'Choice', 'PPGCurrency': 'Choice',
                      'PPGAuthorityLink': 'URL', 'PPGCurrencyChecked': 'DateTime',
                      'PPGCurrencyEvidence': 'Note', 'PPGReplacesEdition': 'URL'}
    if any(types[k] != v for k, v in required_types.items()):
        raise ValueError('Reference navigation field type drift')
    def text(label, value):
        return {'elmType': 'div', 'style': {'white-space':'normal', 'margin-bottom':'6px'},
                'children': [{'elmType':'span', 'style':{'font-weight':'600'}, 'txtContent': label + ' '},
                             {'elmType':'span', 'txtContent':value}]}
    def link(label, path, condition=None):
        result = {'elmType':'a', 'attributes':{'href':path, 'target':'_blank'},
                  'style':{'display':'block', 'padding':'6px 0'}, 'txtContent':label}
        if condition:
            result['style']['display'] = '=if(' + condition + ",'block','none')"
        return result
    children = [text('Meaning:', config['guidance']), text('Reference:', '[$FileLeafRef]'),
                text('Authority check:', authority_expression()), text('Recorded currency:', "=if([$PPGCurrency] == '', 'Unconfirmed', [$PPGCurrency])"),
                text('Document identity:', "=if([$PPGDocumentUID] == '', 'Unresolved — no family inferred', [$PPGDocumentUID])"),
                text('Source-stated edition:', "=if([$PPGPolicyEdition] == '', 'Missing or unresolved — inspect linkage evidence', [$PPGPolicyEdition])"),
                text('Native file version (not source edition):', '[$_UIVersionString]'),
                link('Open captured reference — not issuance proof', '[$FileRef]'),
                text('Captured source URL (provenance):', '[$PPGCaptureSourceURL]'),
                text('Authority source as recorded:', '[$PPGAuthorityLink]'),
                link('Open recorded authoritative source — verify exact issued edition', '[$PPGAuthorityLink]', "indexOf([$PPGAuthorityLink], 'https://') == 0"),
                text('Currency check date:', '[$PPGCurrencyChecked]'), text('Currency evidence:', '[$PPGCurrencyEvidence]'),
                text('Edition linkage evidence (including unresolved conflicts):', '[$PPGCaptureEditionEvidence]'),
                text('Replaces edition as recorded:', '[$PPGReplacesEdition]'),
                link('Open recorded previous edition — reference only', '[$PPGReplacesEdition]', "indexOf([$PPGReplacesEdition], 'https://') == 0"),
                link('Browse recorded current findings — not issue authority', bindings['current_view_path']),
                link('Browse previous/superseded/withdrawn findings', bindings['historical_view_path']),
                link('Find version-specific publication evidence — verify issued source', bindings['assurance_path'] + '?FilterField1=Stage&FilterValue1=Publication'),
                link('Open local review cases and draft links', bindings['queue_path'] + '/AllItems.aspx')]
    formatter = {'$schema':'https://developer.microsoft.com/json-schemas/sp/v2/row-formatting.schema.json',
                 'hideSelection':False, 'rowFormatter':{'elmType':'div',
                 'style':{'padding':'16px','margin':'8px 0','border':'1px solid #8a8886','width':'100%'}, 'children':children}}
    # Capture SHA is recorded provenance; include supporting pages explicitly and
    # retain their distinct label. Exclude templates, controls and transient files.
    root = escape(bindings['library_path'].rstrip('/') + '/Captured Policy Archive')
    predicate = '<And><IsNotNull><FieldRef Name="PPGCaptureSHA256" /></IsNotNull><And><Eq><FieldRef Name="FSObjType" /><Value Type="Integer">0</Value></Eq><Or><Eq><FieldRef Name="FileDirRef" /><Value Type="Text">' + root + '</Value></Eq><BeginsWith><FieldRef Name="FileDirRef" /><Value Type="Text">' + root + '/</Value></BeginsWith></Or></And></And>'
    references = {'create':{'parameters':{'Title':config['referenceViewTitle'], 'ViewFields':config['referenceFields'],
                  'Query':'<Where>' + predicate + '</Where><OrderBy><FieldRef Name="FileLeafRef" /><FieldRef Name="ID" /></OrderBy>',
                  'PersonalView':False,'SetAsDefaultView':False,'Paged':True,'RowLimit':30}},
                  'formatter':{'CustomFormatter':formatter_json(formatter)}, 'scope':1}
    return {'case':drafts, 'library':references}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['bindings', 'library-fields', 'case-fields']:
        parser.add_argument('--' + name, type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify-readback', type=Path, help='JSON with case/library view arrays')
    args = parser.parse_args()
    def load_fields(path):
        value = json.loads(path.read_text())
        return value['value'] if isinstance(value, dict) else value
    bundle = compile_navigation(json.loads(args.bindings.read_text()), load_fields(args.library_fields), load_fields(args.case_fields))
    if args.verify_readback:
        native = json.loads(args.verify_readback.read_text())
        for key, expected in bundle.items():
            verify_views([expected], native[key])
            if key == 'library':
                found = [v for v in native[key] if v['Title'] == expected['create']['parameters']['Title']][0]
                if found.get('Scope') != expected['scope']:
                    raise ValueError('Reference navigation scope drift')
        print(json.dumps({'verifiedViews':2}))
        return
    with args.output.open('x') as handle:
        json.dump(bundle, handle, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
