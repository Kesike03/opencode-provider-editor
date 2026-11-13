"""Run with: py app.py (Windows) or python3 app.py."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from core import (BOOL_FIELDS, MISSING, MODALITIES, MODEL_FIELDS, PROVIDER_FIELDS,
                  diagnose, get_field, key_source, parse_field, validate_field)
from dialogs import ModelDialog, ProviderDialog, ToolTip, fit_window
from i18n import LANGUAGES, default_language, get_language, set_language, tr
from jsonc_editor import Document, loads


EXAMPLE_ZH = '''{
  "$schema": "https://opencode.ai/config.json",
  // 一个 provider 对应一个中转站分组；请按实际协议修改
  "provider": {
    "relay-vip": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "中转站 · VIP 分组",
      "options": {
        "baseURL": "https://example.com/v1",
        "apiKey": "{env:RELAY_API_KEY}"
      },
      "models": {
        "your-model-id": {
          "name": "我的模型",
          // 示例能力和上限不是服务端能力证明
          "reasoning": true,
          "tool_call": true,
          "attachment": false,
          "modalities": {"input": ["text"], "output": ["text"]},
          "interleaved": {"field": "reasoning_content"},
          "limit": {"context": 128000, "output": 8192},
          "variants": {}
        }
      }
    }
  }
}
'''

EXAMPLE_EN = '''{
  "$schema": "https://opencode.ai/config.json",
  // One provider represents one relay group; adapt the protocol to your setup.
  "provider": {
    "relay-vip": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Relay · VIP",
      "options": {
        "baseURL": "https://example.com/v1",
        "apiKey": "{env:RELAY_API_KEY}"
      },
      "models": {
        "your-model-id": {
          "name": "My model",
          // Example capabilities and limits are not proof of server support.
          "reasoning": true,
          "tool_call": true,
          "attachment": false,
          "modalities": {"input": ["text"], "output": ["text"]},
          "interleaved": {"field": "reasoning_content"},
          "limit": {"context": 128000, "output": 8192},
          "variants": {}
        }
      }
    }
  }
}
'''


def example_text():
    return EXAMPLE_EN if get_language() == 'en' else EXAMPLE_ZH


def display(value):
    if value is MISSING:
        return tr('common.missing')
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def set_text(widget, text, readonly=False):
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    widget.insert('1.0', text)
    if readonly:
        widget.configure(state='disabled')


class FieldDialog(tk.Toplevel):
    def __init__(self, parent, field, value, on_save):
        super().__init__(parent)
        self.title(tr('field.title', field=field))
        fit_window(self, 620, 470 if field == 'modalities' else 360, 450, 420 if field == 'modalities' else 280)
        self.transient(parent)
        self.on_save = on_save
        self.field = field
        self.editor = None
        self.choice = None
        self.first_choice = None
        self.modality_vars = {}
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill='both', expand=True)
        family = tkfont.nametofont('TkDefaultFont').actual('family')
        ttk.Label(frame, text=field, font=(family, 14, 'bold')).pack(anchor='w')
        help_label = ttk.Label(frame, text=tr('help.' + field))
        help_label.pack(anchor='w', pady=(8, 14))
        frame.bind('<Configure>', lambda event: help_label.configure(wraplength=max(260, event.width - 36)))
        if field == 'modalities':
            self.body = ttk.Frame(frame)
            self.body.pack(fill='x', pady=(0, 8))
            self.build_modalities(self.body, value)
        elif field in BOOL_FIELDS:
            self.checked = tk.BooleanVar(value=value is True)
            self.choice = ttk.Checkbutton(frame, text=tr('field.enabled'), variable=self.checked)
            self.choice.pack(anchor='w')
            self.body = self.choice
        else:
            self.editor = ScrolledText(frame, height=7, undo=True, font=('Consolas', 11))
            self.editor.pack(fill='both', expand=True)
            if value is MISSING:
                text = '{}' if field in ('headers', 'variants') else ''
            elif field in ('name', 'baseURL'):
                text = str(value)
            else:
                text = json.dumps(value, ensure_ascii=False, indent=2)
            self.editor.insert('1.0', text)
            self.body = self.editor
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=(16, 0))
        ttk.Button(actions, text=tr('field.remove'), command=lambda: self.save(True)).pack(side='left')
        ttk.Button(actions, text=tr('button.save'), command=self.save).pack(side='right')
        ttk.Button(actions, text=tr('button.cancel'), command=self.destroy).pack(side='right', padx=8)
        actions.pack_forget()
        actions.pack(side='bottom', fill='x', pady=(12, 0), before=self.body)
        self.bind('<Escape>', lambda event: self.destroy())
        self.grab_set()
        (self.editor or self.choice or self.first_choice).focus_set()

    def build_modalities(self, parent, value):
        current = value if isinstance(value, dict) else {}
        defaults = {'input': ['text'], 'output': ['text']}
        for key in ('input', 'output'):
            group = ttk.LabelFrame(parent, text=tr('modalities.' + key), padding=8)
            group.pack(fill='x', pady=(0, 10))
            row = ttk.Frame(group)
            row.pack(fill='x')
            selected = current.get(key, defaults[key])
            if not isinstance(selected, list):
                selected = defaults[key]
            for modality in MODALITIES:
                variable = tk.BooleanVar(value=modality in selected)
                check = ttk.Checkbutton(row, text=tr('modalities.' + modality), variable=variable)
                check.pack(side='left', padx=(0, 12))
                self.modality_vars[(key, modality)] = variable
                if self.first_choice is None:
                    self.first_choice = check

    def modality_value(self):
        value = {}
        for key in ('input', 'output'):
            selected = [modality for modality in MODALITIES if self.modality_vars[(key, modality)].get()]
            if not selected:
                raise ValueError(tr('modalities.required'))
            value[key] = selected
        return validate_field('modalities', value)

    def save(self, delete=False):
        try:
            if delete:
                value = None
            elif self.field == 'modalities':
                value = self.modality_value()
            elif self.field in BOOL_FIELDS:
                value = self.checked.get()
            else:
                value = parse_field(self.field, self.editor.get('1.0', 'end-1c'))
            self.on_save(value, delete)
        except (ValueError, TypeError) as exc:
            messagebox.showerror(tr('field.save_error'), str(exc), parent=self)
            return
        self.destroy()


class App(tk.Tk):
    def __init__(self, language=None):
        super().__init__()
        set_language(language or default_language())
        self.doc = None
        self.auth = None
        self.history = []
        self.provider_ids = {}
        self.model_ids = {}
        self.active_pid = None
        self.active_mid = None
        self.refreshing = False
        self.exported = False
        self._status = ('status.waiting', {})
        self._build_ui()
        fit_window(self, 1180, 770, 780, 550)

    def _configure_style(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        windows = self.tk.call('tk', 'windowingsystem') == 'win32'
        if windows:
            family = 'Microsoft YaHei UI' if get_language() == 'zh' else 'Segoe UI'
        else:
            family = tkfont.nametofont('TkDefaultFont').actual('family')
        self.family = family
        tkfont.nametofont('TkDefaultFont').configure(family=family, size=10)
        tkfont.nametofont('TkHeadingFont').configure(family=family, size=10, weight='bold')
        self.configure(background='#f2f5f5')
        style.configure('TFrame', background='#f2f5f5')
        style.configure('TLabel', background='#f2f5f5', foreground='#243443')
        style.configure('TLabelframe', background='#f2f5f5', bordercolor='#d8e1e2', relief='solid')
        style.configure('TLabelframe.Label', background='#f2f5f5', foreground='#243443', font=(family, 10, 'bold'))
        style.configure('Treeview', rowheight=32, background='#ffffff', foreground='#243443', fieldbackground='#ffffff', borderwidth=0)
        style.configure('Treeview.Heading', background='#edf2f2', foreground='#425663', font=(family, 10, 'bold'), relief='flat')
        style.map('Treeview', background=[('selected', '#176d75')], foreground=[('selected', '#ffffff')])
        style.map('Treeview.Heading', background=[('active', '#e2ebea')])
        style.configure('TNotebook', background='#f2f5f5', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(16, 9))
        style.map('TNotebook.Tab', background=[('selected', '#ffffff')], foreground=[('selected', '#176d75')])
        style.configure('TButton', padding=(10, 6), background='#ffffff', foreground='#243443')
        style.configure('Accent.TButton', padding=(14, 7), background='#176d75', foreground='#ffffff')
        style.map('Accent.TButton', background=[('active', '#0e565c')])
        style.configure('TEntry', padding=5)

    def _build_ui(self):
        self.title(tr('app.title'))
        self.tips = ToolTip(self)
        self._configure_style()
        self.outer = ttk.Frame(self, padding=12)
        self.outer.pack(fill='both', expand=True)
        header = ttk.Frame(self.outer)
        header.pack(fill='x')
        title_area = ttk.Frame(header)
        title_area.pack(side='left', fill='x', expand=True)
        ttk.Label(title_area, text=tr('app.heading'), font=(self.family, 17, 'bold')).pack(anchor='w')
        ttk.Label(title_area, text=tr('app.subtitle'), foreground='#647580').pack(anchor='w', pady=(2, 0))
        language_area = ttk.Frame(header)
        language_area.pack(side='right', anchor='n')
        ttk.Label(language_area, text=tr('app.language')).pack(side='left', padx=(0, 6))
        self.language_var = tk.StringVar(value=LANGUAGES[get_language()])
        self.language_box = ttk.Combobox(language_area, textvariable=self.language_var,
                                         values=list(LANGUAGES.values()), state='readonly', width=9)
        self.language_box.pack(side='left')
        self.language_box.bind('<<ComboboxSelected>>', self._language_selected)
        self.tabs = ttk.Notebook(self.outer)
        self.tabs.pack(fill='both', expand=True, pady=(10, 0))
        self.input_tab = ttk.Frame(self.tabs, padding=10)
        self.edit_tab = ttk.Frame(self.tabs, padding=10)
        self.report_tab = ttk.Frame(self.tabs, padding=10)
        self.output_tab = ttk.Frame(self.tabs, padding=10)
        for frame, label in ((self.input_tab, tr('tab.import')), (self.edit_tab, tr('tab.edit')),
                             (self.report_tab, tr('tab.report')), (self.output_tab, tr('tab.output'))):
            self.tabs.add(frame, text=label)
        self.build_input()
        self.build_editor()
        self.build_report()
        self.build_output()
        self.status = tk.StringVar()
        status_label = ttk.Label(self.outer, textvariable=self.status)
        status_label.pack(anchor='w', pady=(8, 0))
        self.outer.bind('<Configure>', lambda event: status_label.configure(wraplength=max(240, event.width - 18)))
        self.set_status(self._status[0], **self._status[1])

    def _language_selected(self, event=None):
        for code, label in LANGUAGES.items():
            if label == self.language_var.get():
                self.switch_language(code)
                return

    def switch_language(self, language):
        if language not in LANGUAGES or language == get_language():
            return
        current_tab = self.tabs.index(self.tabs.select()) if self.tabs.select() else 0
        filter_text = self.model_filter.get()
        input_text = self.input.get('1.0', 'end-1c')
        self.tips.hide()
        set_language(language)
        self.outer.destroy()
        self._build_ui()
        set_text(self.input, input_text)
        self.model_filter.set(filter_text)
        if self.doc is not None:
            self.refresh()
            if self.exported:
                set_text(self.output, self.doc.text, readonly=True)
                self.copy_button.configure(state='normal')
            else:
                self.invalidate_output()
        else:
            self.invalidate_output()
        self.tabs.select(current_tab)

    def set_status(self, key, **values):
        self._status = (key, values)
        self.status.set(tr(key, **values))

    def build_input(self):
        bar = ttk.Frame(self.input_tab)
        bar.pack(fill='x', pady=(0, 10))
        ttk.Button(bar, text=tr('input.paste'), command=self.paste).pack(side='left')
        ttk.Button(bar, text=tr('input.example'), command=self.example).pack(side='left', padx=8)
        ttk.Button(bar, text=tr('input.import'), command=self.import_text, style='Accent.TButton').pack(side='right')
        ttk.Label(self.input_tab, text=tr('input.label')).pack(anchor='w', pady=(0, 8))
        self.input = ScrolledText(self.input_tab, wrap='none', undo=True, font=('Consolas', 11))
        self.input.pack(fill='both', expand=True)

    def tree(self, parent, columns, height=5):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=tuple(c[0] for c in columns), show='headings', height=height, selectmode='browse')
        for name, label, width in columns:
            tree.heading(name, text=label)
            tree.column(name, width=width, minwidth=28 if name == 'help' else 70, stretch=name != 'help')
        y = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.grid(row=0, column=0, sticky='nsew')
        y.grid(row=0, column=1, sticky='ns')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def build_editor(self):
        bar = ttk.Frame(self.edit_tab)
        bar.pack(fill='x', pady=(0, 8))
        ttk.Button(bar, text=tr('editor.load_auth'), command=self.load_auth).pack(side='left')
        ttk.Button(bar, text=tr('editor.clear_auth'), command=self.clear_auth).pack(side='left', padx=5)
        ttk.Button(bar, text=tr('editor.undo'), command=self.undo).pack(side='left')
        ttk.Button(bar, text=tr('editor.export'), command=self.export, style='Accent.TButton').pack(side='right')
        panes = ttk.Panedwindow(self.edit_tab, orient='horizontal')
        panes.pack(fill='both', expand=True)
        nav = ttk.Frame(panes)
        details_area = ttk.Frame(panes)
        panes.add(nav, weight=2)
        panes.add(details_area, weight=3)
        nav.rowconfigure(0, weight=1, minsize=155)
        nav.rowconfigure(1, weight=2, minsize=205)
        nav.columnconfigure(0, weight=1)
        pframe = ttk.LabelFrame(nav, text=tr('editor.groups_title'), padding=8)
        pframe.grid(row=0, column=0, sticky='nsew', pady=(0, 8))
        model_list = ttk.LabelFrame(nav, text=tr('editor.models_title'), padding=8)
        model_list.grid(row=1, column=0, sticky='nsew')
        self.detail_tabs = ttk.Notebook(details_area)
        self.detail_tabs.pack(fill='both', expand=True, padx=(8, 0))
        details = ttk.Frame(self.detail_tabs, padding=10)
        model_details = ttk.Frame(self.detail_tabs, padding=10)
        self.detail_tabs.add(details, text=tr('editor.detail_group'))
        self.detail_tabs.add(model_details, text=tr('editor.detail_model'))
        self.providers = self.tree(pframe, [('id', tr('tree.provider_id'), 145),
                                             ('name', tr('tree.display_name'), 155),
                                             ('count', tr('tree.models'), 62)], 4)
        self.providers.bind('<<TreeviewSelect>>', self.select_provider)
        provider_actions = ttk.Frame(pframe)
        provider_actions.pack(fill='x', pady=(6, 0))
        ttk.Button(provider_actions, text=tr('editor.add_group'), command=self.add_provider).pack(side='left')
        ttk.Button(provider_actions, text=tr('editor.delete'), command=self.delete_provider).pack(side='left', padx=6)
        self.providers.master.pack_forget()
        self.providers.master.pack(fill='both', expand=True, pady=(8, 0))
        self.provider_summary = ttk.Label(details, text=tr('editor.select_group'), justify='left', foreground='#536674')
        self.provider_summary.pack(fill='x', pady=(0, 8))
        details.bind('<Configure>', lambda event: self.provider_summary.configure(wraplength=max(180, event.width - 30)))
        self.help = {field: tr('help.' + field) for field in PROVIDER_FIELDS + MODEL_FIELDS}
        self.provider_fields = self.tree(details, [('help', ' ', 34),
                                                    ('field', tr('tree.field'), 155),
                                                    ('value', tr('tree.value'), 400)], 3)
        self.tips.attach_tree(self.provider_fields, self.help)
        self.provider_fields.bind('<Double-1>', self.edit_provider)
        self.provider_fields.bind('<Return>', self.edit_provider)
        ttk.Button(details, text=tr('editor.edit_selected'), command=self.edit_selected_provider).pack(anchor='e', pady=(8, 0))
        self.provider_fields.master.pack_forget()
        self.provider_fields.master.pack(fill='both', expand=True, pady=(8, 0))
        search_bar = ttk.Frame(model_list)
        search_bar.pack(fill='x', pady=(0, 6))
        ttk.Label(search_bar, text=tr('editor.search_models')).pack(side='left')
        self.model_filter = tk.StringVar()
        self.model_filter.trace_add('write', lambda *_: self.refresh_models())
        ttk.Entry(search_bar, textvariable=self.model_filter).pack(side='left', fill='x', expand=True, padx=(8, 0))
        self.models = self.tree(model_list, [('id', tr('tree.model_id'), 175),
                                             ('name', tr('tree.display_name'), 190)], 7)
        self.models.bind('<<TreeviewSelect>>', self.select_model)
        self.models.bind('<Double-1>', self.focus_model_details)
        model_actions = ttk.Frame(model_list)
        model_actions.pack(fill='x', pady=(6, 0))
        ttk.Button(model_actions, text=tr('editor.add_model'), command=self.add_model).pack(side='left')
        ttk.Button(model_actions, text=tr('editor.delete'), command=self.delete_model).pack(side='left', padx=6)
        self.models.master.pack_forget()
        self.models.master.pack(fill='both', expand=True, pady=(8, 0))
        self.model_heading = ttk.Label(model_details, text=tr('editor.select_model'), font=(self.family, 12, 'bold'))
        self.model_heading.pack(anchor='w', pady=(0, 10))
        self.model_fields = self.tree(model_details, [('help', ' ', 34),
                                                       ('field', tr('tree.field'), 155),
                                                       ('value', tr('tree.value'), 400)], 7)
        self.tips.attach_tree(self.model_fields, self.help)
        self.model_fields.bind('<Double-1>', self.edit_model)
        self.model_fields.bind('<Return>', self.edit_model)
        ttk.Button(model_details, text=tr('editor.edit_selected'), command=self.edit_selected_model).pack(anchor='e', pady=(8, 0))
        self.model_fields.master.pack_forget()
        self.model_fields.master.pack(fill='both', expand=True, pady=(8, 0))

    def build_report(self):
        ttk.Label(self.report_tab, text=tr('report.heading')).pack(anchor='w', pady=(0, 12))
        self.report = ScrolledText(self.report_tab, wrap='word', font=('', 11), state='disabled')
        self.report.pack(fill='both', expand=True)

    def build_output(self):
        bar = ttk.Frame(self.output_tab)
        bar.pack(fill='x', pady=(0, 10))
        ttk.Button(bar, text=tr('output.generate'), command=self.export).pack(side='left')
        self.copy_button = ttk.Button(bar, text=tr('output.copy'), command=self.copy_output, state='disabled')
        self.copy_button.pack(side='left', padx=8)
        ttk.Label(self.output_tab, text=tr('output.warning')).pack(anchor='w', pady=(0, 8))
        self.output = ScrolledText(self.output_tab, wrap='none', font=('Consolas', 11), state='disabled')
        self.output.pack(fill='both', expand=True)

    def paste(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showerror(tr('msg.paste_title'), tr('msg.paste_empty'), parent=self)
            return
        set_text(self.input, text)

    def example(self):
        set_text(self.input, example_text())

    def import_text(self):
        try:
            document = Document(self.input.get('1.0', 'end-1c'))
            diagnose(document.data, self.auth)
        except (ValueError, TypeError, RecursionError) as exc:
            messagebox.showerror(tr('msg.import_title'), str(exc), parent=self)
            return
        if self.history and not messagebox.askyesno(tr('msg.replace_title'), tr('msg.replace_body'), parent=self):
            return
        self.doc = document
        self.history = []
        self.active_pid = None
        self.active_mid = None
        self.invalidate_output()
        self.refresh()
        self.tabs.select(self.edit_tab)
        self.set_status('status.imported')

    def load_auth(self):
        filename = filedialog.askopenfilename(parent=self, title=tr('msg.auth_pick_title'),
                                              filetypes=[(tr('msg.file_json'), '*.json'),
                                                         (tr('msg.file_all'), '*.*')])
        if not filename:
            return
        try:
            auth = loads(Path(filename).read_text(encoding='utf-8-sig'))
            if not isinstance(auth, dict):
                raise ValueError(tr('msg.auth_root'))
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr('msg.auth_read_title'), str(exc), parent=self)
            return
        self.auth = auth
        self.refresh()
        self.set_status('status.auth_loaded')

    def clear_auth(self):
        self.auth = None
        self.refresh()
        self.set_status('status.auth_cleared')

    def refresh(self):
        if self.doc is None:
            return
        self.refreshing = True
        self.providers.delete(*self.providers.get_children())
        self.provider_ids.clear()
        for index, (pid, provider) in enumerate(self.doc.data.get('provider', {}).items()):
            iid = str(index)
            self.provider_ids[iid] = pid
            self.providers.insert('', 'end', iid=iid, values=(pid, provider.get('name', tr('common.none')),
                                                               len(provider.get('models', {}))))
        if self.active_pid not in self.provider_ids.values():
            self.active_pid = next(iter(self.provider_ids.values()), None)
        for iid, pid in self.provider_ids.items():
            if pid == self.active_pid:
                self.providers.selection_set(iid)
        self.refreshing = False
        self.refresh_details()
        issues = diagnose(self.doc.data, self.auth)
        counts = {level: sum(row[0] == level for row in issues) for level in ('error', 'warning', 'info', 'note')}
        text = '  ·  '.join(f'{tr("level." + level)} {count}' for level, count in counts.items()) + '\n\n'
        text += '\n\n'.join(f'[{tr("level." + level)}] {loc}\n{message}' for level, loc, message in issues)
        set_text(self.report, text, readonly=True)

    def select_provider(self, event=None):
        if self.refreshing or not self.providers.selection():
            return
        pid = self.provider_ids.get(self.providers.selection()[0])
        if pid != self.active_pid:
            self.active_pid = pid
            self.active_mid = None
            self.refresh_details()
            self.detail_tabs.select(0)

    def refresh_details(self):
        self.provider_fields.delete(*self.provider_fields.get_children())
        if self.active_pid is None:
            self.provider_summary.configure(text=tr('editor.select_group'))
            self.refresh_models()
            return
        provider = self.doc.data['provider'][self.active_pid]
        self.provider_summary.configure(text=tr('editor.summary',
                                                url=str(provider.get('options', {}).get('baseURL', tr('common.none'))),
                                                key=key_source(self.active_pid, provider, self.auth)))
        for field in PROVIDER_FIELDS:
            obj = provider if field == 'name' else provider.get('options', {})
            self.provider_fields.insert('', 'end', iid=field, values=('?', field, display(get_field(obj, field))))
        self.refresh_models()

    def refresh_models(self):
        self.refreshing = True
        self.models.delete(*self.models.get_children())
        self.model_ids.clear()
        if self.doc is None or self.active_pid is None:
            self.active_mid = None
            self.refreshing = False
            self.refresh_model_fields()
            return
        filter_text = self.model_filter.get().strip().casefold()
        provider = self.doc.data['provider'][self.active_pid]
        for index, (mid, model) in enumerate(provider.get('models', {}).items()):
            if filter_text and filter_text not in (mid + ' ' + str(model.get('name', ''))).casefold():
                continue
            iid = str(index)
            self.model_ids[iid] = mid
            self.models.insert('', 'end', iid=iid, values=(mid, model.get('name', tr('common.none'))))
        if self.active_mid not in self.model_ids.values():
            self.active_mid = next(iter(self.model_ids.values()), None)
        for iid, mid in self.model_ids.items():
            if mid == self.active_mid:
                self.models.selection_set(iid)
        self.refreshing = False
        self.refresh_model_fields()

    def select_model(self, event=None):
        if self.refreshing or not self.models.selection():
            return
        mid = self.model_ids.get(self.models.selection()[0])
        if mid != self.active_mid:
            self.active_mid = mid
            self.refresh_model_fields()
        self.detail_tabs.select(1)

    def refresh_model_fields(self):
        self.model_fields.delete(*self.model_fields.get_children())
        if self.active_mid is None:
            self.model_heading.configure(text=tr('editor.select_model'))
            return
        self.model_heading.configure(text=self.active_mid)
        model = self.doc.data['provider'][self.active_pid]['models'][self.active_mid]
        for field in MODEL_FIELDS:
            self.model_fields.insert('', 'end', iid=field, values=('?', field, display(get_field(model, field))))

    def focus_model_details(self, event):
        self.detail_tabs.select(1)
        if self.model_fields.get_children():
            self.model_fields.focus_set()
            self.model_fields.focus(self.model_fields.get_children()[0])
            self.model_fields.selection_set(self.model_fields.get_children()[0])

    def edit_selected_provider(self):
        row = next(iter(self.provider_fields.selection()), None) or self.provider_fields.focus()
        if not row and self.provider_fields.get_children():
            row = self.provider_fields.get_children()[0]
        self.open_provider_field(row)

    def edit_selected_model(self):
        row = next(iter(self.model_fields.selection()), None) or self.model_fields.focus()
        if not row and self.model_fields.get_children():
            row = self.model_fields.get_children()[0]
        self.open_model_field(row)

    def edit_provider(self, event):
        if event.type == tk.EventType.ButtonPress and self.provider_fields.identify_column(event.x) == '#1':
            return
        row = self.provider_fields.identify_row(event.y) if event.type == tk.EventType.ButtonPress else self.provider_fields.focus()
        self.open_provider_field(row)

    def open_provider_field(self, row):
        if row not in PROVIDER_FIELDS or self.active_pid is None:
            return
        path = ['provider', self.active_pid]
        if row != 'name':
            path.append('options')
        path.append(row)
        self.open_field(row, path)

    def edit_model(self, event):
        if event.type == tk.EventType.ButtonPress and self.model_fields.identify_column(event.x) == '#1':
            return
        row = self.model_fields.identify_row(event.y) if event.type == tk.EventType.ButtonPress else self.model_fields.focus()
        self.open_model_field(row)

    def open_model_field(self, field):
        if field not in MODEL_FIELDS or self.active_mid is None:
            return
        path = ['provider', self.active_pid, 'models', self.active_mid] + field.split('.')
        self.open_field(field, path)

    def open_field(self, field, path):
        value = self.doc.data
        for key in path:
            value = value.get(key, MISSING) if isinstance(value, dict) else MISSING
        def save(new_value, delete):
            self.apply_change(path, new_value, delete)
        FieldDialog(self, field, value, save)

    def apply_change(self, path, value=None, delete=False):
        previous = self.doc.text
        self.doc.update(path, value, delete)
        if self.doc.text != previous:
            self.history.append(previous)
            self.tips.hide()
            self.invalidate_output()
            self.refresh()
            self.set_status('status.updated')

    def add_provider(self):
        if self.doc is None:
            messagebox.showinfo(tr('msg.provider_need_import_title'), tr('msg.provider_need_import_body'), parent=self)
            return
        def save(pid, provider):
            if pid in self.doc.data.get('provider', {}):
                raise ValueError(tr('msg.provider_exists'))
            self.active_pid, self.active_mid = pid, None
            self.apply_change(['provider', pid], provider)
        ProviderDialog(self, save)

    def delete_provider(self):
        if self.doc is None or self.active_pid is None:
            return
        pid = self.active_pid
        if not messagebox.askyesno(tr('msg.provider_delete_title'),
                                   tr('msg.provider_delete_body', pid=pid), parent=self):
            return
        self.apply_change(['provider', pid], delete=True)

    def add_model(self):
        if self.doc is None or self.active_pid is None:
            messagebox.showinfo(tr('msg.model_need_group_title'), tr('msg.model_need_group_body'), parent=self)
            return
        pid = self.active_pid
        def save(mid, model):
            if mid in self.doc.data['provider'][pid].get('models', {}):
                raise ValueError(tr('msg.model_exists'))
            if self.model_filter.get():
                self.model_filter.set('')
            self.active_mid = mid
            self.apply_change(['provider', pid, 'models', mid], model)
        ModelDialog(self, save)

    def delete_model(self):
        if self.doc is None or self.active_pid is None or self.active_mid is None:
            return
        pid, mid = self.active_pid, self.active_mid
        if not messagebox.askyesno(tr('msg.model_delete_title'),
                                   tr('msg.model_delete_body', pid=pid, mid=mid), parent=self):
            return
        self.apply_change(['provider', pid, 'models', mid], delete=True)

    def invalidate_output(self):
        self.exported = False
        self.copy_button.configure(state='disabled')
        set_text(self.output, tr('output.empty'), readonly=True)

    def undo(self):
        if not self.history:
            self.set_status('status.no_undo')
            return
        self.doc = Document(self.history.pop())
        self.invalidate_output()
        self.refresh()
        self.set_status('status.undone')

    def export(self):
        if self.doc is None:
            messagebox.showinfo(tr('msg.export_need_import_title'), tr('msg.export_need_import_body'), parent=self)
            return
        # Verify the syntax again before exposing the final text.
        loads(self.doc.text)
        set_text(self.output, self.doc.text, readonly=True)
        self.exported = True
        self.copy_button.configure(state='normal')
        self.tabs.select(self.output_tab)
        self.set_status('status.exported')

    def copy_output(self):
        if not self.exported:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(self.doc.text)
            self.update_idletasks()
        except tk.TclError:
            messagebox.showerror(tr('msg.copy_fail_title'), tr('msg.copy_fail_body'), parent=self)
            return
        self.set_status('status.copied')


if __name__ == '__main__':
    App().mainloop()
