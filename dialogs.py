"""Provider creation dialog and contextual field help."""
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from core import build_provider, fetch_model_ids
from i18n import tr


def fit_window(window, width, height, min_width, min_height):
    screen_w, screen_h = window.winfo_screenwidth(), window.winfo_screenheight()
    width = min(width, max(400, screen_w - 72))
    height = min(height, max(360, screen_h - 110))
    window.geometry(f'{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 2 - 20)}')
    window.minsize(min(min_width, width), min(min_height, height))


class ToolTip:
    def __init__(self, parent):
        self.parent = parent
        self.popup = None
        self.text = None

    def show(self, text, x, y):
        if self.text == text and self.popup:
            return
        self.hide()
        self.text = text
        self.popup = tk.Toplevel(self.parent)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        frame = tk.Frame(self.popup, background='#c1d0d0', padx=1, pady=1)
        frame.pack()
        tk.Label(frame, text=text, background='#f3f8f7', foreground='#193047',
                 justify='left', wraplength=360, padx=12, pady=9).pack()
        self.popup.update_idletasks()
        x = min(x + 12, self.parent.winfo_screenwidth() - self.popup.winfo_reqwidth() - 8)
        y = min(y + 16, self.parent.winfo_screenheight() - self.popup.winfo_reqheight() - 8)
        self.popup.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.popup.deiconify()

    def hide(self):
        self.text = None
        if self.popup:
            self.popup.destroy()
            self.popup = None

    def attach(self, widget, description):
        widget.bind('<Enter>', lambda event: self.show(description, event.x_root, event.y_root))
        widget.bind('<Leave>', lambda event: self.hide())
        widget.bind('<Button-1>', lambda event: self.show(description, event.x_root, event.y_root))

    def attach_tree(self, tree, descriptions):
        def move(event):
            row = tree.identify_row(event.y)
            if tree.identify_region(event.x, event.y) == 'cell' and tree.identify_column(event.x) == '#1' and row in descriptions:
                self.show(descriptions[row], event.x_root, event.y_root)
            else:
                self.hide()
        tree.bind('<Motion>', move, add='+')
        tree.bind('<Leave>', lambda event: self.hide(), add='+')
        tree.bind('<Button-1>', move, add='+')


