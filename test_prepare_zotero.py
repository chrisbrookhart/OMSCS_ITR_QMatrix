import tempfile
from pathlib import Path
import unittest
from zipfile import ZipFile

from candidate_workbook import read_rows
from prepare_rayyan import parse_export
from prepare_zotero import ris_record


class ZoteroTests(unittest.TestCase):
    def test_sparse_workbook_and_rich_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.xlsx'
            with ZipFile(path, 'w') as z:
                z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Records" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/sharedStrings.xml', '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Title</t></si><si><t>Abstract</t></si></sst>')
                z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row><row><c r="A2" t="inlineStr"><is><r><t>Synthetic </t></r><r><t>title</t></r></is></c></row></sheetData></worksheet>')
            self.assertEqual(read_rows(path), [{'Title': 'Synthetic title', 'Abstract': ''}])

    def test_ris_multiline_and_authors(self):
        from parse_records import SourceRecord
        row = {name: '' for name in ['ID','Sept ID','Year','Title','Authors','Venue','Document type','Found in','DOI','Abstract','Keywords','Language','Screening flags','Stage','Assigned to','Screener 1','Screener 2','Decision','Exclusion reason','Excluded at stage','Notes']}
        row.update({'ID':'1', 'Title':'Synthetic title', 'Authors':'Example, First (123); Example, Second', 'Found in':'Scopus; ERIC', 'Abstract':'First line\nER  - misleading text', 'Document type':'Conference Paper'})
        fields = parse_export(ris_record(SourceRecord.from_csv_row(row)), 'ris')[0]
        self.assertEqual(fields['AU'], ['Example, First', 'Example, Second'])
        self.assertEqual(fields['TY'], ['CPAPER'])
        self.assertEqual(fields['AB'], ['First line ER  - misleading text'])


if __name__ == '__main__':
    unittest.main()
