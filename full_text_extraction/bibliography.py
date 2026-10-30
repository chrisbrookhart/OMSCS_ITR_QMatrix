"""Local BibTeX metadata and exact, auditable PDF-to-entry associations."""
from pathlib import Path
import re

import bibtexparser
from bibtexparser import bparser, latexenc

import models
import storage

KEY_FIELD = 'ID'
TYPE_FIELD = 'ENTRYTYPE'
TITLE_FIELD = 'title'
AUTHORS_FIELD = 'author'
YEAR_FIELD = 'year'
ABSTRACT_FIELD = 'abstract'
DOI_FIELD = 'doi'
URL_FIELD = 'url'
JOURNAL_FIELD = 'journal'
BOOKTITLE_FIELD = 'booktitle'
FILE_FIELD = 'file'
ALIASES_FIELD = 'ids'
METADATA_FILE = 'bibliography.json'
METADATA_PATHS = ('title', 'doi', 'publication_year')


def load_entries(paths: list[Path]) -> list[models.BibliographicMetadata]:
    entries: dict[str, models.BibliographicMetadata] = {}
    for path in paths:
        parser = bparser.BibTexParser(common_strings=True, ignore_nonstandard_types=False)
        content = path.read_bytes()
        digest = storage.digest_bytes(content)
        database = parser.parse(content.decode('utf-8-sig'), partial=False)
        for entry in database.entries:
            fields = {key: latexenc.latex_to_unicode(str(value)) for key, value in entry.items()
                      if key not in (KEY_FIELD, TYPE_FIELD)}
            metadata = models.BibliographicMetadata(citation_key=entry[KEY_FIELD], fields=fields,
                source=str(path.resolve()), source_sha256=digest)
            previous = entries.get(metadata.citation_key)
            if previous is not None and previous.fields != fields:
                raise ValueError(f'Conflicting BibTeX entries for key {metadata.citation_key}')
            entries[metadata.citation_key] = metadata
    return list(entries.values())


def normalized_title(value: str) -> str:
    return ''.join(character for character in value.casefold() if character.isalnum())


def normalized_doi(value: str) -> str:
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.IGNORECASE).casefold()


def exact_source_match(entry: models.BibliographicMetadata, source: str, key: str | None) -> bool:
    if key is not None:
        return entry.citation_key == key
    stem = Path(source).stem.casefold()
    aliases = re.split(r'[,;\s]+', entry.fields.get(ALIASES_FIELD, '').casefold())
    files = entry.fields.get(FILE_FIELD, '').replace('\\', '/').casefold()
    return entry.citation_key.casefold() == stem or stem in aliases or Path(source).name.casefold() in files


def match_entry(entries: list[models.BibliographicMetadata], source: str, pages: list[str],
                key: str | None = None) -> models.BibliographicMetadata | None:
    # Prefer explicit associations over document-text matching; never use LLM metadata.
    candidates = [entry for entry in entries if exact_source_match(entry, source, key)]
    basis = 'source_map_or_filename'
    if not candidates and key is None:
        first_page = ''.join((pages[0] if pages else '').casefold().split())
        candidates = [entry for entry in entries if entry.fields.get(DOI_FIELD)
                      and normalized_doi(entry.fields[DOI_FIELD]) in first_page]
        basis = 'doi_on_first_pdf_page'
    if not candidates and key is None:
        beginning = normalized_title(' '.join(pages[:2]))
        candidates = [entry for entry in entries if entry.fields.get(TITLE_FIELD)
                      and normalized_title(entry.fields[TITLE_FIELD]) in beginning]
        basis = 'exact_title_in_first_two_pdf_pages'
    return select_candidate(candidates, source, pages, basis)


def select_candidate(candidates: list[models.BibliographicMetadata], source: str, pages: list[str],
                      basis: str) -> models.BibliographicMetadata | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0].model_copy(update={'match_basis': basis})
    dois = {normalized_doi(entry.fields.get(DOI_FIELD, '')) for entry in candidates}
    identities = {(normalized_title(entry.fields.get(TITLE_FIELD, '')),
                   normalized_title(entry.fields.get(AUTHORS_FIELD, '')), entry.fields.get(YEAR_FIELD, ''))
                  for entry in candidates}
    if len(dois - {''}) > 1 or (not (len(dois) == 1 and '' not in dois)
                               and not (len(identities) == 1 and next(iter(identities))[0])):
        raise ValueError(f'Ambiguous BibTeX association for {source}; provide an explicit source map')
    beginning = normalized_title(' '.join(pages[:2]))
    ordered = sorted(candidates, key=lambda entry: candidate_priority(entry, beginning))
    return ordered[0].model_copy(update={'match_basis': basis + '; duplicate identity, preferred exact title and complete metadata',
        'alternative_keys': [entry.citation_key for entry in ordered[1:]]})


def candidate_priority(entry: models.BibliographicMetadata, beginning: str) -> tuple[int, int, int, str]:
    title = normalized_title(entry.fields.get(TITLE_FIELD, ''))
    completeness = sum(bool(value) for key, value in entry.fields.items() if key != FILE_FIELD)
    return (-int(bool(title) and title in beginning), -int(bool(entry.fields.get(ABSTRACT_FIELD))),
            -completeness, entry.citation_key)


def citation(metadata: models.BibliographicMetadata | None) -> str | None:
    if metadata is None:
        return None
    fields = metadata.fields
    authors = fields.get(AUTHORS_FIELD, '').replace(' and ', '; ')
    year = fields.get(YEAR_FIELD)
    creator = f'{authors} ({year})' if authors and year else authors or year
    parts = [creator, fields.get(TITLE_FIELD), fields.get(JOURNAL_FIELD) or fields.get(BOOKTITLE_FIELD),
             fields.get(DOI_FIELD)]
    return '. '.join(part.rstrip('.') for part in parts if part) or metadata.citation_key
