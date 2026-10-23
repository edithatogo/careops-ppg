"""Read-only content presence checks; never approve or advance a document."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.ppg_structured_content import validate_modules

STEPS = {'draft', 'review', 'approval', 'publication'}
MODIFIERS = {'documentType', 'site', 'population', 'service', 'capability'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def evaluate(definition, records, document_uid, source_edition, context, step):
    validate_modules(definition)
    if step not in STEPS or not document_uid or not source_edition:
        raise ValueError('Exact document, edition and supported progression step required')
    if not isinstance(context, dict) or set(context)-MODIFIERS:
        raise ValueError('Unknown applicability context')
    for values in context.values():
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError('Applicability values must be explicit nonblank string lists')
    keys = [r['ContentKey'] for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate content identity')
    if any(r['DocumentUID'] != document_uid or r['SourceEditionKey'] != source_edition for r in records):
        raise ValueError('Mixed document or edition; reconcile before evaluation')
    module_keys = {m['key'] for m in definition['modules']}
    row_modifiers = {}
    for r in records:
        modifiers = r.get('OptionalModifiers')
        if isinstance(modifiers, str):
            try:
                modifiers = json.loads(modifiers) if modifiers.strip() else {}
            except json.JSONDecodeError as error:
                raise ValueError('Malformed block modifiers; reconcile before evaluation') from error
        modifiers = {} if modifiers is None else modifiers
        if not isinstance(modifiers, dict) or set(modifiers)-MODIFIERS:
            raise ValueError('Unknown block modifier')
        for values in modifiers.values():
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError('Block modifiers require nonempty string lists')
        row_modifiers[r['ContentKey']] = modifiers
        if r.get('ReviewedModule') and r['ReviewedModule'] not in module_keys:
            raise ValueError('Unknown reviewed module')
    results, seen = [], set()
    for rule in definition.get('rules', []):
        rid = rule.get('ruleId')
        if not isinstance(rid, str) or not rid.strip() or rid in seen:
            raise ValueError('Missing or duplicate rule identity')
        seen.add(rid)
        status = rule['status']
        if status not in {'proposed', 'verified_required', 'verified_conditional'}:
            raise ValueError('Unknown content rule status')
        steps = rule.get('progressionSteps')
        if not isinstance(steps, list) or not steps or set(steps)-STEPS or len(steps) != len(set(steps)):
            raise ValueError('Explicit progression steps required')
        conditions = rule.get('conditions', {})
        if not isinstance(conditions, dict) or set(conditions)-MODIFIERS:
            raise ValueError('Unknown rule condition')
        if status == 'verified_required' and conditions:
            raise ValueError('Conditional rules must declare conditional status')
        if status == 'verified_conditional' and not conditions:
            raise ValueError('Conditional rule requires applicability conditions')
        for values in conditions.values():
            if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError('Condition values must be nonempty string lists')
        if status != 'proposed':
            sha = rule['authorityEvidence'].get('sha256', '')
            if (rule.get('templateVerified') is not True or len(sha) != 64
                    or any(c not in '0123456789abcdef' for c in sha)):
                raise ValueError('Verified rule requires exact authority/template evidence')
        eligible, unresolved_content = [], []
        for r in records:
            if (r.get('ReviewedModule') != rule['moduleKey']
                    or r.get('BlockReviewState') != 'Reviewed'
                    or not isinstance(r.get('ReviewText'), str) or not r['ReviewText'].strip()):
                continue
            modifiers = row_modifiers[r['ContentKey']]
            if any(context.get(k) and not set(v).intersection(context[k]) for k, v in modifiers.items()):
                continue
            if any(not context.get(k) for k in modifiers):
                unresolved_content.append(r['ContentKey'])
            else:
                eligible.append(r['ContentKey'])
        missing = [k for k in conditions if not context.get(k)]
        excluded = any(context.get(k) and not set(values).intersection(context[k])
                       for k, values in conditions.items())
        if status == 'proposed':
            result = 'unverified_rule'
        elif step not in steps:
            result = 'not_due_at_step'
        elif excluded:
            result = 'not_applicable'
        elif missing or (not eligible and unresolved_content):
            result = 'unknown_applicability'
        else:
            result = 'present' if eligible else 'missing_reviewed_content'
        results.append(dict(ruleId=rid, moduleKey=rule['moduleKey'], result=result,
                            missingContext=missing, reviewedContentKeys=eligible,
                            unresolvedContentKeys=unresolved_content,
                            authorityEvidence=rule.get('authorityEvidence'),
                            progressionSteps=steps))
    blocked = any(r['result'] in {'unverified_rule', 'unknown_applicability',
                                 'missing_reviewed_content'} for r in results)
    qualified = definition.get('requiredness') == 'verified' and bool(results)
    return dict(schemaVersion=1, kind='read_only_content_presence', documentUID=document_uid,
                sourceEditionKey=source_edition, moduleVersion=definition['moduleVersion'],
                definitionSHA256=digest(definition), recordsSHA256=digest(records),
                context=context, progressionStep=step, results=results,
                ruleSetQualified=qualified,
                readiness='needs_resolution' if blocked else ('presence_checks_clear' if qualified else 'unverified_rules'),
                draftEditingAllowed=True, lifecycleChanged=False, humanDecision=None,
                policyApproved=False, publicationAuthorised=False, notificationsEnabled=False,
                limitations=['Presence is not clinical completeness, approval or permission to progress.',
                             'Only explicitly reviewed module/text counts; proposals and retained source text do not silently satisfy rules.',
                             'Non-text content and missing authority require explicit review; no source or reviewer fields are modified.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    value = evaluate(data['definition'], data['records'], data['documentUID'],
                     data['sourceEditionKey'], data['context'], data['progressionStep'])
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
