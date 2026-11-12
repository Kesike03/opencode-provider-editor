"""Small JSONC syntax tree and surgical object edits (standard library only)."""
from dataclasses import dataclass, field
import json
import re

from i18n import tr


@dataclass
class Node:
    start: int
    end: int
    value: object
    children: dict = field(default_factory=dict)
    keys: dict = field(default_factory=dict)
    commas: dict = field(default_factory=dict)


class JSONCError(ValueError):
    pass


class Parser:
    def __init__(self, text):
        self.text = text
        self.i = 1 if text.startswith('\ufeff') else 0

    def error(self, message):
        line = self.text.count('\n', 0, self.i) + 1
        col = self.i - self.text.rfind('\n', 0, self.i)
        raise JSONCError(tr('jsonc.location', message=message, line=line, column=col))

    def skip(self):
        while self.i < len(self.text):
            if self.text[self.i] in ' \t\r\n':
                self.i += 1
            elif self.text.startswith('//', self.i):
                end = self.text.find('\n', self.i)
                self.i = len(self.text) if end < 0 else end
            elif self.text.startswith('/*', self.i):
                end = self.text.find('*/', self.i + 2)
                if end < 0:
                    self.error(tr('jsonc.unclosed_comment'))
                self.i = end + 2
            else:
                break

    def string(self):
        try:
            value, end = json.JSONDecoder().raw_decode(self.text, self.i)
        except ValueError:
            self.error(tr('jsonc.bad_string'))
        if not isinstance(value, str):
            self.error(tr('jsonc.key_string'))
        self.i = end
        return value

    def value(self):
        self.skip()
        start = self.i
        if self.i >= len(self.text):
            self.error(tr('jsonc.missing_value'))
        char = self.text[self.i]
        if char in '{[':
            obj = char == '{'
            close = '}' if obj else ']'
            result = {} if obj else []
            node = Node(start, 0, result)
            self.i += 1
            self.skip()
            if self.text[self.i:self.i + 1] == close:
                self.i += 1
                node.end = self.i
                return node
            while True:
                self.skip()
                key_start = self.i
                if obj:
                    key = self.string()
                    if key in result:
                        self.error(tr('jsonc.duplicate_key'))
                    self.skip()
                    if self.text[self.i:self.i + 1] != ':':
                        self.error(tr('jsonc.missing_colon'))
                    self.i += 1
                else:
                    key = len(result)
                child = self.value()
                node.children[key] = child
                node.keys[key] = key_start
                if obj:
                    result[key] = child.value
                else:
                    result.append(child.value)
                self.skip()
                if self.text[self.i:self.i + 1] == ',':
                    node.commas[key] = self.i
                    self.i += 1
                    self.skip()
                    if self.text[self.i:self.i + 1] != close:
                        continue
                elif self.text[self.i:self.i + 1] != close:
                    self.error(tr('jsonc.missing_comma'))
                if self.text[self.i:self.i + 1] != close:
                    self.error(tr('jsonc.missing_close'))
                self.i += 1
                node.end = self.i
                return node
        if char == '"':
            value = self.string()
        else:
            match = re.match(r'(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)', self.text[self.i:])
            if not match:
                self.error(tr('jsonc.invalid_value'))
            self.i += len(match[0])
            value = json.loads(match[0])
            if isinstance(value, float) and not __import__('math').isfinite(value):
                self.error(tr('jsonc.nonfinite'))
        return Node(start, self.i, value)

    def parse(self):
        try:
            node = self.value()
            self.skip()
            if self.i != len(self.text):
                self.error(tr('jsonc.trailing'))
            return node
        except RecursionError:
            self.error(tr('jsonc.too_deep'))


def loads(text):
    return Parser(text).parse().value


def _same(a, b):
    # Python considers True == 1; JSON does not.
    return type(a) is type(b) and a == b


def patch(text, path, value=None, delete=False):
    root = Parser(text).parse()
    node = root
    for index, key in enumerate(path[:-1]):
        if not isinstance(node.value, dict):
            raise JSONCError(tr('jsonc.parent_object'))
        if key not in node.children:
            if delete:
                return text
            wrapped = value
            for part in reversed(path[index + 1:]):
                wrapped = {part: wrapped}
            return patch(text, path[:index + 1], wrapped)
        node = node.children[key]
    if not isinstance(node.value, dict):
        raise JSONCError(tr('jsonc.parent_object'))
    key = path[-1]
    if key in node.children:
        child = node.children[key]
        if delete:
            edits = [(node.keys[key], child.end, '')]
            if key in node.commas:
                edits.append((node.commas[key], node.commas[key] + 1, ''))
            else:
                keys = list(node.children)
                pos = keys.index(key)
                if pos:
                    comma = node.commas[keys[pos - 1]]
                    edits.append((comma, comma + 1, ''))
            for start, end, replacement in sorted(edits, reverse=True):
                text = text[:start] + replacement + text[end:]
            return text
        if _same(child.value, value):
            return text
        if isinstance(child.value, dict) and isinstance(value, dict):
            for old in child.value:
                if old not in value:
                    text = patch(text, path + (old,), delete=True)
            for subkey, subval in value.items():
                text = patch(text, path + (subkey,), subval)
            return text
        replacement = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return text[:child.start] + replacement + text[child.end:]
    if delete:
        return text
    newline = '\r\n' if '\r\n' in text else '\n'
    line_start = text.rfind('\n', 0, node.start) + 1
    parent_indent = re.match(r'[ \t]*', text[line_start:])[0]
    indent = parent_indent + '  '
    if node.children:
        first = next(iter(node.children))
        prefix = text[text.rfind('\n', 0, node.keys[first]) + 1:node.keys[first]]
        if prefix and not prefix.strip():
            indent = prefix
    serialized = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)
    entry = json.dumps(key, ensure_ascii=False) + ': ' + serialized.replace('\n', newline + indent)
    # Insert before the closing brace; preceding comments stay byte-for-byte.
    pos = node.end - 1
    prefix = text[:pos]
    if node.children:
        last = next(reversed(node.children))
        if last not in node.commas:
            at = node.children[last].end
            prefix = prefix[:at] + ',' + prefix[at:]
    insertion = newline + indent + entry + newline + parent_indent
    return prefix + insertion + text[pos:]


class Document:
    def __init__(self, text):
        self.text = text
        self.data = loads(text)
        if not isinstance(self.data, dict):
            raise JSONCError(tr('jsonc.root_object'))
        if 'providers' in self.data:
            raise JSONCError(tr('jsonc.providers_format'))
        providers = self.data.get('provider', {})
        if not isinstance(providers, dict):
            raise JSONCError(tr('jsonc.provider_object'))
        for provider in providers.values():
            if not isinstance(provider, dict):
                raise JSONCError(tr('jsonc.provider_object'))
            for field_name in ('options', 'models'):
                if field_name in provider and not isinstance(provider[field_name], dict):
                    raise JSONCError(tr('jsonc.provider_field_object', field=field_name))
            for model in provider.get('models', {}).values():
                if not isinstance(model, dict):
                    raise JSONCError(tr('jsonc.model_object'))
                if 'limit' in model and not isinstance(model['limit'], dict):
                    raise JSONCError(tr('jsonc.limit_object'))

    def update(self, path, value=None, delete=False):
        text = patch(self.text, tuple(path), value, delete)
        updated = Document(text)
        self.text, self.data = updated.text, updated.data
