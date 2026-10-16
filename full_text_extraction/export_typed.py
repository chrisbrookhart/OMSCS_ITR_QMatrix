"""Flatten typed observations for spreadsheet review while retaining native JSON types."""
import csv
import json
from pathlib import Path


def export_typed(run: Path, fields, papers):
    native = []
    numeric = []
    for paper in papers:
        result = json.loads((run / paper['directory'] / 'extraction.json').read_text())['fields']
        for name, field in result.items():
            definition = fields[name]
            kind = definition.get('value_type') if isinstance(definition, dict) else None
            typed = field.get('typed_value')
            native.append({'source': paper['source'], 'field': name, 'status': field['status'],
                           'value_type': kind, 'typed_value': typed})
            if kind in ('integer_conditions', 'numeric_conditions'):
                for observation in typed or []:
                    for value in observation['values'] or [None]:
                        numeric.append({'source': paper['source'], 'field': name, 'status': field['status'],
                                        'value_type': kind, 'condition': observation['condition'],
                                        'measure': observation['measure'], 'unit': observation['unit'],
                                        'value': value, 'minimum': observation['minimum'],
                                        'maximum': observation['maximum'], 'context': field['value']})
    with (run / 'typed_values.jsonl').open('w', encoding='utf-8') as stream:
        for record in native:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    columns = ['source', 'field', 'status', 'value_type', 'condition', 'measure', 'unit',
               'value', 'minimum', 'maximum', 'context']
    with (run / 'numeric_observations.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(numeric)
