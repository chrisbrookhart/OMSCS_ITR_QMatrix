"""Read the combined candidate workbook without optional Excel dependencies."""
from pathlib import Path
import posixpath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

DEFAULT_INPUT = Path('input/20261009/Candidate Records - Final Search.xlsx')
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_rows(path: Path) -> list[dict[str, str]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = workbook.findall('s:sheets/s:sheet', NS)
        sheet = next((s for s in sheets if s.get('name') == 'Records'), None)
        if sheet is None:
            raise ValueError('Workbook must contain a Records worksheet')
        rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in relationships if r.get('Id') == rid)
        member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in item.findall('.//s:t', NS))
                       for item in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        rows = []
        for row in ET.fromstring(archive.read(member)).findall('s:sheetData/s:row', NS):
            values = {}
            for cell in row.findall('s:c', NS):
                column = ''.join(c for c in cell.get('r', '') if c.isalpha())
                value = cell.findtext('s:v', '', NS)
                if cell.get('t') == 's':
                    value = strings[int(value)]
                elif cell.get('t') == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                values[column] = value
            if not rows or any(values.values()):
                rows.append(values)
        if not rows:
            raise ValueError('Records worksheet is empty')
        headers = rows[0]
        if len(set(headers.values())) != len(headers):
            raise ValueError('Duplicate worksheet headers')
        return [{header: row.get(col, '') for col, header in headers.items()} for row in rows[1:]]
