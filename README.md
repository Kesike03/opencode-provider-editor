# OpenCode Config Editor

English | [Chinese](README.zh.md)

A local Python desktop app for editing OpenCode relay configurations in the `provider` format. It uses only the Python standard library and Tkinter, has no third-party dependencies, and starts no web service. Editing and checks run locally; a relay URL is contacted only when you click “Fetch model list from URL”.

## Run

Install Python 3.10 or newer, then run from this directory:

```powershell
py app.py
```

On macOS / Linux, run `python3 app.py`. Some Linux distributions require the `python3-tk` system package. The Windows Python installer must include Tcl/Tk.

## Language

The interface supports Chinese and English and can switch languages from the top-right corner at any time. Switching preserves the input text, current tab, model filter, selected group/model, and exported result. The default language is selected from `OPENCODE_EDITOR_LANG`, then `LC_ALL` / `LC_MESSAGES` / `LANG`, then the system locale; Chinese is used when none is recognized. You can also force a language:

```powershell
$env:OPENCODE_EDITOR_LANG='en'; py app.py
```

```bash
OPENCODE_EDITOR_LANG=en python3 app.py
```

## Usage

1. On the Import tab, paste the complete `opencode.json` / `opencode.jsonc` text and click “Read configuration”. You can also insert an example first. Even if the original text is `{}`, you can create the first group on the Edit tab.
2. On the Quick Edit tab, select a provider on the left (one provider represents one relay group). The list shows ID, name, and model count; “Group settings” on the right shows the full baseURL and masked key source. Selecting a model switches the right side to “Model capabilities & limits”; the two detail views are tabs.
3. Click “+ Add group” and choose either a built-in provider or a custom provider. In custom mode, enter the ID, name, and URL; the API key may be empty, and authentication can use addable/removable headers. Model ID rows are also addable/removable; “Fetch model list from URL” fills IDs for you to review. Both groups and models have Delete buttons with confirmation.
4. Select a group field, or search models by ID / name and select a capability field on the right. The `?` to the left of each field shows a localized description; double-click the field or click “Edit selected field”. Booleans use a checkbox; headers, interleaved, and variants accept JSONC input. Edits can be undone one at a time.
5. Review the Check tab for missing capability metadata, formatting, context limits, and enabled/disabled lists.
6. Click “Generate output”, then “Copy all”, and paste the result back into your configuration file. Old output is invalidated after an edit so stale text cannot be copied accidentally.

A field being undeclared and a field being `false` are different states. “Remove field (not declared)” in a dialog deletes the configuration entry so OpenCode can apply its default or inherited behavior. An empty string is written as an empty string, not removed. The Import tab keeps the originally pasted text and does not change with table edits; importing again uses that text as the source.

## Supported fields

| Level | Table field | Configuration location |
| --- | --- | --- |
| provider | name | `provider.<id>.name` |
| provider | baseURL, headers | `provider.<id>.options.baseURL / headers` |
| model | name, reasoning, tool_call, attachment, interleaved, variants | `provider.<id>.models.<model-id>.*` |
| model | limit.context, limit.output | `provider.<id>.models.<model-id>.limit.*` |

Existing IDs may contain dots, slashes, or Chinese characters; the program uses the real key path. New provider IDs are limited to lowercase letters, underscores, digits, and hyphens; new model IDs may contain slashes but not `#`. Other configuration entries (npm, options, modalities, plugins, permissions, etc.) are preserved. To change an existing ID, edit the input text and import again.

### Creating groups and fetching models

