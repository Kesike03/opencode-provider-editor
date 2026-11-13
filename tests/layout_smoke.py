"""Check controls remain visible at representative desktop window sizes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, EXAMPLE_EN, EXAMPLE_ZH, FieldDialog
from dialogs import ProviderDialog, ModelDialog
from i18n import tr


def controls(widget, kind):
    for child in widget.winfo_children():
        if child.winfo_class() == kind:
            yield child
        yield from controls(child, kind)


def buttons(widget):
    return controls(widget, 'TButton')


def check_language(language, example):
    app = App(language=language)
    try:
        app.input.insert('1.0', example)
        app.import_text()
        app.deiconify()
        for width, height in ((1180, 770), (900, 650), (780, 550)):
            app.geometry(f'{width}x{height}+10+10')
            app.update()
            tab = app.edit_tab
            visible = {b.cget('text'): b for b in buttons(tab) if b.winfo_ismapped()}
            for key in ('editor.add_group', 'editor.add_model', 'editor.export', 'editor.edit_selected'):
                label = tr(key)
                assert label in visible, (language, width, height, label)
                b = visible[label]
                assert b.winfo_width() > 40 and b.winfo_height() > 20, (language, width, height, label, b.winfo_width(), b.winfo_height())
                assert b.winfo_rooty() + b.winfo_height() <= app.winfo_rooty() + app.winfo_height(), (language, width, height, label)
                assert b.winfo_rootx() + b.winfo_width() <= app.winfo_rootx() + app.winfo_width(), (language, width, height, label)
            for tree in (app.providers, app.models, app.model_fields):
                assert tree.winfo_width() > 110 and tree.winfo_height() > 40, (language, width, height, tree)
                assert sum(tree.column(name, 'width') for name in tree['columns']) <= tree.winfo_width() + 4, (language, width, height, tree)
            assert app.language_box.winfo_ismapped()
            assert app.language_box.winfo_rootx() + app.language_box.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            app.detail_tabs.select(0)
            app.update()
            assert app.provider_fields.winfo_width() > 110 and app.provider_fields.winfo_height() > 40
            group_edit = next(b for b in buttons(tab) if b.cget('text') == tr('editor.edit_selected') and b.winfo_ismapped())
            assert group_edit.winfo_height() > 20
            app.detail_tabs.select(1)
            app.update()
            print('Editor layout:', language, width, height, 'provider', app.providers.winfo_height(), 'models', app.models.winfo_height())

        app.add_provider()
        app.update()
        dialog = next(w for w in app.winfo_children() if isinstance(w, ProviderDialog))
        dialog.geometry('480x420+10+10')
        app.update()
        for b in buttons(dialog):
            if b.cget('text') == tr('provider_dialog.submit'):
                assert b.winfo_ismapped() and b.winfo_height() > 20
                assert b.winfo_rooty() + b.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
        dialog.destroy()

        app.add_model()
        app.update()
        dialog = next(w for w in app.winfo_children() if isinstance(w, ModelDialog))
        dialog.geometry('380x220+10+10')
        app.update()
        assert dialog.model_id.winfo_ismapped()
        assert any(b.cget('text') == tr('model_dialog.submit') and b.winfo_ismapped() for b in buttons(dialog))
        dialog.destroy()
        app.open_field('interleaved', ['provider', 'relay-vip', 'models', 'your-model-id', 'interleaved'])
        app.update()
        dialog = next(w for w in app.winfo_children() if isinstance(w, FieldDialog))
        dialog.geometry('450x280+10+10')
        app.update()
        assert any(b.cget('text') == tr('button.save') and b.winfo_ismapped() and b.winfo_height() > 20 for b in buttons(dialog))
        dialog.destroy()
        app.open_field('modalities', ['provider', 'relay-vip', 'models', 'your-model-id', 'modalities'])
        app.update()
        dialog = next(w for w in app.winfo_children() if isinstance(w, FieldDialog))
        dialog.geometry('620x470+10+10')
        app.update()
        labels = {c.cget('text') for c in controls(dialog, 'TCheckbutton') if c.winfo_ismapped()}
        for key in ('modalities.text', 'modalities.image', 'modalities.audio',
                    'modalities.video', 'modalities.pdf'):
            assert tr(key) in labels, (language, key)
        assert any(b.cget('text') == tr('button.save') and b.winfo_ismapped() for b in buttons(dialog))
        dialog.destroy()
        print('Layout smoke check passed:', language)
    finally:
        app.destroy()


for language, example in (('zh', EXAMPLE_ZH), ('en', EXAMPLE_EN)):
    check_language(language, example)
