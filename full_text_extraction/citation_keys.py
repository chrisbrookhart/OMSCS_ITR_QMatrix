"""Readable BibTeX-safe citation keys without guessing unextracted author names."""
from pathlib import Path
import re
import unicodedata
import models

TITLE_WORD_LIMIT = 4
DISAMBIGUATION_CHARACTERS = 8
UNKNOWN_YEAR = 'nd'
FALLBACK_TITLE = 'Paper'
FILENAME_SEPARATOR = ' - '
AUTHOR_SEPARATOR = ' and '
STOP_WORDS = frozenset(('a', 'an', 'the', 'of', 'and', 'for', 'to', 'in', 'on', 'with', 'using', 'from', 'by', 'at', 'as'))


def title_token(title: str) -> str:
    ascii_title = unicodedata.normalize('NFKD', title).encode('ascii', errors='ignore').decode()
    words = [word for word in re.findall(r'[A-Za-z0-9]+', ascii_title) if word.lower() not in STOP_WORDS]
    token = ''.join(word if word.isupper() else word.capitalize() for word in words[:TITLE_WORD_LIMIT])
    return token if token and token[0].isalpha() else FALLBACK_TITLE + token


def make_key(*, title: str, year: int | None, source_sha256: str, author: str | None = None) -> str:
    """A short source suffix keeps keys stable even when titles/years collide."""
    year_token = str(year) if year is not None else UNKNOWN_YEAR
    citation = f'{title_token(author)}{year_token}{title_token(title)}' if author else f'{title_token(title)}{year_token}'
    return f'{citation}_{source_sha256[:DISAMBIGUATION_CHARACTERS]}'


def from_filename(source: str, source_sha256: str) -> str | None:
    """Reuse Zotero's Author - Year - Title source label as an identifier only."""
    parts = Path(source).stem.split(FILENAME_SEPARATOR, maxsplit=2)
    if len(parts) != 3 or not re.fullmatch(r'\d{4}', parts[1].strip()):
        return None
    author = re.sub(r'\s+et al\.?$', '', parts[0].split(AUTHOR_SEPARATOR)[0]).strip()
    if not author or not parts[2].strip():
        return None
    return make_key(title=parts[2], year=int(parts[1]), author=author, source_sha256=source_sha256)


def from_paper(paper: models.Paper, source: str, source_sha256: str) -> str:
    named_key = from_filename(source, source_sha256)
    if named_key:
        return named_key
    return make_key(title=paper.title.value or Path(source).stem,
                    year=paper.publication_year.value, source_sha256=source_sha256)
