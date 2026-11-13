"""Desktop smoke check; run from the project root."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, EXAMPLE_ZH, FieldDialog
from dialogs import ModelDialog, ProviderDialog
from i18n import get_language, tr


app = App(language='zh')
app.withdraw()
try:
    app.input.insert('1.0', EXAMPLE_ZH)
    app.import_text()
    app.update()
    assert len(app.providers.get_children()) == 1
    assert len(app.models.get_children()) == 1
    assert len(app.model_fields.get_children()) == 9
    assert app.model_fields.item('reasoning', 'values')[0] == '?'
    app.tips.show('思考能力', 40, 40)
    assert app.tips.popup is not None
    app.tips.hide()
    app.model_filter.set('not-present')
    app.update()
    assert not app.models.get_children()
    app.model_filter.set('YOUR-MODEL')
    app.update()
    assert len(app.models.get_children()) == 1
    app.open_field('reasoning', ['provider', 'relay-vip', 'models', 'your-model-id', 'reasoning'])
    app.update()
    dialog = next(w for w in app.winfo_children() if isinstance(w, FieldDialog))
    dialog.checked.set(False)
    dialog.save()
    assert app.doc.data['provider']['relay-vip']['models']['your-model-id']['reasoning'] is False
    app.open_field('modalities', ['provider', 'relay-vip', 'models', 'your-model-id', 'modalities'])
    app.update()
    dialog = next(w for w in app.winfo_children() if isinstance(w, FieldDialog))
    assert dialog.modality_vars[('input', 'text')].get()
    assert dialog.modality_vars[('output', 'text')].get()
    dialog.modality_vars[('input', 'image')].set(True)
    dialog.modality_vars[('input', 'pdf')].set(True)
    dialog.save()
    assert app.doc.data['provider']['relay-vip']['models']['your-model-id']['modalities'] == {
        'input': ['text', 'image', 'pdf'], 'output': ['text']}
    app.export()
    assert app.output.get('1.0', 'end-1c') == app.doc.text
    app.copy_output()
    assert app.clipboard_get() == app.doc.text
    app.language_var.set('English')
    app._language_selected()
    app.update()
    assert get_language() == 'en'
    assert app.tabs.tab(app.output_tab, 'text') == tr('tab.output')
    assert app.tabs.index(app.tabs.select()) == 3
    assert app.status.get() == tr('status.copied')
    assert app.input.get('1.0', 'end-1c') == EXAMPLE_ZH
    assert app.output.get('1.0', 'end-1c') == app.doc.text
    assert str(app.copy_button.cget('state')) == 'normal'
    assert len(app.providers.get_children()) == 1
    assert len(app.models.get_children()) == 1
    assert 'Permissions and capabilities' in app.report.get('1.0', 'end-1c')
    app.switch_language('zh')
    app.update()
    assert get_language() == 'zh'
    assert app.input.get('1.0', 'end-1c') == EXAMPLE_ZH
    assert '权限与能力' in app.report.get('1.0', 'end-1c')
    while app.history:
        app.undo()
    assert app.doc.text == EXAMPLE_ZH
    assert not app.exported
    app.add_provider()
    app.update()
    provider_dialog = next(w for w in app.winfo_children() if isinstance(w, ProviderDialog))
    provider_dialog.mode.set('custom')
    provider_dialog.pid.set('relay_two')
    provider_dialog.name.set('第二分组')
    provider_dialog.url.set('https://example.test/v1')
    provider_dialog.model_rows[0][1].set('model-first')
    provider_dialog.add_model_row('model-second')
    provider_dialog.add_header_row('X-Group', 'vip')
    provider_dialog.work.put((['model-second', 'model-fetched'], None))
    provider_dialog.poll_fetch()
    assert provider_dialog.get_models() == ['model-first', 'model-second', 'model-fetched']
    provider_dialog.save()
    assert app.active_pid == 'relay_two'
    assert len(app.providers.get_children()) == 2
    assert app.doc.data['provider']['relay_two']['options']['headers'] == {'X-Group': 'vip'}
    app.add_model()
    app.update()
    model_dialog = next(w for w in app.winfo_children() if isinstance(w, ModelDialog))
    model_dialog.model_id.insert(0, 'third/model')
    model_dialog.save()
    assert app.active_mid == 'third/model'
    with patch('app.messagebox.askyesno', return_value=True):
        app.delete_model()
    assert 'third/model' not in app.doc.data['provider']['relay_two']['models']
    with patch('app.messagebox.askyesno', return_value=True):
        app.delete_provider()
    assert 'relay_two' not in app.doc.data['provider']
    print('GUI smoke check passed: import, tooltip, search, edit, modalities, export, copy, undo, add/delete provider and model')
finally:
    app.destroy()