class ProviderDialog(tk.Toplevel):
    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.title(tr('provider_dialog.title'))
        fit_window(self, 700, 670, 480, 420)
        self.transient(parent)
        self.on_save = on_save
        self.tip = ToolTip(self)
        self.work = queue.Queue()
        self.fetching = False
        self.mode = tk.StringVar(value='native')
        self.pid = tk.StringVar()
        self.name = tk.StringVar()
        self.url = tk.StringVar()
        self.key = tk.StringVar()
        self.model_rows = []
        self.header_rows = []
        self.status = tk.StringVar(value='')

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        family = tkfont.nametofont('TkDefaultFont').actual('family')
        ttk.Label(outer, text=tr('provider_dialog.heading'), font=(family, 16, 'bold')).pack(anchor='w', pady=(0, 12))
        modebar = ttk.Frame(outer)
        modebar.pack(fill='x', pady=(0, 12))
        for value, label in (('native', tr('provider_dialog.mode_native')),
                             ('custom', tr('provider_dialog.mode_custom'))):
            ttk.Radiobutton(modebar, text=label, variable=self.mode, value=value, command=self.refresh_mode).pack(side='left', padx=(0, 22))

        area = ttk.Frame(outer)
        area.pack(fill='both', expand=True)
        canvas = tk.Canvas(area, highlightthickness=0)
        scrollbar = ttk.Scrollbar(area, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.bind('<MouseWheel>', lambda event: canvas.yview_scroll(-int(event.delta / 120), 'units'))
        self.bind('<Button-4>', lambda event: canvas.yview_scroll(-1, 'units'))
        self.bind('<Button-5>', lambda event: canvas.yview_scroll(1, 'units'))
        form = ttk.Frame(canvas, padding=(2, 2, 14, 12))
        slot = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(slot, width=event.width))

        self.add_entry(form, tr('provider_dialog.provider_id'), self.pid, tr('provider_dialog.help_pid'))
        self.add_entry(form, tr('provider_dialog.name'), self.name, tr('provider_dialog.help_name'))
        self.add_entry(form, tr('provider_dialog.base_url'), self.url, tr('provider_dialog.help_url'))
        self.add_entry(form, tr('provider_dialog.api_key'), self.key, tr('provider_dialog.help_key'), show='•')

        models_bar = ttk.Frame(form)
        models_bar.pack(fill='x', pady=(14, 4))
        ttk.Label(models_bar, text=tr('provider_dialog.models_title'), font=(family, 11, 'bold')).pack(side='left')
        help_models = ttk.Label(models_bar, text='  ?  ', foreground='#176d75', cursor='question_arrow')
        help_models.pack(side='left')
        self.tip.attach(help_models, tr('provider_dialog.help_models'))
        ttk.Button(models_bar, text=tr('provider_dialog.add_row'), command=self.add_model_row).pack(side='right')
        self.models_area = ttk.Frame(form)
        self.models_area.pack(fill='x')
        self.add_model_row()
        self.fetch_button = ttk.Button(form, text=tr('provider_dialog.fetch'), command=self.fetch_models)
        self.fetch_button.pack(anchor='w', pady=(8, 0))

        headers_bar = ttk.Frame(form)
        headers_bar.pack(fill='x', pady=(18, 4))
        ttk.Label(headers_bar, text=tr('provider_dialog.headers_title'), font=(family, 11, 'bold')).pack(side='left')
        help_headers = ttk.Label(headers_bar, text='  ?  ', foreground='#176d75', cursor='question_arrow')
        help_headers.pack(side='left')
        self.tip.attach(help_headers, tr('provider_dialog.help_headers'))
        ttk.Button(headers_bar, text=tr('provider_dialog.add_row'), command=self.add_header_row).pack(side='right')
        self.headers_area = ttk.Frame(form)
        self.headers_area.pack(fill='x')

        status_label = ttk.Label(outer, textvariable=self.status, foreground='#176d75')
        status_label.pack(anchor='w', pady=(8, 4))
        outer.bind('<Configure>', lambda event: status_label.configure(wraplength=max(240, event.width - 30)))
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x', pady=(8, 0))
        ttk.Button(buttons, text=tr('button.cancel'), command=self.destroy).pack(side='right')
        ttk.Button(buttons, text=tr('provider_dialog.submit'), command=self.save).pack(side='right', padx=8)
        buttons.pack_forget()
        status_label.pack_forget()
        buttons.pack(side='bottom', fill='x', pady=(8, 0), before=area)
        status_label.pack(side='bottom', fill='x', pady=(8, 4), before=area)
        self.bind('<Escape>', lambda event: self.destroy())
        self.refresh_mode()
        self.grab_set()

    def add_entry(self, parent, label, variable, description, show=None):
        line = ttk.Frame(parent)
        line.pack(fill='x', pady=(5, 7))
        heading = ttk.Frame(line)
        heading.pack(fill='x', pady=(0, 4))
        ttk.Label(heading, text=label).pack(side='left')
        question = ttk.Label(heading, text='  ?  ', foreground='#176d75', cursor='question_arrow')
        question.pack(side='left')
        self.tip.attach(question, description)
        entry = ttk.Entry(line, textvariable=variable, show=show)
        entry.pack(fill='x')
        return entry

    def refresh_mode(self):
        self.status.set(tr('provider_dialog.status_mode'))

    def add_model_row(self, value=''):
        frame = ttk.Frame(self.models_area)
        frame.pack(fill='x', pady=3)
        variable = tk.StringVar(value=value)
        ttk.Entry(frame, textvariable=variable).pack(side='left', fill='x', expand=True)
        ttk.Button(frame, text=tr('provider_dialog.remove_row'), command=lambda: self.remove_row(self.model_rows, frame)).pack(side='left', padx=(6, 0))
        self.model_rows.append((frame, variable))

    def add_header_row(self, name='', value=''):
        frame = ttk.Frame(self.headers_area)
        frame.pack(fill='x', pady=3)
        key_var, value_var = tk.StringVar(value=name), tk.StringVar(value=value)
        ttk.Entry(frame, textvariable=key_var, width=23).pack(side='left', padx=(0, 6))
        ttk.Entry(frame, textvariable=value_var).pack(side='left', fill='x', expand=True)
        ttk.Button(frame, text=tr('provider_dialog.remove_row'), command=lambda: self.remove_row(self.header_rows, frame)).pack(side='left', padx=(6, 0))
        self.header_rows.append((frame, key_var, value_var))

    def remove_row(self, rows, frame):
        rows[:] = [row for row in rows if row[0] is not frame]
        frame.destroy()

    def get_headers(self):
        headers = {}
        for _, key, value in self.header_rows:
            name, content = key.get().strip(), value.get().strip()
            if not name and not content:
                continue
            if not name or not content:
                raise ValueError(tr('provider_dialog.error_headers_pair'))
            if name.lower() in (old.lower() for old in headers):
                raise ValueError(tr('provider_dialog.error_headers_duplicate'))
            headers[name] = content
        return headers

    def get_models(self):
        return [var.get().strip() for _, var in self.model_rows if var.get().strip()]

    def fetch_models(self):
        if self.fetching:
            return
        try:
            url = self.url.get().strip()
            key = self.key.get().strip()
            headers = self.get_headers()
        except ValueError as exc:
            messagebox.showerror(tr('provider_dialog.error_headers_title'), str(exc), parent=self)
            return
        self.fetching = True
        self.fetch_button.configure(state='disabled')
        self.status.set(tr('provider_dialog.status_fetching'))
        def work():
            try:
                self.work.put((fetch_model_ids(url, key, headers), None))
            except Exception as exc:
                self.work.put((None, exc))
        threading.Thread(target=work, daemon=True).start()
        self.after(100, self.poll_fetch)

    def poll_fetch(self):
        try:
            ids, error = self.work.get_nowait()
        except queue.Empty:
            self.after(100, self.poll_fetch)
            return
        self.fetching = False
        self.fetch_button.configure(state='normal')
        if error:
            self.status.set(tr('provider_dialog.status_failed'))
            messagebox.showerror(tr('provider_dialog.error_fetch_title'), str(error), parent=self)
            return
        existing = set(self.get_models())
        blank = next((var for _, var in self.model_rows if not var.get().strip()), None)
        added = 0
        for mid in ids:
            if mid in existing:
                continue
            if blank:
                blank.set(mid)
                blank = None
            else:
                self.add_model_row(mid)
            existing.add(mid)
            added += 1
        self.status.set(tr('provider_dialog.status_fetched', total=len(ids), added=added))

    def save(self):
        try:
            pid = self.pid.get().strip()
            provider = build_provider(pid, self.name.get().strip(), self.url.get().strip(),
                                      self.key.get().strip(), self.get_models(), self.get_headers(),
                                      native=self.mode.get() == 'native')
            self.on_save(pid, provider)
        except (ValueError, TypeError) as exc:
            messagebox.showerror(tr('provider_dialog.error_add_title'), str(exc), parent=self)
            return
        self.destroy()


