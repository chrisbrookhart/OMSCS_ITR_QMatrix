"""Prepare physical PDF pages without truncating the document."""
from pathlib import Path
import logging
from pypdf import PdfReader
import storage

PDF_LOGGER_NAME = 'pypdf'
PDF_WARNINGS_FILE = 'pdf_warnings.log'


def normalize_page_text(text: str, page_number: int) -> str:
    """Combine surrogate pairs and replace invalid PDF character mappings."""
    normalized = text.encode('utf-16', errors='surrogatepass').decode('utf-16', errors='replace')
    if normalized != text:
        logging.getLogger(PDF_LOGGER_NAME).warning(
            'Normalized invalid Unicode surrogate text on physical PDF page %s.', page_number)
    return normalized


def read_pdf(path: Path, warnings_path: Path) -> list[str]:
    logger = logging.getLogger(PDF_LOGGER_NAME)
    handler = logging.FileHandler(warnings_path, encoding='utf-8')
    previous_propagate = logger.propagate
    logger.addHandler(handler)
    logger.propagate = False
    try:
        return [normalize_page_text(page.extract_text() or '', number)
                for number, page in enumerate(PdfReader(path).pages, 1)]
    finally:
        logger.removeHandler(handler)
        logger.propagate = previous_propagate
        handler.close()


def prepare(path: Path, folder: Path, maximum_characters: int) -> tuple[list[str], str]:
    pages = read_pdf(path, folder / PDF_WARNINGS_FILE)
    text = '\n\n'.join(f'[PDF PAGE {number}]\n{page}' for number, page in enumerate(pages, 1))
    storage.write_json(folder / storage.PAGES_FILE, pages)
    (folder / storage.TEXT_FILE).write_text(text, encoding='utf-8')
    if not any(page.strip() for page in pages):
        raise ValueError('No extractable PDF text; OCR required')
    if len(text) > maximum_characters:
        raise ValueError('Paper exceeds character limit; not truncated or sent')
    return pages, text
