"""Convert explicit literal collector bindings to solution environment parameters."""
from copy import deepcopy
import re


def parameterise(flow, variables):
    result = deepcopy(flow)
    definition = result['properties']['definition']
    parameters = definition.setdefault('parameters', {})
    counts = {}
    for schema, value in variables.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]+', schema) or not isinstance(value, str) or not value:
            raise ValueError('Explicit schema and nonempty text value required')
        name = schema
        count = 0
        def visit(node):
            nonlocal count
            if isinstance(node, dict):
                return {k: visit(v) for k, v in node.items()}
            if isinstance(node, list):
                return [visit(v) for v in node]
            if isinstance(node, str) and not node.startswith('@') and value in node:
                count += 1
                return node.replace(value, "@{parameters('" + name + "')}")
            return node
        for section in ('actions', 'triggers'):
            definition[section] = visit(definition[section])
        if count:
            parameters[name] = {'type': 'String', 'defaultValue': value,
                                'metadata': {'schemaName': schema}}
            counts[schema] = count
    if not counts:
        raise ValueError('No exact literal binding matched')
    definition['contentVersion'] = '1.2.0.0'
    return result, counts
