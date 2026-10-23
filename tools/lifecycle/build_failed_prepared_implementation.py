"""Compose an isolated fictional implementation-failure recording profile.

Offline only. Uses the existing schema and complete publication/frame/replay
checks. Recorded means the failure assertion was recorded, never implemented.
"""
from build_prepared_implementation import build as implementation_build
from build_operator_entry import _flatten


def build(publication, target, binding):
    result = implementation_build(publication, target, binding)
    actions = result['properties']['definition']['actions']
    validation = actions['Validate_implementation_input']['expression']
    original = "equals(triggerBody()?['text'],'Record implementation')"
    if validation.count(original) != 1:
        raise ValueError('Reviewed implementation action contract changed')
    actions['Validate_implementation_input']['expression'] = validation.replace(
        original, "equals(triggerBody()?['text'],'Record failed implementation')")
    payload = actions['Implementation_payload']['inputs']
    payload.update(Title='FICTIONAL failed implementation record',
        ConditionsState='Open',
        ConditionsNotes='FICTIONAL implementation failure remains unresolved; no completion or progression granted.',
        Summary='FICTIONAL implementation failure recording; no clinical rollout or effectiveness claim')
    receipt = actions['Native_implementation_receipt']['inputs']
    receipt.update(failureAssertionRecorded=True, conditionsRemainOpen=True)
    fields = result['properties']['definition']['triggers']['manual']['inputs']['schema']['properties']
    fields['text']['description'] = 'Enter Record failed implementation. Fictional recording only; conditions stay open.'
    fields['text_2']['title'] = 'Fictional failed action and reason'
    fields['text_4']['title'] = 'Fictional unresolved work and next action'
    # No new writer or accidental repair of another stage is allowed.
    writers = {name for name, action in _flatten(actions).items()
               if action.get('type') == 'OpenApiConnection'
               and action['inputs']['parameters'].get('parameters/method') != 'GET'}
    if writers != {'Create_implementation'}:
        raise ValueError('Failure recording must retain only the existing event writer')
    return result
