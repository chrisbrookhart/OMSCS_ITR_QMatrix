"""Synthetic coverage of malformed Unicode returned by PDF extraction."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import pdf_text
import storage


class PdfTextTests(unittest.TestCase):
    def test_surrogates_are_normalized_before_persistence(self) -> None:
        page = Mock()
        page.extract_text.return_value = 'Math \ud835; pair \ud835\udc00; normal α.'
        reader = Mock(pages=[page])
        with TemporaryDirectory() as temporary, patch('pdf_text.PdfReader', return_value=reader):
            folder = Path(temporary)
            pages, text = pdf_text.prepare(folder / 'synthetic.pdf', folder, 1000)
            self.assertEqual(pages, ['Math \ufffd; pair 𝐀; normal α.'])
            self.assertEqual((folder / storage.TEXT_FILE).read_text(encoding='utf-8'), text)
            self.assertIn('physical PDF page 1',
                          (folder / pdf_text.PDF_WARNINGS_FILE).read_text(encoding='utf-8'))

    def test_valid_unicode_is_preserved(self) -> None:
        text = 'Q-matrix α 𝐀 and ordinary text'
        self.assertEqual(pdf_text.normalize_page_text(text, 1), text)


if __name__ == '__main__':
    unittest.main()
