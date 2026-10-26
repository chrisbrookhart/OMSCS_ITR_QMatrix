"""Aggregate extraction coverage without treating missing results as negative findings."""
import argparse
from collections import Counter
import csv
import json
import hashlib
from pathlib import Path


def write_coverage(run, fields=None):
    manifest = json.loads((run / 'manifest.json').read_text())
    if fields is None:
        taxonomy = run / 'taxonomy.json'
        fields = json.loads(taxonomy.read_text())['fields'] if taxonomy.exists() else json.loads((run / 'settings.json').read_text())['fields']
    selected = manifest['selected_pdfs']
    success = [p for p in manifest['papers'] if p['status'] == 'extracted']
    # Recheck saved extractions locally; never change model values or statuses.
    from legacy_review import evidence_warnings
    for paper in success:
        for stale in ('error', 'http_status', 'api_error_code'):
            paper.pop(stale, None)
        folder = run / paper['directory']
        if (folder / 'pages.json').exists():
            extraction = json.loads((folder / 'extraction.json').read_text())
            extraction['review_warnings'] = evidence_warnings(extraction['fields'], json.loads((folder / 'pages.json').read_text()), fields)
            (folder / 'extraction.json').write_text(json.dumps(extraction, ensure_ascii=False, indent=2) + '\n')
            paper['review_warnings'] = extraction['review_warnings']
    manifest['coverage_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['validation_script_sha256'] = hashlib.sha256((Path(__file__).parent / 'legacy_review.py').read_bytes()).hexdigest()
    (run / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    from export_typed import export_typed
    export_typed(run, fields, success)
    from legacy_review import append_review_rows
    review_rows = []
    for paper in success:
        extraction = json.loads((run / paper['directory'] / 'extraction.json').read_text())
        append_review_rows(review_rows, paper, extraction['fields'])
    if review_rows:
        with (run / 'review.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(review_rows[0]))
            writer.writeheader()
            writer.writerows(review_rows)
    failed = sum(p['status'] == 'error' for p in manifest['papers'])
    rows = []
    for name, definition in fields.items():
        counts = Counter()
        codes = Counter()
        supported = 0
        flagged = 0
        typed_present = 0
        structural_na = 0
        for paper in success:
            extraction = json.loads((run / paper['directory'] / 'extraction.json').read_text())
            field = extraction['fields'][name]
            counts[field['status']] += 1
            warnings = [w for w in extraction['review_warnings'] if w.startswith(name + ':')]
            flagged += bool(warnings)
            structural_na += field['status'] == 'not_applicable' and not warnings
            supported += field['status'] == 'reported' and bool(field['evidence']) and bool(field['value']) and not warnings
            typed = field.get('typed_value')
            numeric_kind = isinstance(definition, dict) and definition.get('value_type') in ('integer_conditions', 'numeric_conditions')
            has_typed = (any(o['values'] or o['minimum'] is not None or o['maximum'] is not None for o in typed or [])
                         if numeric_kind else typed is not None and typed != [])
            typed_present += field['status'] == 'reported' and has_typed
            if isinstance(definition, dict) and definition.get('value_type') == 'enum_list':
                codes.update(set(typed or []))
            else:
                codes.update(set(field.get('codes', [])))
        applicable = len(success) - structural_na
        rows.append({'field': name, 'rq': definition.get('rq', '') if isinstance(definition, dict) else '',
                     'selected': selected, 'extracted': len(success),
                     'reported': counts['reported'], 'not_reported': counts['not_reported'],
                     'not_applicable': counts['not_applicable'], 'accepted_structural_not_applicable': structural_na, 'unclear': counts['unclear'],
                     'failed_papers': failed, 'unprocessed_papers': selected - len(success) - failed,
                     'applicable_extracted': applicable, 'evidence_supported_reported': supported,
                     'flagged': flagged, 'typed_values_present': typed_present, 'reported_pct_applicable': round(100 * counts['reported'] / applicable, 1) if applicable else None,
                     'evidence_supported_pct_applicable': round(100 * supported / applicable, 1) if applicable else None,
                     'codes': dict(codes)})
    totals = Counter()
    for paper in manifest['papers']:
        usage = paper.get('usage') or {}
        for key in ('input_tokens', 'output_tokens', 'total_tokens'):
            totals[key] += usage.get(key, 0)
    report = {'selected': selected, 'extracted': len(success), 'failed': failed,
              'not_attempted': selected - len(success) - failed,
              'papers_with_warnings': sum(bool(p.get('review_warnings')) for p in success),
              'token_usage': dict(totals), 'fields': rows,
              'interpretation': 'Model-reported coverage and exact quote checks, not human-validated accuracy. All pilot candidates; no final eligibility filter.'}
    (run / 'coverage.json').write_text(json.dumps(report, indent=2) + '\n')
    with (run / 'coverage.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**row, 'codes': json.dumps(row['codes'])} for row in rows)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    result = write_coverage(args.run)
    print(f"Coverage saved: {result['extracted']}/{result['selected']} papers extracted")
