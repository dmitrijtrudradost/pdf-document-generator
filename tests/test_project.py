import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import AppError
from core.loaders.csv_loader import load_csv
from core.loaders.json_loader import load_json
from core.model import build_documents
from core.renderer import render_template
from core.selector import choose_documents


class DataLoadingTests(unittest.TestCase):
    def test_json_formats_and_invalid_json(self):
        examples = [
            ([{'invoice_id': 'A'}], 'A'),
            ({'invoices': [{'invoice_id': 'B'}]}, 'B'),
            ({'C': {'total': 1}}, 'C'),
            ({'invoice_id': 'D', 'items': [{'name': 'item'}]}, 'D'),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.json'
            for data, expected in examples:
                with self.subTest(expected=expected):
                    path.write_text(json.dumps(data), encoding='utf-8')
                    records, skipped = load_json(path)
                    self.assertEqual(records[0]['invoice_id'], expected)
                    self.assertEqual(skipped, 0)
            path.write_text('{invalid', encoding='utf-8')
            with self.assertRaises(AppError):
                load_json(path)

    def test_csv_stdlib_reads_semicolon_and_cyrillic(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.csv'
            path.write_text('invoice_id;name\nA-1;Ромашка\n', encoding='utf-8')
            records, _, delimiter, engine = load_csv(path, {'csv_engine': 'stdlib'})
            self.assertEqual((delimiter, engine), (';', 'stdlib'))
            self.assertEqual(records[0]['name'], 'Ромашка')


class DocumentTests(unittest.TestCase):
    def test_template_escapes_values_and_expands_items(self):
        template = '<h1>{{ customer.name }}</h1>{{#items}}<p>{{ name }}</p>{{/items}}'
        record = {'customer': {'name': '<Клиент>'}, 'items': [{'name': 'A&B'}, {'name': 'C'}]}
        result, warnings = render_template(template, record, {})
        self.assertEqual(result, '<h1>&lt;Клиент&gt;</h1><p>A&amp;B</p><p>C</p>')
        self.assertEqual(warnings, [])

    def test_interactive_selection_recovers_after_invalid_input(self):
        documents, _ = build_documents([{'invoice_id': 'A'}, {'invoice_id': 'B'}], 'invoice_id', [])
        with patch('builtins.input', side_effect=['wrong', '2']), contextlib.redirect_stdout(io.StringIO()):
            selected = choose_documents(documents, 'test', 'invoice_id')
        self.assertEqual([doc.invoice_id for doc in selected], ['B'])


if __name__ == '__main__':
    unittest.main()
