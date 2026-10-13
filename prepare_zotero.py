"""Convert combined candidates to a local Zotero RIS import; no filtering or deduplication."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from candidate_workbook import DEFAULT_INPUT
from parse_records import read_records, update_records


def ris_record(record):
    kind = record.document_type.casefold()
    item_type = ('CPAPER' if 'conference' in kind else 'CHAP' if 'chapter' in kind
                 else 'BOOK' if kind == 'book' else 'THES' if 'dissertation' in kind or 'thesis' in kind
                 else 'JOUR' if 'article' in kind or 'review' in kind else 'GEN')
    lines = [f'TY  - {item_type}']

    def add(tag, value):
        if value:
            # Keep multiline values in one RIS field; prevent text becoming tags.
            lines.append(f'{tag}  - ' + re.sub(r'\s*[\r\n]+\s*', ' ', str(value)))

    add('ID', record.id)
    add('TI', record.title)
    for author in record.authors:
        add('AU', re.sub(r'\s*\(\d+\)$', '', author))
    add('T2', record.venue)
    add('PY', record.year)
    add('DO', record.doi)
    add('AB', record.abstract)
    add('LA', record.language)
    for keyword in record.keywords:
        add('KW', keyword)
    for label in record.labels:
        add('KW', 'Suggested label: ' + label.value)
    for field, value in vars(record).items():
        if field in ('id', 'sept_id', 'document_type', 'databases', 'screening_flags', 'stage',
                     'assigned_to', 'screener_1', 'screener_2', 'decision', 'exclusion_reason',
                     'excluded_at_stage', 'notes') and value:
            add('N1', field + ': ' + ('; '.join(value) if isinstance(value, tuple) else value))
    add('N1', 'Source: combined candidate workbook; label tags are keyword suggestions requiring review.')
    lines.append('ER  - ')
    return '\n'.join(lines) + '\n\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    records = update_records(read_records(args.input))
    if not records or any(not record.title.strip() for record in records):
        raise ValueError('Empty candidate set or missing title')
    directory = args.output / datetime.now().strftime('zotero_%Y%m%d_%H%M%S_%f')
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'candidates.ris').write_text(''.join(map(ris_record, records)), encoding='utf-8')
    audit = {'source': str(args.input), 'source_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
             'records': len(records), 'missing_abstracts': sum(not r.abstract.strip() for r in records),
             'missing_dois': sum(not r.doi.strip() for r in records),
             'document_types': dict(Counter(r.document_type for r in records)),
             'database_memberships': dict(Counter(d for r in records for d in r.databases)),
             'filtering': False, 'deduplication': False, 'labels': 'Existing keyword heuristics'}
    (directory / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(f'Wrote {len(records)} records to {directory / "candidates.ris"}')


if __name__ == '__main__':
    main()
