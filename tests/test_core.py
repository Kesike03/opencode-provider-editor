import unittest
from unittest.mock import patch as mock_patch
from urllib.error import HTTPError

from core import (build_provider, diagnose, fetch_model_ids, key_source, mask,
                  models_endpoint, parse_field)
from i18n import set_language
from jsonc_editor import Document, JSONCError, loads, patch


class JSONCTests(unittest.TestCase):
    def setUp(self):
        set_language('zh')

    def test_comments_strings_trailing_commas(self):
        text = '\ufeff{/* block */"url":"https://a//b", "text":"/* hi */ \\\"", "list":[true,null,], // tail\n}'
        self.assertEqual(loads(text), {'url': 'https://a//b', 'text': '/* hi */ "', 'list': [True, None]})

    def test_invalid_syntax(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":01}', '[1,,]', '{/*', '{} garbage', '{"a":1e999}', '{"a":}'):
            with self.subTest(text=text), self.assertRaises(JSONCError):
                loads(text)

    def test_noop_and_unknown_fields(self):
        text = '{\r\n // comment\r\n "provider": {}, "unknown": [1,2,],\r\n}'
        doc = Document(text)
        self.assertEqual(doc.text, text)
        doc.update(['provider', 'a.b/c', 'models', 'x.y/z', 'reasoning'], True)
        self.assertTrue(doc.data['provider']['a.b/c']['models']['x.y/z']['reasoning'])
        self.assertIn('"unknown": [1,2,]', doc.text)
        self.assertIn('// comment\r\n', doc.text)

    def test_patch_keeps_comments_and_order(self):
        text = '{"a": {"x": 1, /* x note */ "y": 2}, "z":3}'
        edited = patch(text, ('a',), {'x': 4, 'y': 2, 'new': False})
        self.assertIn('/* x note */ "y": 2', edited)
        self.assertLess(edited.index('"x"'), edited.index('"y"'))
        self.assertEqual(loads(edited), {'a': {'x': 4, 'y': 2, 'new': False}, 'z': 3})

    def test_delete_positions_and_trailing_comments(self):
        for text in ('{"a":1,"b":2,"c":3}', '{"a":1,"b":2,"c":3,}', '{"a":1/*a*/,"b":2//b\n,"c":3//c\n}'):
            for key in ('a', 'b', 'c'):
                edited = patch(text, (key,), delete=True)
                expected = {'a': 1, 'b': 2, 'c': 3}
                del expected[key]
                self.assertEqual(loads(edited), expected)
            for key in ('a', 'b', 'c'):
                text = patch(text, (key,), delete=True)
            self.assertEqual(loads(text), {})

    def test_append_after_line_comment(self):
        for text in ('{"a":1 // tail\n}', '{"a":1, // tail\n}', '{// empty\n}'):
            edited = patch(text, ('new',), '值')
            self.assertEqual(loads(edited)['new'], '值')
            self.assertIn('//', edited)

    def test_boolean_is_not_number(self):
        self.assertIs(loads(patch('{"a":1}', ('a',), True))['a'], True)

    def test_reject_incompatible_structure(self):
        for text in ('[]', '{"providers":{}}', '{"provider":[]}', '{"provider":{"p":{"models":{"m":{"limit":null}}}}}'):
            with self.assertRaises(JSONCError):
                Document(text)

    def test_user_style_config_round_trip(self):
        text = '''{
  "provider": {
    "openai": {
      "options": {"baseURL": "https://example.test/v1", "apiKey": "sk-example"},
      "models": {
        "gpt-6": {
          "name": "GPT-6 (Astra)",
          "limit": {"context": 1050000, "output": 128000},
          "options": {"store": false},
          "variants": {"low": {}, "medium": {}, "high": {}, "xhigh": {}, "max": {}}
        },
        "gpt-6-astra": {"name": "GPT-6 Astra", "variants": {"low": {}}}
      }
    }
  },
  "agent": {"build": {"options": {"store": false}}, "plan": {"options": {"store": false}}},
  "$schema": "https://opencode.ai/config.json"
}'''
        doc = Document(text)
        self.assertEqual(doc.text, text)
        doc.update(['provider', 'openai', 'models', 'gpt-6', 'reasoning'], True)
        doc.update(['provider', 'openai', 'models', 'gpt-6', 'interleaved'], {'field': 'reasoning_content'})
        doc.update(['provider', 'openai', 'options', 'headers'], {'X-Group': 'vip'})
        self.assertEqual(doc.data['provider']['openai']['models']['gpt-6']['options'], {'store': False})
        self.assertEqual(list(doc.data['provider']['openai']['models']['gpt-6']['variants']), ['low', 'medium', 'high', 'xhigh', 'max'])
        self.assertEqual(doc.data['agent']['build']['options']['store'], False)
        self.assertEqual(doc.data['provider']['openai']['models']['gpt-6-astra']['name'], 'GPT-6 Astra')
        self.assertLess(doc.text.index('"provider"'), doc.text.index('"agent"'))
        self.assertLess(doc.text.index('"agent"'), doc.text.index('"$schema"'))

    def test_add_delete_groups_models_and_undo_text(self):
        doc = Document('{// keep\n"agent":{"build":{}},"provider":{}}')
        starting = doc.text
        doc.update(['provider', 'custom'], build_provider('custom', '自定义', 'https://example.test/v1', '', ['m/one', 'm-two'], {'X-Group': 'vip'}))
        self.assertIn('// keep', doc.text)
        self.assertIn('"agent":{"build":{}}', doc.text)
        self.assertIn('"npm": "@ai-sdk/openai-compatible"', doc.text)
        self.assertEqual(list(doc.data['provider']['custom']['models']), ['m/one', 'm-two'])
        doc.update(['provider', 'custom', 'models', 'm/one'], delete=True)
        self.assertNotIn('m/one', doc.data['provider']['custom']['models'])
        doc.update(['provider', 'custom'], delete=True)
        self.assertEqual(doc.data['provider'], {})
        self.assertEqual(Document(starting).text, starting)

    def test_add_first_group_to_config_without_provider(self):
        doc = Document('{"$schema":"https://opencode.ai/config.json"}')
        doc.update(['provider', 'openai'], build_provider('openai', '', '', '', [], {}, native=True))
        self.assertEqual(doc.data['provider']['openai'], {})


class MetadataTests(unittest.TestCase):
    def setUp(self):
        set_language('zh')

    def test_key_sources(self):
        self.assertEqual(mask('abcdefgh'), 'abcd…（长度 8）')
        self.assertNotIn('abc', mask('abc'))
        auth = {'p': {'type': 'api', 'key': 'auth-secret'}}
        self.assertIn('auth.json / auth', key_source('p', {}, auth))
        self.assertIn('配置内联 / inli', key_source('p', {'options': {'apiKey': 'inline-secret'}}, auth))
        self.assertIn('未确认', key_source('p', {}))
        self.assertIn('配置引用', key_source('p', {'options': {'apiKey': '{env:KEY}'}}))

    def test_validation(self):
        for field, text in [('reasoning', '1'), ('limit.context', 'true'), ('limit.output', '0'), ('headers', '{"a":1}'), ('variants', '{"high":true}'), ('interleaved', '{"wrong":"x"}')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_field(field, text)
        self.assertEqual(parse_field('interleaved', '{"field":"reasoning_content"}'), {'field': 'reasoning_content'})
        self.assertEqual(parse_field('variants', '{"high":{"reasoningEffort":"high"}}')['high']['reasoningEffort'], 'high')

    def test_diagnostics(self):
        doc = Document('{"disabled_providers":["p"], "provider":{"p":{"models":{"m":{"reasoning":false,"interleaved":true,"limit":{"context":100,"output":200}}}}}}')
        report = '\n'.join(row[2] for row in diagnose(doc.data))
        self.assertIn('disabled_providers', report)
        self.assertIn('reasoning 为 false', report)
        self.assertIn('输出上限大于', report)
        self.assertIn('无法确认分组权限', report)

    def test_provider_wizard_validation(self):
        provider = build_provider('relay_vip-1', 'VIP', 'https://relay.test/v1', 'sk-abc', ['m/one'], {'X-Group': 'vip'})
        self.assertEqual(provider['options']['headers']['X-Group'], 'vip')
        self.assertEqual(build_provider('openai', '', '', '', [], {}, native=True), {})
        for pid in ('UPPER', 'a.b', '中转站', ''):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                build_provider(pid, 'x', 'https://a.test/v1', '', [], {})
        for ids in (['a', 'a'], ['a#b']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                build_provider('relay', 'x', 'https://a.test/v1', '', ids, {})
        with self.assertRaises(ValueError):
            build_provider('relay', '', '', '', [], {})
        with self.assertRaises(ValueError):
            build_provider('relay', 'x', 'https://a.test/v1', '', [], {'Authorization': 'a\r\nb'})

    def test_models_endpoint(self):
        self.assertEqual(models_endpoint('https://example.test/v1/'), 'https://example.test/v1/models')
        self.assertEqual(models_endpoint('https://example.test/v1/models'), 'https://example.test/v1/models')
        for bad in ('{env:URL}', 'file:///secret', 'https://user:pass@example.test/v1', 'https://example.test/v1?key=x'):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                models_endpoint(bad)

    def test_fetch_openai_models_and_auth(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, count):
                self.count = count
                return b'{"data":[{"id":"gpt-6"},{"id":"gpt-6"},{"id":"m/one"},{}]}'

        response = Response()
        with mock_patch('core.urlopen', return_value=response) as urlopen:
            ids = fetch_model_ids('https://relay.test/v1', 'sk-test', {'X-Group': 'vip'})
        self.assertEqual(ids, ['gpt-6', 'm/one'])
        request, = urlopen.call_args.args
        self.assertEqual(request.full_url, 'https://relay.test/v1/models')
        self.assertEqual(request.get_header('Authorization'), 'Bearer sk-test')
        self.assertEqual(request.get_header('X-group'), 'vip')
        self.assertEqual(response.count, 4 * 1024 * 1024 + 1)
        auth_error = HTTPError('https://relay.test/v1/models', 401, 'Unauthorized', {}, None)
        try:
            with mock_patch('core.urlopen', side_effect=auth_error):
                with self.assertRaisesRegex(ValueError, 'HTTP 401'):
                    fetch_model_ids('https://relay.test/v1', 'secret')
        finally:
            auth_error.close()
        with self.assertRaises(ValueError):
            fetch_model_ids('https://relay.test/v1', '{env:KEY}')

    def test_fetch_rejects_other_response_shapes(self):
        class Response:
            def __init__(self, raw):
                self.raw = raw

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, count):
                return self.raw

        for raw in (b'not json', b'{"models":[{"id":"x"}]}', b'{"data":[]}'):
            with mock_patch('core.urlopen', return_value=Response(raw)):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    fetch_model_ids('https://relay.test/v1')


if __name__ == '__main__':
    unittest.main()
