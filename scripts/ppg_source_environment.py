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
            if isinstance(node, str) and node.startswith('@'):
                # Replace only quoted WDL literals, preserving escaped quotes and
                # expressions. A URL and list binding may share one literal.
                def literal(match):
                    nonlocal count
                    text = match.group()[1:-1].replace("''", "'")
                    if value not in text:
                        return match.group()
                    count += 1
                    chunks = []
                    for index, part in enumerate(text.split(value)):
                        if index:
                            chunks.append("parameters('" + name + "')")
                        if part:
                            chunks.append("'" + part.replace("'", "''") + "'")
                    return chunks[0] if len(chunks) == 1 else 'concat(' + ','.join(chunks) + ')'
                return re.sub(r"'(?:[^']|'')*'", literal, node)
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