class ModelDialog(tk.Toplevel):
    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.title(tr('model_dialog.title'))
        fit_window(self, 480, 240, 380, 220)
        self.transient(parent)
        self.on_save = on_save
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=tr('model_dialog.model_id')).pack(anchor='w')
        self.model_id = ttk.Entry(frame)
        self.model_id.pack(fill='x', pady=(4, 12))
        ttk.Label(frame, text=tr('model_dialog.display_name')).pack(anchor='w')
        self.name = ttk.Entry(frame)
        self.name.pack(fill='x', pady=(4, 16))
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        ttk.Button(bar, text=tr('model_dialog.submit'), command=self.save).pack(side='right')
        ttk.Button(bar, text=tr('button.cancel'), command=self.destroy).pack(side='right', padx=8)
        self.bind('<Return>', lambda event: self.save())
        self.bind('<Escape>', lambda event: self.destroy())
        self.grab_set()
        self.model_id.focus_set()

    def save(self):
        mid = self.model_id.get().strip()
        if not mid or '#' in mid:
            messagebox.showerror(tr('model_dialog.invalid_title'), tr('model_dialog.invalid_body'), parent=self)
            return
        try:
            self.on_save(mid, {'name': self.name.get().strip()} if self.name.get().strip() else {})
        except ValueError as exc:
            messagebox.showerror(tr('model_dialog.error_title'), str(exc), parent=self)
            return
        self.destroy()
