#!/usr/bin/env python3
"""Conservative source-header proposals; never infer authority or mint identities."""
import re
import uuid


_DOCUMENT_IDENTIFIER = re.compile(
    r'Document\s+(?:Number|No\.?)\s*:?\s*([A-Za-z][A-Za-z0-9./_-]+)', re.I
)


def propose(header, catalogue):
    # Caller supplies freshly extracted first-page text from hash-verified bytes.
    first_page = header
    header = first_page[:1500]
    aliases = set(_DOCUMENT_IDENTIFIER.findall(header))
    editions = set(re.findall(r'Version\s*(?:No\.?|Number)?\s*:?\s*([0-9]+(?:\.[0-9]+)*)', header, re.I))
    if len(aliases) != 1:
        return {'state': 'unresolved', 'reason': 'missing_or_ambiguous_document_header'}
    alias = next(iter(aliases))
    # The header window establishes eligibility, but must not hide another
    # identifier later on the supplied first page or truncate one at its edge.
    if set(_DOCUMENT_IDENTIFIER.findall(first_page)) != {alias}:
        return {'state': 'unresolved', 'sourceAlias': alias,
                'reason': 'document_identifiers_conflict_on_first_page'}
    matches = [r for r in catalogue if r.get('sourceDocumentId') == alias]
    if len(matches) != 1:
        return {'state': 'unresolved', 'sourceAlias': alias, 'reason': 'catalogue_alias_not_unique_or_absent'}
    try:
        uid = uuid.UUID(matches[0]['DocumentUID'])
        if not uid.int:
            raise ValueError('Empty UUID')
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'state': 'unresolved', 'sourceAlias': alias, 'reason': 'invalid_existing_identity'}
    if len(editions) != 1:
        return {'state': 'unresolved', 'sourceAlias': alias, 'reason': 'missing_or_ambiguous_printed_edition'}
    edition = next(iter(editions))
    encoded = re.search(r'-V(\d+(?:\.\d+)*)(?:-|$)', alias, re.I)
    def numeric_version(value):
        parts = [int(v) for v in value.split('.')]
        while len(parts) > 1 and parts[-1] == 0:
            parts.pop()
        return parts
    page_editions = re.findall(r'Version\s*(?:No\.?|Number)?\s*:?\s*([0-9]+(?:\.[0-9]+)*)', first_page, re.I)
    if len({tuple(numeric_version(value)) for value in page_editions}) > 1:
        return {'state': 'unresolved', 'sourceAlias': alias, 'reason': 'printed_editions_conflict_on_first_page'}
    if encoded and numeric_version(encoded[1]) != numeric_version(edition):
        return {'state': 'unresolved', 'sourceAlias': alias, 'reason': 'printed_and_encoded_editions_differ'}
    return {'state': 'exact', 'sourceAlias': alias, 'existingDocumentUID': str(uid),
            'sourceEdition': edition, 'catalogueItemId': matches[0]['Id']}
