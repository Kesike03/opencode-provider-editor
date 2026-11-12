import ast
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app import EXAMPLE_EN, EXAMPLE_ZH, example_text
from core import (MODEL_FIELDS, PROVIDER_FIELDS, build_provider, diagnose, fetch_model_ids,
                  key_source, mask, models_endpoint, parse_field)
from i18n import CATALOG, LANGUAGES, default_language, get_language, set_language, tr
from jsonc_editor import Document, JSONCError, loads


PLACEHOLDER = re.compile(r'%\((\w+)\)[sd]')
HAN = re.compile(r'[\u4e00-\u9fff]')
ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def tearDown(self):
        set_language('zh')

    def test_languages_have_identical_keys(self):
        self.assertEqual(set(CATALOG), set(LANGUAGES))
        self.assertEqual(set(CATALOG['zh']), set(CATALOG['en']))

    def test_placeholders_match(self):
        for key, chinese in CATALOG['zh'].items():
            english = CATALOG['en'][key]
            self.assertEqual(set(PLACEHOLDER.findall(chinese)), set(PLACEHOLDER.findall(english)), key)

    def test_english_catalog_has_no_chinese(self):
        for key, value in CATALOG['en'].items():
            self.assertIsNone(HAN.search(value), key)

    def test_every_editable_field_has_help(self):
        for field in PROVIDER_FIELDS + MODEL_FIELDS:
            self.assertIn('help.' + field, CATALOG['zh'])
            self.assertIn('help.' + field, CATALOG['en'])

    def test_all_static_source_keys_exist(self):
        for filename in ('app.py', 'core.py', 'dialogs.py', 'jsonc_editor.py'):
            tree = ast.parse((ROOT / filename).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                if not isinstance(func, ast.Name) or func.id != 'tr':
                    continue
                key = node.args[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    self.assertIn(key.value, CATALOG['zh'], filename)

    def test_language_state_and_fallback(self):
        set_language('en')
        self.assertEqual(get_language(), 'en')
        self.assertEqual(tr('core.masked', prefix='abcd', length=8), 'abcd… (length 8)')
        self.assertEqual(tr('missing.key'), 'missing.key')
        with self.assertRaises(ValueError):
            set_language('fr')

    def test_example_matches_language(self):
        set_language('zh')
        self.assertEqual(example_text(), EXAMPLE_ZH)
        set_language('en')
        self.assertEqual(example_text(), EXAMPLE_EN)

    def test_default_language_detection(self):
        with patch.dict(os.environ, {'OPENCODE_EDITOR_LANG': 'en'}, clear=True):
            with patch('i18n.locale.getlocale', return_value=(None, None)):
                self.assertEqual(default_language(), 'en')
        with patch.dict(os.environ, {'OPENCODE_EDITOR_LANG': 'en-US'}, clear=True):
            with patch('i18n.locale.getlocale', return_value=(None, None)):
                self.assertEqual(default_language(), 'en')
        with patch.dict(os.environ, {'LANG': 'zh_CN.UTF-8'}, clear=True):
            with patch('i18n.locale.getlocale', return_value=(None, None)):
                self.assertEqual(default_language(), 'zh')
        with patch.dict(os.environ, {}, clear=True):
            with patch('i18n.locale.getlocale', return_value=(None, None)):
                self.assertEqual(default_language(), 'zh')
        with patch.dict(os.environ, {}, clear=True):
            with patch('i18n.locale.getlocale', return_value=('English_United States', '1252')):
                self.assertEqual(default_language(), 'en')
        with patch.dict(os.environ, {}, clear=True):
            with patch('i18n.locale.getlocale', return_value=('Chinese (Simplified)_China', '936')):
                self.assertEqual(default_language(), 'zh')


class LocalizedMessageTests(unittest.TestCase):
    def setUp(self):
        set_language('en')

    def tearDown(self):
        set_language('zh')

    def test_core_messages(self):
        self.assertEqual(mask('abcdefgh'), 'abcd… (length 8)')
        self.assertIn('Unconfirmed', key_source('p', {}))
        with self.assertRaisesRegex(ValueError, 'Choose true or false'):
            parse_field('reasoning', '1')
        with self.assertRaisesRegex(ValueError, 'Provider IDs may contain only'):
            build_provider('UPPER', 'x', 'https://a.test/v1', '', [], {})
        with self.assertRaisesRegex(ValueError, 'valid http'):
            models_endpoint('{env:URL}')
        with self.assertRaisesRegex(ValueError, 'unexpanded key reference'):
            fetch_model_ids('https://relay.test/v1', '{env:KEY}')

    def test_jsonc_messages(self):
        with self.assertRaisesRegex(JSONCError, 'Duplicate key'):
            loads('{"a":1,"a":2}')
        with self.assertRaisesRegex(JSONCError, 'line 1, column'):
            loads('[1,,]')
        with self.assertRaisesRegex(JSONCError, 'newer providers configuration'):
            Document('{"providers":{}}')

    def test_diagnostics_use_language_neutral_levels(self):
        doc = Document('{"disabled_providers":["p"], "provider":{"p":{"models":{"m":{"reasoning":false,"interleaved":true,"limit":{"context":100,"output":200}}}}}}')
        rows = diagnose(doc.data)
        self.assertLessEqual({row[0] for row in rows}, {'error', 'warning', 'info', 'note'})
        report = '\n'.join(row[2] for row in rows)
        self.assertIn('This provider is listed in disabled_providers', report)
        self.assertIn('A reasoning-content field is set', report)
        self.assertIn('output limit is greater', report)
        self.assertIn('Offline checks cannot confirm', report)
        self.assertIsNone(HAN.search(report))


if __name__ == '__main__':
    unittest.main()
