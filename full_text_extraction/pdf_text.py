"""Prepare physical PDF pages without truncating the document."""
from pathlib import Path
import logging
from pypdf import PdfReader
import storage


def read_pdf(path: Path, warnings_path: Path) -> list[str]:
    logger = logging.getLogger('pypdf')
    handler = logging.FileHandler(warnings_path, encoding='utf-8')
    previous_propagate = logger.propagate
    logger.addHandler(handler)
    logger.propagate = False
    try:
        return [page.extract_text() or '' for page in PdfReader(path).pages]
    finally:
        logger.removeHandler(handler)
        logger.propagate = previous_propagate
        handler.close()


def prepare(path: Path, folder: Path, maximum_characters: int) -> tuple[list[str], str]:
    pages = read_pdf(path, folder / 'pdf_warnings.log')
    text = '\n\n'.join(f'[PDF PAGE {number}]\n{page}' for number, page in enumerate(pages, 1))
    storage.write_json(folder / storage.PAGES_FILE, pages)
    (folder / storage.TEXT_FILE).write_text(text, encoding='utf-8')
    if not any(page.strip() for page in pages):
        raise ValueError('No extractable PDF text; OCR required')
    if len(text) > maximum_characters:
        raise ValueError('Paper exceeds character limit; not truncated or sent')
    return pages, text
