#!/usr/bin/env python3
"""Presentation helpers for existing PPG Lists; never changes records or decisions."""
from datetime import date
import re
import json


def bind_form(template, workspace_path):
    """Resolve only the private workspace path; retain the versioned template."""
    if not workspace_path.startswith("/") or any(c in workspace_path for c in "\"'?#") or ".." in workspace_path:
        raise ValueError("Expected a qualified server-relative workspace path")
    return json.loads(json.dumps(template).replace("{{workspacePath}}", workspace_path))


def formatter_json(formatter):
    """Keep XML-backed view properties safe while preserving JSON semantics."""
    return (json.dumps(formatter).replace('&', chr(92)+'u0026')
            .replace('<', chr(92)+'u003c').replace('>', chr(92)+'u003e'))


def target_state(value, today):
    """An ISO date is a recorded target, not proof of agreement."""
    if not value:
        return 'No target recorded'
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        return 'Pending or non-ISO condition — not classified overdue'
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return 'Invalid calendar date — check target'
    return ('Past recorded date — confirm agreement' if parsed < today else
            'Recorded date — confirm agreement')


def target_expression():
    """Native formatter expression: strict calendar checks, Brisbane date boundary."""
    f='[$targetDate]'
    y=f'Number(substring({f},0,4))'
    m=f'Number(substring({f},5,7))'
    d=f'Number(substring({f},8,10))'
    # Check each character: Number(" 1") and rollover dates must not pass.
    digits=' && '.join(f"indexOf('0123456789',substring({f},{i},{i+1})) >= 0" for i in [0,1,2,3,5,6,8,9])
    # Native length() counts list values; explicit character bounds check text.
    shape=f"substring({f},10,11) == '' && substring({f},9,10) != '' && substring({f},4,5) == '-' && substring({f},7,8) == '-' && {digits}"
    leap=f'(({y} % 4 == 0 && {y} % 100 != 0) || {y} % 400 == 0)'
    days=f'if({m} == 2,if({leap},29,28),if({m} == 4 || {m} == 6 || {m} == 9 || {m} == 11,30,31))'
    valid=f'{y} >= 1 && {m} >= 1 && {m} <= 12 && {d} >= 1 && {d} <= {days}'
    past=f"Number(Date({f} + 'T23:59:59.999+10:00')) < Number(@now)"
    return f"=if({f} == '', 'No target recorded', if({shape},if({valid},if({past},'Past recorded date — confirm agreement','Recorded date — confirm agreement'),'Invalid calendar date — check target'),'Pending or non-ISO condition — not classified overdue'))"


def row_formatter(site, queue_path, readiness_path, assurance_path):
    def text(label, value):
        return {'elmType':'div','style':{'margin-bottom':'6px','white-space':'normal'},
                'children':[{'elmType':'span','style':{'font-weight':'600'},'txtContent':label+' '},
                            {'elmType':'span','txtContent':value}]}
    def link(label, href, condition=None):
        result={'elmType':'a','style':{'display':'block','padding':'6px 0'},'attributes':{'href':href,'target':'_blank'},'txtContent':label}
        if condition:result['style']['display']='=if('+condition+",'block','none')"
        return result
    children=[text('Case:','[$Title]'),text('CaseUID:','[$CaseUID]'),
              text('Status:','[$caseStatus]'),text('Next action:',"=if([$nextAction] == '', 'Missing — record an action when known', [$nextAction])"),
              text('Recorded role:',"=if([$accountableRole] == '', 'Missing — no assignment inferred', [$accountableRole])"),
              text('Target as recorded:','[$targetDate]'),text('Date check:',target_expression()),
              text('Linked document identities:','[$linkedDocumentUIDs]'),
              link('Open case and review/implementation links',"='"+queue_path+"/DispForm.aspx?ID=' + [$ID]"),
              link('Open recorded source snapshot', '[$sourceBaselineRef]',"indexOf([$sourceBaselineRef], '"+site+"/') == 0"),
              text('Source snapshot:',"=if([$sourceBaselineRef] == '', 'Missing — resolve before preparation', [$sourceBaselineRef])"),
              link('Open working draft — review required','[$evidenceDraftLink]',"indexOf([$evidenceDraftLink], '"+site+"/') == 0"),
              text('Draft/evidence reference:',"=if([$evidenceDraftLink] == '', 'Missing — no package inferred', [$evidenceDraftLink])"),
              link('Readiness findings for this CaseUID',"='"+readiness_path+"?FilterField1=CaseUID&FilterValue1=' + [$CaseUID]"),
              link('Decision and implementation history for this CaseUID',"='"+assurance_path+"?FilterField1=CaseUID&FilterValue1=' + [$CaseUID]")]
    return {'$schema':'https://developer.microsoft.com/json-schemas/sp/v2/row-formatting.schema.json',
            'hideSelection':False,'rowFormatter':{'elmType':'div','style':{'padding':'16px','margin':'8px 0','border':'1px solid #8a8886','width':'100%','display':'block'},'children':children}}
