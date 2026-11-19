import json
import os
import queue
import re
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import bot
from adb import stop_signal
from config import LIVES_INTERVAL, UI_NEXT_ROUND_DELAY
from run_statistics import BOX_TYPE_LABELS, RunStatistics, summarize
from session_lock import exclusive_session


ROOT = Path(__file__).resolve().parent
STATS_DIR = ROOT / 'stats'
TITLE = 'cookierun-classic-autorun'
APP_ICON = ROOT / 'ui_assets' / 'cookierun-classic-autorun.ico'
BOX_ORDER = ('rainbow', 'gold', 'silver', 'wood')
SETTINGS = (
    ('Fast Start', 'use_fast_start', 'Buys and uses Fast Start at the start of each run.'),
    ('Cookie Relay', 'use_cookie_relay', 'Buys Cookie Relay and uses it when the relay prompt appears.'),
    ('Claim Relics', 'detect_relic', 'Claims Relic rewards when their screen appears.'),
    ('Jump 7 times at start', 'jump_at_start', 'Taps Jump seven times once controls are ready. With Fast Start, waits for the controls to return.'),
)
BACK = '#0e1013'
PANEL = '#181c21'
BORDER = '#333b46'
FIELD = '#222831'
INK = '#eff2f6'
MUTED = '#b0bac7'
GREEN = '#80deb0'
AMBER = '#ffd182'
RED = '#ff9399'
EMPTY_METRICS = ('0', '0', '0:00')
METRIC_NAMES = ('Total Rounds', 'Total Boxes', 'Total Time')
START_COLOR = '#82e5b2'
STOP_COLOR = '#ff9399'
ISSUE_TEXT = re.compile(r'⚠|❌|\b(error|failed|exception|timeout|timed out|warn(?:ing)?|connection lost)\b', re.I)
LOG_TIME = re.compile(r'^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]? ')
LOG_SYMBOL = re.compile(r'^\s*(?P<icon>[\u2300-\u23ff\u2600-\u27bf\U0001f000-\U0001faff\u2b00-\u2bff])\ufe0f?\s+')
LOG_COLORS = {'INFO': '#a3c9fc', 'WAIT': AMBER, 'OK': GREEN, 'WARN': AMBER, 'ERROR': RED}


def session_duration(session):
    started = datetime.fromisoformat(session['started_at'])
    ended = datetime.fromisoformat(session['ended_at'])
    seconds = max(0, int((ended - started).total_seconds()))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes}:{seconds:02d}'


def finished_sessions(directory):
    records = []
    for path in directory.glob('*.json'):
        try:
            session = json.loads(path.read_text(encoding='utf-8'))
            if not session['ended_at'] or not isinstance(session['rounds'], list):
                continue
            ended = datetime.fromisoformat(session['ended_at']).astimezone()
            summary = summarize(session['rounds'])
            records.append((ended, summary, session_duration(session), session.get('activity_log')))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            continue
    return sorted(records, key=lambda record: record[0], reverse=True)


def add_tooltip(widget, text):
    window = None
    pending = None

    def show():
        nonlocal window, pending
        pending = None
        window = tk.Toplevel(widget)
        window.wm_overrideredirect(True)
        window.geometry(f'+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 4}')
        tk.Label(window, text=text, bg=FIELD, fg=INK, padx=8, pady=4,
                 highlightthickness=1, highlightbackground=BORDER,
                 font=('Segoe UI', 9), wraplength=310, justify='left').pack()

    def schedule(_event):
        nonlocal pending
        pending = widget.after(350, show)

    def hide(_event):
        nonlocal window, pending
        if pending is not None:
            widget.after_cancel(pending)
            pending = None
        if window is not None:
            window.destroy()
            window = None

    widget.bind('<Enter>', schedule)
    widget.bind('<Leave>', hide)
    widget.bind('<Destroy>', hide)


def box_display(count, counts):
    if count is None:
        return {}, 'Mystery box count unavailable'
    if counts is None:
        return (dict.fromkeys(BOX_ORDER, 0), '') if count == 0 else ({}, f'Unknown type: {count}')
    unknown = counts.get('unknown', 0)
    values = {key: counts[key] for key in BOX_ORDER if counts.get(key) or not unknown}
    return values, f'Unknown type: {unknown}' if unknown else ''


