"""Readable citation keys do not invent bibliographic facts."""
import unittest
import citation_keys
from test_extract import paper


class CitationKeyTests(unittest.TestCase):
    def test_title_year_and_stable_disambiguation(self) -> None:
        arguments = {'title': 'The generation of Q-matrices', 'year': 2024, 'source_sha256': 'abcdef0123456789'}
        key = citation_keys.make_key(**arguments)
        self.assertEqual(key, 'GenerationQMatrices2024_abcdef01')
        self.assertEqual(citation_keys.make_key(**arguments), key)
        self.assertNotEqual(citation_keys.make_key(**{**arguments, 'source_sha256': '12345678abcdef01'}), key)

    def test_unicode_punctuation_and_unknown_year(self) -> None:
        key = citation_keys.make_key(title='Q-mátrix: génération & refinement!', year=None, source_sha256='abcdef0123456789')
        self.assertEqual(key, 'QMatrixGenerationRefinementnd_abcdef01')
        self.assertRegex(key, r'^[A-Za-z][A-Za-z0-9_]+$')

    def test_zotero_filename_reuses_author_year_title_before_and_after_extraction(self) -> None:
        source = 'folder/Smith and Jones - 2024 - Q-matrix generation across domains.pdf'
        expected = 'Smith2024QMatrixGenerationAcross_abcdef01'
        self.assertEqual(citation_keys.from_filename(source, 'abcdef0123456789'), expected)
        self.assertEqual(citation_keys.from_paper(paper(), source, 'abcdef0123456789'), expected)

    def test_et_al_and_particles_are_preserved_without_guessing_surnames(self) -> None:
        source = 'de la Torre et al. - 2023 - Generating Q matrices.pdf'
        key = citation_keys.from_filename(source, 'abcdef0123456789')
        self.assertEqual(key, 'DeLaTorre2023GeneratingQMatrices_abcdef01')

    def test_no_invented_author_or_year_and_filename_fallback(self) -> None:
        result = paper()
        result.title.value = None
        key = citation_keys.from_paper(result, 'folder/q_matrix_design.pdf', 'abcdef0123456789')
        self.assertEqual(key, 'QMatrixDesignnd_abcdef01')


if __name__ == '__main__':
    unittest.main()