- “Based on a built-in provider” takes an existing provider ID such as `openai`; only the entered overrides are written, and no npm adapter is set. Duplicate IDs cannot be added; select the existing group to edit it.
- “Add a custom provider” requires a display name and base URL and automatically sets `npm: "@ai-sdk/openai-compatible"`. This targets OpenAI-compatible endpoints; adjust the adapter before export for other protocols.
- The model-list button requests `GET <baseURL>/models` with `Authorization: Bearer <API key>` (if a key is provided) and the entered headers; a header named Authorization overrides the Bearer value. Responses shaped as `{"data":[{"id":"model-id"}]}` are supported. Fetched IDs are deduplicated and appended to the model rows; hand-entered IDs are not removed, and capability metadata is not written.
- The request runs in the background with a 12-second timeout and a 4 MB response limit; failures leave the form unchanged. URLs with embedded credentials, query strings, or fragments are rejected, and `{env:...}` key references cannot be used for live fetching. The request sends the entered key/headers to the entered URL, so verify the address first.
- Deleting a group or model removes only that definition; defaults, agents, or other references are not changed automatically. Undo can restore it.

## Reasoning and relay permissions

`reasoning: true` is a capability declaration; it cannot give reasoning support to a model that lacks it. Whether reasoning content is returned also depends on the SDK adapter, request parameters, relay group permissions, and the model.

For example, if the server uses a `reasoning_content` field, enter the form that matches its protocol:

```json
{
  "reasoning": true,
  "interleaved": {"field": "reasoning_content"},
  "limit": {"context": 128000, "output": 8192}
}
```

The limits above are examples only. `variants` has no universal presets: parameters such as `reasoningEffort` or `thinking` depend on the adapter and model and require the corresponding documentation. Offline checks do not verify that a model exists, that permissions are granted, or that response fields are present, and they consume no API quota.

Fields are checked against `ProviderConfig` in the [OpenCode configuration schema](https://opencode.ai/config.json). Newer schemas also offer a structurally different `providers` configuration; this tool explicitly rejects that format to avoid corrupting it, and this version targets existing `provider` configurations. Support for forms such as the interleaved string may differ between OpenCode versions; `{"field":"reasoning_content"}` is a commonly supported object form. Checks cover the fields edited by this tool, not the entire OpenCode schema.

## Keys and auth.json

- Inline `options.apiKey` values show only the first 4 characters and total length in the overview; keys of 4 characters or fewer are fully masked.
- `{env:NAME}` / `{file:path}` are shown as references and are never read or expanded.
- Click “Load auth.json” to choose an authentication file manually; API keys are matched by provider ID, and OAuth is marked separately. The usual path is `~/.local/share/opencode/auth.json`, though `XDG_DATA_HOME` may change it.
- Without a loaded auth file, the key is shown as “Unconfirmed”; the tool does not assume it exists. Inline configuration is shown first; actual runtime authentication follows OpenCode.
- Loaded authentication data is used only for display and is never merged into the output. You can clear it from memory at any time.
- Input and output retain complete keys from the original configuration, and the headers editor also displays original values for editing. The program does not write configuration files, log, or autosave. A key for a new group is written to `options.apiKey` in the output; do not share that output with anyone who should not see it.

## JSONC preservation

Parsing records the position of every value. Editing an existing field replaces only its value; a new field is appended to its containing object; deleting a field removes only that key/value and any necessary comma. Untouched regions, key order, comments, and unknown fields remain as they were. With no edits, the output is byte-for-byte identical to the input.

Objects (headers, variants, etc.) are recursively merged by key to preserve internal comments where possible. Comments inside a replaced/deleted value may be lost when the entire value type changes, an array is replaced, or a field is deleted. Local whitespace around new fields may differ slightly from the original style. BOM, both comment forms, trailing commas, and CRLF are supported; duplicate keys and invalid JSON values are rejected with line and column positions.

## Verification

```powershell
py -m unittest discover -s tests -v
```

Tests cover parsing, comment preservation, group/model add/delete, key masking, offline checks, simulated model-list responses, and Chinese/English catalog keys, placeholders, and English error messages. Use `py tests/gui_smoke.py` for desktop interaction and language-switch checks, and `py tests/layout_smoke.py` to verify Chinese and English controls at 1180×770, 900×650, and 780×550 plus narrow dialogs (both need a graphical desktop). All network requests in tests use simulated responses and never contact a real relay.

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).