def prepare_log_view(widget):
    widget.tag_configure('time', foreground=MUTED)
    for tag, color in LOG_COLORS.items():
        widget.tag_configure(tag, foreground=color)


def insert_log_line(widget, message, timestamp=None):
    if timestamp is None:
        match = LOG_TIME.match(message)
        if match:
            timestamp = match[1]
            message = message[match.end():]
    if timestamp:
        widget.insert('end', f'[{timestamp}] ', 'time')
    symbol = LOG_SYMBOL.match(message)
    if symbol:
        icon = symbol['icon']
        message = message[symbol.end():]
    else:
        icon = ''
    badge, separator, after_badge = message.partition('] ')
    if separator and badge.removeprefix('[') in LOG_COLORS and badge.startswith('['):
        tag = badge[1:]
        message = after_badge
    elif icon == '❌' or message.startswith('Error:'):
        tag = 'ERROR'
    elif icon == '⚠' or ISSUE_TEXT.search(message):
        tag = 'WARN'
    elif icon == '✅':
        tag = 'OK'
    elif icon in ('⏳', '⌛', '🔍'):
        tag = 'WAIT'
    else:
        tag = 'INFO' if icon else None
    if tag:
        widget.insert('end', f'[{tag}] ', tag)
    widget.insert('end', message + '\n')


class ActivityOutput:
    def __init__(self, events):
        self.events = events
        self.pending = ''
        self.archive = None

    def emit(self, line):
        timestamp = datetime.now()
        self.events.put(('log', (timestamp, line)))
        if self.archive is not None:
            try:
                self.archive.write(f'{timestamp:%Y-%m-%d %H:%M:%S} {line}\n')
                self.archive.flush()
            except OSError:
                self.archive.close()
                self.archive = None
                self.events.put(('log', (timestamp, 'Warning: Could not continue saving the activity log.')))

    def write(self, value):
        lines = (self.pending + value).split('\n')
        self.pending = lines.pop()
        for line in lines:
            self.emit(line.rstrip('\r'))
        return len(value)

    def flush(self):
        if self.pending:
            self.write('\n')


def run_session(options, stop, events):
    class WindowStatistics(RunStatistics):
        def __init__(self, directory=None):
            super().__init__(directory)
            if log_path is not None:
                self.session['activity_log'] = log_path.name
                self.save()

        def begin(self):
            is_new = self.current is None
            super().begin()
            if is_new:
                output.emit(f'Round {len(self.session["rounds"])} started.')

        def complete(self):
            before = self.session['summary']['completed']
            super().complete()
            completed = self.session['summary']['completed']
            if completed != before:
                events.put(('progress', completed))

        def print_round(self):
            row = self.current
            if row and row['status'] == 'completed' and row['id'] not in self.reported_rounds:
                events.put(('round', (len(self.session['rounds']), dict(row))))
            super().print_round()

        def leave_round(self, reason='Returned to menu'):
            if self.current and self.current['status'] == 'running':
                output.emit(f'Warning: Round {len(self.session["rounds"])} interrupted. {reason}.')
            super().leave_round(reason)

        def print_summary(self):
            events.put(('summary', (dict(self.session['summary']), session_duration(self.session))))
            super().print_summary()

    token = stop_signal.set(stop)
    message = 'Stopped'
    failed = False
    output = ActivityOutput(events)
    log_path = None
    try:
        with exclusive_session(STATS_DIR / 'controller.lock'):
            try:
                directory = STATS_DIR / 'logs'
                directory.mkdir(parents=True, exist_ok=True)
                candidate = directory / f'{datetime.now():%Y-%m-%d_%H-%M-%S_%f}.log'
                output.archive = candidate.open('x', encoding='utf-8')
                log_path = candidate
            except OSError as error:
                output.emit(f'Warning: Could not open a log file: {error}')
            output.emit('Start requested.')
            bot.save_options(bot.SETTINGS_PATH, options)
            with redirect_stdout(output):
                outcome = bot.main(options, stop=stop, on_status=lambda state: events.put(('status', state)),
                                   statistics_factory=WindowStatistics)
                message = outcome or message
    except Exception as error:
        failed = True
        message = str(error).strip() or type(error).__name__
        output.emit(f'Error: {message}')
    finally:
        output.flush()
        output.emit('Stopped.')
        if output.archive is not None:
            output.archive.close()
        stop_signal.reset(token)
        events.put(('done', (message, failed)))


class DesktopWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.stop_signal = threading.Event()
        self.worker = None
        self.closing = False
        self.target_rounds = 0
        self.history_window = None
        self.logs_window = None
        self.help_window = None
        self.images = {key: tk.PhotoImage(file=ROOT / 'ui_assets' / f'{key}.png')
                       for key in BOX_ORDER}
        self.images = {key: image.subsample(2, 2) for key, image in self.images.items()}
        root.title(TITLE)
        if os.name == 'nt' and APP_ICON.is_file():
            root.iconbitmap(default=str(APP_ICON))
        root.configure(bg=BACK)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.columnconfigure(0, weight=2, uniform='workspace')
        root.columnconfigure(1, weight=3, uniform='workspace')
        root.rowconfigure(1, weight=1)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Dark.TCombobox', fieldbackground=FIELD, background=FIELD,
                        foreground=INK, arrowcolor=INK, bordercolor=BORDER,
                        lightcolor=FIELD, darkcolor=FIELD)
        style.map('Dark.TCombobox', fieldbackground=[('readonly', FIELD), ('disabled', PANEL)],
                  foreground=[('disabled', MUTED), ('readonly', INK)],
                  selectbackground=[('readonly', FIELD)], selectforeground=[('readonly', INK)])
        style.configure('Dark.Vertical.TScrollbar', background=FIELD, troughcolor=BACK,
                        bordercolor=BACK, arrowcolor=MUTED, lightcolor=FIELD, darkcolor=FIELD)
        style.map('Dark.Vertical.TScrollbar', background=[('active', BORDER)])
        root.option_add('*TCombobox*Listbox.background', FIELD)
        root.option_add('*TCombobox*Listbox.foreground', INK)
        root.option_add('*TCombobox*Listbox.selectBackground', '#275141')

        header = tk.Frame(root, bg=BACK)
        header.grid(row=0, column=0, columnspan=2, sticky='ew', padx=12, pady=(10, 7))
        header.columnconfigure(0, weight=1)
        self.label(header, TITLE, 15, bold=True, bg=BACK).grid(row=0, column=0, sticky='w')
        self.start_button = tk.Button(header, text='Start', command=self.start, width=6,
                                      fg='#10291d', activebackground='#a2f3ca',
                                      activeforeground='#10291d', disabledforeground='#8893a2',
                                      relief='flat', font=('Segoe UI', 10, 'bold'))
        self.stop_button = tk.Button(header, text='Stop', command=self.stop, width=6,
                                     fg='#381419', activebackground='#ffb1b5',
                                     activeforeground='#381419', disabledforeground='#8893a2',
                                     relief='flat', font=('Segoe UI', 10, 'bold'))
        self.set_run_controls(start_enabled=True, stop_enabled=False)
        self.start_button.grid(row=0, column=1, padx=(8, 6), ipady=3)
        self.stop_button.grid(row=0, column=2, ipady=3)
        self.help_button = tk.Button(header, text='? Help', command=self.show_help,
                                     bg='#294679', fg='white', activebackground='#385c99',
                                     activeforeground='white', relief='flat', padx=9,
                                     font=('Segoe UI', 10, 'bold'))
        self.help_button.grid(row=0, column=3, padx=(8, 0), ipady=3)
        self.status = tk.StringVar(value='Ready · LDPlayer connection checked on Start')
        self.status_label = tk.Label(header, textvariable=self.status, bg=BACK, fg=MUTED,
                                     font=('Segoe UI', 10), wraplength=500, justify='left')
        self.status_label.grid(row=1, column=0, sticky='w', pady=(5, 0))
        self.progress = tk.StringVar()
        tk.Label(header, textvariable=self.progress, bg=BACK, fg=INK,
                 font=('Segoe UI', 10)).grid(row=1, column=1, columnspan=3, sticky='e', pady=(5, 0))

        sidebar = tk.Frame(root, bg=BACK)
        sidebar.grid(row=1, column=0, sticky='nsew', padx=(12, 5), pady=(0, 10))
        sidebar.columnconfigure(0, weight=1)
        settings = self.panel(sidebar, 0, 'Saved Settings')
        choices = tk.Frame(settings, bg=PANEL)
        choices.grid(row=1, column=0, columnspan=2, sticky='ew')
        choices.columnconfigure((0, 1), weight=1, uniform='choices')
        saved = bot.load_saved_options(bot.SETTINGS_PATH) or {}
        self.inputs = []
        self.flags = {}
        for index, (label, key, tip) in enumerate(SETTINGS):
            value = tk.BooleanVar(value=saved.get(key, False))
            self.flags[key] = value
            row, column = ((0, 0), (0, 1), (1, 1), (1, 0))[index]
            control = tk.Checkbutton(choices, text=label, variable=value, bg=PANEL, fg=INK,
                                     activebackground=PANEL, activeforeground=INK, selectcolor=FIELD,
                                     disabledforeground=MUTED, highlightbackground=PANEL,
                                     anchor='w', font=('Segoe UI', 10))
            control.grid(row=row, column=column, sticky='ew', pady=2)
            add_tooltip(control, tip)
            self.inputs.append(control)
        tk.Frame(settings, bg=BORDER, height=1).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(5, 7))
        boost = tk.Frame(settings, bg=PANEL)
        boost.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 2))
        boost_label = self.label(boost, 'Random Boost', 10)
        boost_label.pack(side='left', padx=(0, 12))
        self.boost = ttk.Combobox(boost, state='readonly', width=18, style='Dark.TCombobox',
                                  values=('Off', *(name for name, _ in bot.BOOST_CHOICES)))
        self.boost.set(saved.get('desired_boost_name') or 'Off')
        self.boost.pack(side='left', fill='x', expand=True)
        for target in (boost_label, self.boost):
            add_tooltip(target, 'Chooses which Random Boost to try to buy each run. Off skips this purchase.')

        limit = tk.Frame(settings, bg=PANEL)
        limit.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(5, 2))
        limit_label = self.label(limit, 'Stop after N rounds', 10)
        limit_label.pack(side='left', padx=(0, 10))
        self.round_limit = tk.Entry(limit, width=6, bg=FIELD, fg=INK, insertbackground=INK,
                                    disabledbackground=PANEL, disabledforeground=MUTED,
                                    relief='flat', highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=GREEN,
                                    font=('Segoe UI', 10))
        self.round_limit.insert(0, str(saved.get('round_limit', 0)))
        self.round_limit.pack(side='left', ipady=2)
        for target in (limit_label, self.round_limit):
            add_tooltip(target, 'Stops at the main menu after N completed runs. 0 keeps running until you stop it.')
        self.inputs.append(self.round_limit)
        self.label(limit, '0 = Unlimited', 9, fg=MUTED).pack(side='left', padx=8)

        latest = self.panel(sidebar, 1, 'Latest Round')
        self.latest_text = self.label(latest, 'Awaiting a completed round', 10, fg=MUTED)
        self.latest_text.grid(row=1, column=0, columnspan=2, sticky='w', pady=(0, 3))
        self.latest_grades = self.grade_row(latest, 2)
        self.latest_note = self.label(latest, '', 9, fg=MUTED)
        self.latest_note.grid(row=3, columnspan=2, sticky='w')
        self.latest_note.grid_remove()

        summary = self.panel(sidebar, 2, 'Session Summary', pady=0)
        self.last_session_button = tk.Button(
            summary, text='Session History', command=self.show_last_session, bg=FIELD,
            fg=INK, activebackground=BORDER, activeforeground=INK, relief='flat',
            font=('Segoe UI', 9), padx=7, pady=1)
        self.last_session_button.grid(row=0, column=1, sticky='e', pady=(0, 4))
        self.metrics = self.metric_row(summary, 1)
        tk.Frame(summary, bg=BORDER, height=1).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(2, 5))
        self.label(summary, 'Boxes by type', 9, fg=MUTED).grid(
            row=3, column=0, columnspan=2, sticky='w')
        self.summary_grades = self.grade_row(summary, 4)
        self.summary_note = self.label(summary, 'Available after Stop', 9, fg=MUTED)
        self.summary_note.grid(row=5, columnspan=2, sticky='w')

        activity = self.panel(root, 1, 'Activity Log', column=1, sticky='nsew',
                              padx=(5, 12), pady=(0, 10))
        activity.rowconfigure(1, weight=1)
        log_buttons = tk.Frame(activity, bg=PANEL)
        log_buttons.grid(row=0, column=1, sticky='e', pady=(0, 4))
        self.small_button(log_buttons, 'Open Logs', self.show_logs).pack(side='left', padx=(0, 5))
        self.small_button(log_buttons, 'Copy Log', lambda: self.copy_log(self.log)).pack(side='left')
        log_body = tk.Frame(activity, bg=BACK)
        log_body.grid(row=1, column=0, columnspan=2, sticky='nsew')
        self.log = tk.Text(log_body, bg=BACK, fg=INK, relief='flat',
                           selectbackground='#275141', selectforeground=INK,
                           font=('Consolas', 10), height=4, width=1, wrap='word',
                           padx=9, pady=7, state='disabled',
                           highlightthickness=1, highlightbackground=BORDER, highlightcolor=GREEN)
        prepare_log_view(self.log)
        scroll = ttk.Scrollbar(log_body, command=self.log.yview, style='Dark.Vertical.TScrollbar')
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        self.append_log(datetime.now(), 'Ready. Press Start to connect to LDPlayer.')
        root.update_idletasks()
        root.minsize(max(540, root.winfo_reqwidth()), root.winfo_reqheight())
        root.geometry(f'{max(940, root.winfo_reqwidth())}x{max(525, root.winfo_reqheight())}')
        self.root.after(100, self.poll)

    def label(self, parent, text, size, *, bold=False, bg=PANEL, fg=INK):
        return tk.Label(parent, text=text, bg=bg, fg=fg,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'))

    def small_button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=FIELD, fg=INK,
                         activebackground=BORDER, activeforeground=INK, relief='flat',
                         font=('Segoe UI', 9), padx=7, pady=1)

    def show_help(self):
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.lift()
            return
        window = self.help_window = tk.Toplevel(self.root)
        window.title('Help')
        window.transient(self.root)
        window.configure(bg=PANEL, padx=14, pady=12)
        window.geometry('610x490')
        window.minsize(390, 300)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        self.label(window, 'How to use Auto Run', 15, bold=True).grid(
            row=0, column=0, sticky='w', pady=(0, 8))

        body = tk.Frame(window, bg=BACK)
        body.grid(row=1, column=0, sticky='nsew')
        guide = tk.Text(body, bg=BACK, fg=INK, relief='flat', wrap='word',
                        font=('Segoe UI', 10), padx=12, pady=10,
                        selectbackground='#275141', selectforeground=INK)
        guide.tag_configure('heading', font=('Segoe UI', 11, 'bold'), foreground=GREEN,
                            spacing1=10, spacing3=4)
        guide.tag_configure('item', lmargin1=0, lmargin2=15, spacing3=5)
        scroll = ttk.Scrollbar(body, command=guide.yview, style='Dark.Vertical.TScrollbar')
        guide.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        guide.pack(side='left', fill='both', expand=True)

        sections = (
            ('Start and stop', (
                'Open Cookie Run Classic at the main menu in LDPlayer, then press Start. Your settings are saved for next time.',
                'Press Stop at any time, or set Stop after N rounds to finish at the main menu after that many completed rounds. The header shows your progress when a limit is set. 0 means unlimited.',
            )),
            ('Saved settings', (
                'Fast Start: Buys the boost and taps its opening prompt.',
                'Cookie Relay: Buys Relay and uses it when the relay prompt appears.',
                'Jump 7 times at start: Taps Jump when controls are ready. With Fast Start, skips the jumps if the controls cannot be confirmed afterward.',
                'Random Boost: Tries to buy your selected boost each run. Choose Off to skip this purchase.',
                'Claim Relics: Claims Relic rewards when their screen appears.',
            )),
            ('Automatic behavior', (
                f'Round 1 begins when the menu is ready. Later rounds wait an extra {UI_NEXT_ROUND_DELAY} seconds.',
                f'Every {LIVES_INTERVAL // 60} minutes, at the main menu, the app checks Mailbox → Lives and tries Quick Receive & Send if hearts are available.',
                'The app does not restart the game on a schedule. It stops when it detects player verification or the game connection is lost.',
            )),
            ('Results and logs', (
                'Latest Round shows boxes from the most recent result. Hover over an icon for its name.',
                'Session Summary shows Total Rounds, Total Boxes and Total Time after stopping. Session History opens earlier summaries.',
                'Activity Log shows timestamped events. Open Logs lets you review saved logs and filter errors and warnings. Copy Log copies the text.',
            )),
        )
        for heading, items in sections:
            guide.insert('end', heading + '\n', 'heading')
            for item in items:
                guide.insert('end', '• ' + item + '\n', 'item')
        guide.config(state='disabled')
        close_button = self.small_button(window, 'Close', window.destroy)
        close_button.grid(row=2, column=0, sticky='e', pady=(8, 0))
        window.bind('<Escape>', lambda _event: window.destroy())
        window.wait_visibility()
        window.grab_set()
        close_button.focus_set()

    def panel(self, parent, row, title, *, column=0, sticky='ew', padx=0, pady=(0, 10)):
        panel = tk.Frame(parent, bg=PANEL, padx=10, pady=6,
                         highlightbackground=BORDER, highlightthickness=1)
        panel.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
        panel.columnconfigure(0, weight=1)
        self.label(panel, title, 12, bold=True).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        return panel

    def grade_row(self, parent, row):
        strip = tk.Frame(parent, bg=PANEL)
        strip.grid(row=row, column=0, columnspan=2, sticky='ew')
        values = {}
        for index, key in enumerate(BOX_ORDER):
            strip.columnconfigure(index, weight=1, uniform='grades')
            tile = tk.Frame(strip, bg=PANEL)
            tile.grid(row=0, column=index, sticky='w')
            icon = tk.Label(tile, image=self.images[key], bg=PANEL)
            icon.pack(side='left')
            value = self.label(tile, 'x0', 14, bold=True, fg=GREEN)
            value.pack(side='left', padx=(5, 0))
            for target in (icon, value):
                add_tooltip(target, f'{BOX_TYPE_LABELS[key]} Mystery Box')
            values[key] = value
        return values

    def metric_row(self, parent, row):
        metrics = tk.Frame(parent, bg=PANEL)
        metrics.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 4))
        widgets = []
        for index, name in enumerate(METRIC_NAMES):
            metrics.columnconfigure(index, weight=1)
            self.label(metrics, name, 9, fg=MUTED).grid(row=0, column=index, sticky='w', padx=(0, 6))
            value = self.label(metrics, EMPTY_METRICS[index], 16, bold=True, fg=GREEN)
            value.grid(row=1, column=index, sticky='w')
            widgets.append(value)
        return widgets

    def render_summary(self, summary, duration, metrics, grades, note_widget):
        values = (summary['completed'], summary['total_boxes'], duration)
        for widget, value in zip(metrics, values):
            widget.config(text=str(value))
        counts, note = box_display(summary['total_boxes'], summary['box_type_totals'])
        self.show_grades(grades, counts)
        if summary['unknown_box_rounds']:
            unread = f'Unknown box count: {summary["unknown_box_rounds"]} rounds'
            note = ' · '.join(filter(None, (note, unread)))
        note_widget.config(text=note)

    def show_last_session(self):
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.destroy()
        window = self.history_window = tk.Toplevel(self.root)
        window.title('Session History')
        window.configure(bg=PANEL, padx=12, pady=10)
        window.columnconfigure((0, 1), weight=1)
        window.transient(self.root)
        self.small_button(window, 'Open Session Folder',
                          lambda: self.open_session_folder(window)).grid(
                              row=4, column=0, columnspan=2, sticky='e', pady=(8, 0))
        records = finished_sessions(STATS_DIR / 'sessions')
        if not records:
            self.label(window, 'No finished sessions saved yet.', 10, fg=MUTED).grid(
                row=0, column=0, columnspan=2, sticky='w')
            return
        dates = tuple(record[0].strftime('%Y-%m-%d %H:%M:%S') for record in records)
        selector = ttk.Combobox(window, values=dates, state='readonly', style='Dark.TCombobox')
        selector.grid(row=0, column=0, sticky='w', pady=(0, 8))
        selector.current(0)
        metrics = self.metric_row(window, 1)
        grades = self.grade_row(window, 2)
        note = self.label(window, '', 9, fg=MUTED)
        note.grid(row=3, column=0, columnspan=2, sticky='w')
        open_log = self.small_button(window, 'Open Session Log',
                                     lambda: self.show_logs(records[selector.current()][3]))
        open_log.grid(row=0, column=1, sticky='e', pady=(0, 8))

        def refresh(_event=None):
            _, summary, duration, filename = records[selector.current()]
            path = STATS_DIR / 'logs' / Path(filename).name if isinstance(filename, str) else None
            open_log.config(state='normal' if path is not None and path.is_file() else 'disabled')
            self.render_summary(summary, duration, metrics, grades, note)

        selector.bind('<<ComboboxSelected>>', refresh)
        refresh()

    def open_session_folder(self, parent):
        directory = STATS_DIR / 'sessions'
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.startfile(directory)
        except OSError as error:
            messagebox.showerror('Could not open session folder', str(error), parent=parent)

    def copy_log(self, widget):
        text = widget.get('1.0', 'end-1c')
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def show_logs(self, selected_name=None):
        if self.logs_window is not None and self.logs_window.winfo_exists():
            self.logs_window.destroy()
        window = self.logs_window = tk.Toplevel(self.root)
        window.title('Activity Logs')
        window.configure(bg=PANEL, padx=12, pady=10)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        window.geometry('680x355')
        controls = tk.Frame(window, bg=PANEL)
        controls.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        paths = sorted((STATS_DIR / 'logs').glob('*.log'), reverse=True)
        selector = ttk.Combobox(controls, values=('Current Activity', *(path.stem for path in paths)),
                                width=29, state='readonly', style='Dark.TCombobox')
        selector.current(next((i for i, path in enumerate(paths, 1) if path.name == selected_name),
                              1 if paths else 0))
        selector.pack(side='left')
        issues_only = tk.BooleanVar(window, False)
        filter_button = tk.Checkbutton(controls, text='Errors & warnings', variable=issues_only,
                                       bg=PANEL, fg=INK, selectcolor=FIELD,
                                       activebackground=PANEL, activeforeground=INK)
        filter_button.pack(side='left', padx=8)
        log_body = tk.Frame(window, bg=BACK)
        log_body.grid(row=1, column=0, sticky='nsew')
        view = tk.Text(log_body, bg=BACK, fg=INK, wrap='word', font=('Consolas', 10),
                       state='disabled', padx=7, pady=6)
        prepare_log_view(view)
        scroll = ttk.Scrollbar(log_body, command=view.yview, style='Dark.Vertical.TScrollbar')
        view.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        view.pack(side='left', fill='both', expand=True)

        def refresh(_event=None):
            index = selector.current()
            try:
                contents = (paths[index - 1].read_text(encoding='utf-8', errors='replace')
                            if index > 0 else self.log.get('1.0', 'end-1c'))
            except OSError as error:
                contents = f'Error: Could not open log: {error}'
            view.config(state='normal')
            view.delete('1.0', 'end')
            for line in contents.splitlines():
                is_issue = bool(ISSUE_TEXT.search(line))
                if is_issue or not issues_only.get():
                    insert_log_line(view, line)
            if view.index('end-1c') == '1.0':
                view.insert('end', 'No matching log messages.')
            elif not issues_only.get():
                view.see('end')
            view.config(state='disabled')

        selector.bind('<<ComboboxSelected>>', refresh)
        filter_button.config(command=refresh)
        self.small_button(controls, 'Refresh', refresh).pack(side='right')
        self.small_button(controls, 'Copy Log', lambda: self.copy_log(view)).pack(side='right', padx=5)
        refresh()

    def show_grades(self, widgets, values, *, missing='?'):
        for key, widget in widgets.items():
            widget.config(text=f'x{values.get(key, missing)}')

    def append_log(self, timestamp, message):
        follow = self.log.yview()[1] >= 0.999
        self.log.config(state='normal')
        insert_log_line(self.log, message, timestamp.strftime('%Y-%m-%d %H:%M:%S') if message else None)
        if int(self.log.index('end-1c').split('.')[0]) > 2001:
            self.log.delete('1.0', '2.0')
        self.log.config(state='disabled')
        if follow:
            self.log.see('end')

    def set_status(self, message, color=MUTED):
        self.status.set(message)
        self.status_label.config(fg=color)

    def show_progress(self, completed):
        target = self.target_rounds
        self.progress.set(f'{completed} / {target} rounds completed' if target else '')

    def start(self):
        if self.worker is not None:
            return
        value = self.round_limit.get().strip()
        try:
            if not value.isascii() or not value.isdecimal():
                raise ValueError
            round_limit = int(value)
        except ValueError:
            self.set_status('Enter 0 or a positive whole number for the round limit.', RED)
            self.round_limit.focus_set()
            return
        name = None if self.boost.get() == 'Off' else self.boost.get()
        options = {key: value.get() for key, value in self.flags.items()}
        options.update(use_desired_random_boost=name is not None, desired_boost_name=name,
                       desired_boost_template=dict(bot.BOOST_CHOICES).get(name), round_limit=round_limit)
        self.latest_text.config(text='Awaiting a completed round')
        self.latest_note.grid_remove()
        self.summary_note.config(text='Available after Stop')
        for metric, value in zip(self.metrics, EMPTY_METRICS):
            metric.config(text=value)
        self.show_grades(self.latest_grades, {}, missing=0)
        self.show_grades(self.summary_grades, {}, missing=0)
        self.set_run_controls(start_enabled=False, stop_enabled=True)
        self.boost.config(state='disabled')
        for control in self.inputs:
            control.config(state='disabled')
        self.target_rounds = round_limit
        self.show_progress(0)
        self.set_status('Connecting to LDPlayer…', AMBER)
        self.stop_signal = threading.Event()
        self.worker = threading.Thread(target=run_session, args=(options, self.stop_signal, self.events))
        self.worker.start()

    def stop(self):
        if self.stop_signal.is_set():
            return
        self.stop_signal.set()
        self.set_run_controls(start_enabled=False, stop_enabled=False)
        self.set_status('Stopping…', AMBER)
        self.append_log(datetime.now(), 'Stop requested.')

    def poll(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                self.append_log(*payload)
            elif kind == 'status' and not self.stop_signal.is_set():
                color = AMBER if payload == 'Waiting for next round' else GREEN
                self.set_status(f'LDPlayer connected · {payload}', color)
            elif kind == 'progress':
                self.show_progress(payload)
            elif kind == 'round':
                number, row = payload
                count = row['boxes']
                quantity = 'Mystery Boxes: unknown' if count is None else f'{count} Mystery Box' + ('es' if count != 1 else '')
                self.latest_text.config(text=f'Round {number} · {quantity}')
                grades, note = box_display(count, row.get('box_types'))
                self.show_grades(self.latest_grades, grades)
                self.latest_note.config(text=note)
                if note:
                    self.latest_note.grid()
                else:
                    self.latest_note.grid_remove()
            elif kind == 'summary':
                summary, duration = payload
                self.render_summary(summary, duration, self.metrics,
                                    self.summary_grades, self.summary_note)
            elif kind == 'done':
                self.worker = None
                if self.closing:
                    self.root.destroy()
                    return
                message, failed = payload
                self.set_status(message, RED if failed else MUTED)
                self.append_log(datetime.now(), message)
                self.set_run_controls(start_enabled=True, stop_enabled=False)
                self.boost.config(state='readonly')
                for control in self.inputs:
                    control.config(state='normal')
        self.root.after(100, self.poll)

    def set_run_controls(self, *, start_enabled, stop_enabled):
        for button, enabled, color in ((self.start_button, start_enabled, START_COLOR),
                                       (self.stop_button, stop_enabled, STOP_COLOR)):
            button.config(state='normal' if enabled else 'disabled',
                          bg=color if enabled else FIELD)

    def close(self):
        if self.worker is None:
            self.root.destroy()
        else:
            self.closing = True
            self.stop()


def apply_windows_window_icon(window, path):
    from ctypes import c_int, c_ssize_t, windll, wintypes

    if not path.is_file():
        return
    window.update_idletasks()
    hwnd = int(window.wm_frame(), 0)
    user = windll.user32
    load_image = user.LoadImageW
    load_image.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                           c_int, c_int, wintypes.UINT]
    load_image.restype = wintypes.HANDLE
    send_message = user.SendMessageW
    send_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    send_message.restype = c_ssize_t
    # Set both sizes on the top-level window for the title bar and taskbar.
    for size, width_metric, height_metric in ((0, 49, 50), (1, 11, 12)):
        icon = load_image(None, str(path), 1, user.GetSystemMetrics(width_metric),
                          user.GetSystemMetrics(height_metric), 0x10)
        if icon:
            send_message(hwnd, 0x0080, size, icon)


if __name__ == '__main__':
    os.chdir(ROOT)
    if os.name == 'nt':
        from ctypes import windll

        # Give the Windows taskbar an app identity separate from pythonw.exe.
        windll.shell32.SetCurrentProcessExplicitAppUserModelID('Community.CookieRunClassic.AutoRun')
    window = tk.Tk()
    DesktopWindow(window)
    if os.name == 'nt':
        apply_windows_window_icon(window, APP_ICON)
    window.mainloop()
