import json
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from bisect import bisect_right
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.font import Font

import bot
from adb import stop_signal
from config import LIVES_INTERVAL, UI_NEXT_ROUND_DELAY
from run_statistics import BOX_TYPE_LABELS, REWARD_FIELDS, RunStatistics, summarize
from screen_text import save_evidence
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
START_COLOR = '#197253'
STOP_COLOR = '#9f3948'
ISSUE_TEXT = re.compile(r'⚠|❌|\b(error|failed|exception|timeout|timed out|warn(?:ing)?|connection lost)\b', re.I)
LOG_TIME = re.compile(r'^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]? ')
SESSION_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_SYMBOL = re.compile(r'^\s*(?P<icon>[\u2300-\u23ff\u2600-\u27bf\U0001f000-\U0001faff\u2b00-\u2bff])\ufe0f?\s+')
LOG_COLORS = {'INFO': '#a3c9fc', 'WAIT': AMBER, 'OK': GREEN, 'WARN': AMBER, 'ERROR': RED}
ISSUE_SCREENSHOT_STREAK = 4


def fit_status_text(message, width, measure):
    first, _, rest = message.partition('\n')
    if measure(first) > width:
        cut = bisect_right(range(len(first) + 1), width, key=lambda i: measure(first[:i])) - 1
        # Prefer a word break, but still support long paths or other unbroken text.
        cut = first.rfind(' ', 0, cut + 1) if ' ' in first[:cut + 1] else cut
        rest = ' '.join(part for part in (first[cut:].lstrip(), rest) if part)
        first = first[:cut].rstrip()

    second, more, _ = rest.partition('\n')
    if more or measure(second) > width:
        cut = bisect_right(range(len(second) + 1), width,
                           key=lambda i: measure(second[:i].rstrip() + '…')) - 1
        second = second[:max(0, cut)].rstrip() + '…'
    return f'{first}\n{second}' if second else first


def session_duration(session):
    duration = 0.0
    for row in session['rounds']:
        if row['status'] == 'completed' and row.get('started_at') and row.get('ended_at'):
            started = datetime.fromisoformat(row['started_at'])
            ended = datetime.fromisoformat(row['ended_at'])
            duration += max(0, (ended - started).total_seconds())
    seconds = int(duration)
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
            if summary['completed']:
                rounds = [(number, row) for number, row in enumerate(session['rounds'], 1)
                          if row['status'] == 'completed']
                records.append((ended, summary, session_duration(session), rounds, session.get('activity_log')))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            continue
    return sorted(records, key=lambda record: record[0], reverse=True)


def activity_log_end(path):
    try:
        with path.open('rb') as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 8192))
            for line in reversed(stream.read().decode('utf-8', errors='replace').splitlines()):
                match = LOG_TIME.match(line)
                if match:
                    return datetime.fromisoformat(match[1]).astimezone()
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except (OSError, ValueError):
        return datetime.fromtimestamp(0).astimezone()


def round_screenshot(row, directory):
    root = directory.resolve()
    for field in ('issue_screenshot', 'box_source', 'box_types_source'):
        source = row.get(field)
        if not isinstance(source, str) or not source:
            continue
        try:
            path = (root / Path(source).name).resolve(strict=True)
            if path.parent == root and path.suffix.lower() == '.png' and path.is_file():
                return path
        except (OSError, ValueError):
            continue
    return None


def history_result_notes(summary):
    lines = []
    for label, known in (('Box counts', 'known_box_rounds'),
                         ('Coins', 'known_coin_rounds'),
                         ('EXP', 'known_exp_rounds')):
        unread = summary['completed'] - summary[known]
        if unread:
            unit = 'round' if unread == 1 else 'rounds'
            lines.append(f'{label} unavailable for {unread:,} {unit}')
        if label == 'Box counts':
            unknown_types = summary['box_type_totals']['unknown']
            if unknown_types:
                unit = 'box' if unknown_types == 1 else 'boxes'
                lines.append(f'{unknown_types:,} {unit} with unknown type')
    return '\n'.join(lines)


def add_tooltip(widget, text):
    window = None
    pending = None

    def show():
        nonlocal window, pending
        pending = None
        content = text() if callable(text) else text
        if not content:
            return
        window = tk.Toplevel(widget)
        window.wm_overrideredirect(True)
        window.geometry(f'+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 4}')
        tk.Label(window, text=content, bg=FIELD, fg=INK, padx=8, pady=4,
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


SHORT_LOG_MESSAGES = {
    'Ready. Press Start to connect to LDPlayer': 'Ready',
    'Start requested': 'Starting',
    'cookierun-classic-autorun started': 'Started',
    'Screen must be 1280x720 resolution for the bot to work properly': 'Requires 1280 × 720',
    'Statistics are saved in stats/summary.txt and stats/sessions/': 'Stats Saved to stats/',
    'Starting the game': 'Starting Round',
    'Playing the game': 'Playing',
    'Completing the game': 'Finishing Round',
    'Stop requested': 'Stopping',
    'Bot stopped by user': 'Stopped by User',
    'Stopped': 'Stopped',
    'Purchasing Fast Start': 'Buying Fast Start',
    'Purchasing Cookie Relay': 'Buying Cookie Relay',
    'Purchasing Random Boost': 'Buying Random Boost',
    'Purchasing Desired Random Boost': 'Buying Selected Boost',
    'Skipping Desired Random Boost. Please verify your in-game boost config is correct': 'Boost Skipped',
    'Using Fast Start': 'Fast Start Used',
    'Using Cookie Relay': 'Relay Used',
    'Opening jumps: waiting for Fast Start to finish': 'Waiting for Fast Start',
    'Skipping opening jumps; normal controls were not confirmed in time': 'Jumps Skipped · Controls Not Ready',
    'Accepting Mystery Box': 'Opening Boxes',
    'Accepting Congratulations': 'Closing Congratulations',
    'Accepting Level Up': 'Closing Level-up',
    'Accepting Daily Check-in': 'Claiming Check-in',
    'Accepting Daily Check-in Boost Set': 'Claiming Daily Boosts',
    'Accepting Daily Treasure': 'Claiming Daily Treasure',
    'Accepting Daily New': 'Closing Daily News',
    'Accepting Enter League': 'Entering League',
    'Accepting League Results': 'Closing League Results',
    'Accepting Previous Rank Results': 'Closing Rank Results',
    'Accepting Too Many Treasures': 'Closing Treasure Limit',
    'Accepting Overtake Break Score': 'Closing Score Notice',
    'Opening Relic Complete': 'Opening Relic',
    'Accepting Relic Claim': 'Claiming Relic',
    'Closing announcement dialog': 'Closing Announcement',
    'Closing Party Run mode': 'Exiting Party Run',
    'Closing Game Settings': 'Closing Settings',
    'Handling Inactive state': 'Resuming Game',
    'Handling Quick Receive and Send Lives': 'Checking Mailbox',
    'No lives to receive. Proceeding to send lives': 'No Hearts to Receive',
    'Receiving all lives': 'Receiving Hearts',
    'Sending lives to friends': 'Sending Hearts',
    'All lives received and sent. Done': 'Heart Check Complete',
    'Quick Receive and Send Lives completed': 'Heart Check Complete',
    'Quick heart workflow timed out. Closing mailbox': 'Heart Check Timed Out',
    'Connection restored. Back at the main menu': 'Reconnected · Main Menu',
    'Connection lost. The game did not return to the main menu. Check LDPlayer, then start again':
        'Reconnect Failed · Check LDPlayer',
    'Player verification required. Complete it in LDPlayer, then start again':
        'Verification Required · Check LDPlayer',
    'Update screen detected. Waiting for the game update to finish': 'Updating Game',
    'Update finished; game menu is ready': 'Update Complete',
    'Could not continue saving the activity log': 'Log Saving Failed',
    'Another session is running. Stop it before starting again': 'Session Already Running',
    'Result box count unreadable. Checking the Mystery Box screen if it appears':
        'Box Count Unreadable · Checking Mystery Box Screen',
}

SHORT_LOG_PATTERNS = tuple((re.compile(pattern), replacement) for pattern, replacement in (
    (r'Connecting to device at .+\.\.\.', 'Connecting to LDPlayer'),
    (r'(?:Already connected to|Connected to) \S+', 'LDPlayer Connected'),
    (r'Waiting (\d+) seconds for screen refresh\.\.\.', r'Menu Wait · \1s'),
    (r'Waiting for (\d+)(?:\.0+)? seconds before starting the next game\.\.\.', r'Next Round in \1s'),
    (r'Waiting for (\d+\.\d+) seconds before starting the next game\.\.\.', r'Next Round in \1s'),
    (r'Round (\d+) started\.', r'Round \1 Started'),
    (r'Round (\d+) Complete 1 Mystery Box -> (.+)', r'Round \1 · 1 Box → \2'),
    (r'Round (\d+) Complete (\d+) Mystery Box(?:es)? -> (.+)', r'Round \1 · \2 Boxes → \3'),
    (r'Round (\d+) Complete 1 Mystery Box', r'Round \1 · 1 Box'),
    (r'Round (\d+) Complete (\d+) Mystery Box(?:es)?', r'Round \1 · \2 Boxes'),
    (r'Round (\d+) Complete Mystery Boxes: unknown', r'Round \1 · Box Count Unknown'),
    (r'Round (\d+) interrupted\. (.+?)\.?', r'Round \1 Interrupted · \2'),
    (r'Round limit reached: (\d+) completed\. Stopping at the main menu\.', r'Round Limit Reached · \1'),
    (r'Stopped · Round limit reached \((\d+)\)', r'Stopped · Round Limit Reached · \1'),
    (r'Waiting for desired boost to be detected: (.+)\.\.\.', r'Finding Boost · \1'),
    (r'Desired Boost detected: (.+)!', r'Boost Found · \1'),
    (r"Timeout: Could not detect desired boost '(.+)' within (\d+) seconds\.", r'Boost Not Found · \1 · \2s'),
    (r'Opening jumps: (\d+) taps\.', r'Opening Jumps · \1 Taps'),
    (r'Heart interval reached \((.+)\) — receiving and sending lives\.\.\.', r'Heart Check Due · \1'),
    (r'Connection lost\. Tapping Confirm \((\d+/\d+)\)\.', r'Reconnecting · \1'),
    (r'Closing event popup \((\d+/\d+)\)\.', r'Closing Event Popup · \1'),
    (r"Closing Friend's Info \((\d+/\d+)\)\.", r"Closing Friend's Info · \1"),
    (r'Could not clear event popups after (\d+) attempts\. Screenshot: .*', r'Popups Not Cleared · \1 Attempts'),
    (r'Could not inspect update screen: .*', 'Update Check Failed'),
    (r'Update requires manual confirmation\. Screenshot: .*', 'Update Needs Confirmation'),
    (r'Update button did not advance after (\d+) attempts\. Screenshot: .*', r'Update Stalled · \1 Attempts'),
    (r'Update flow reached an unrecognized screen\. Screenshot: .*', 'Unknown Update Screen'),
    (r'Update exceeded (\d+) minutes\. Screenshot: .*', r'Update Timed Out · \1m'),
    (r'Update ADB command failed: .*', 'Update Connection Failed'),
    (r'Box count could not be confirmed\. Saved screenshot: .*', 'Box Count Unknown'),
    (r'Could not read box count; recorded as unknown: .*', 'Box Count Unknown'),
    (r'Could not confirm box types\. Screenshot: .*', 'Box Types Unknown'),
    (r'Could not read box types; keeping count as unknown type: .*', 'Box Types Unknown'),
    (r'Could not open (?:a log file|log): .*', 'Log Unavailable'),
    (r'Could not read statistics file: (.+)', r'Could Not Read Stats · \1'),
    (r'Failed to connect to (\S+)', r'Connection Failed · \1'),
))


def shorten_log_message(message):
    body = message.removeprefix('Warning: ').removeprefix('Error: ')
    body = LOG_SYMBOL.sub('', body, count=1)
    short = SHORT_LOG_MESSAGES.get(body.rstrip('.!…'))
    if short is not None:
        return short
    for pattern, replacement in SHORT_LOG_PATTERNS:
        match = pattern.fullmatch(body)
        if match:
            return match.expand(replacement)
    return message.removeprefix('Warning: ').removeprefix('Error: ')


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
    widget.insert('end', shorten_log_message(message) + '\n')


class ActivityOutput:
    def __init__(self, events):
        self.events = events
        self.pending = ''
        self.archive = None
        self.on_line = None

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
            line = line.rstrip('\r')
            self.emit(line)
            if self.on_line is not None:
                self.on_line(line)
        return len(value)

    def flush(self):
        if self.pending:
            self.write('\n')


def describe_session_error(error):
    message = str(error).strip() or type(error).__name__
    if isinstance(error, (subprocess.TimeoutExpired, subprocess.CalledProcessError)):
        command = tuple(error.cmd) if isinstance(error.cmd, (list, tuple)) else ()
        if command[:2] == ('adb', '-s') and command[3:5] == ('exec-out', 'screencap'):
            target = command[2]
            if isinstance(error, subprocess.TimeoutExpired):
                return (
                    f'Screen Capture Timed Out after {error.timeout:g}s ({target}). '
                    'If LDPlayer is black or frozen, restart it before pressing Start.',
                    'Screen Capture Timed Out\nCheck LDPlayer, then press Start.',
                )
            detail = (error.stderr or b'').decode(errors='replace')
            if 'offline' in detail.lower():
                return (
                    f'ADB Device Offline ({target}). To reconnect in PowerShell, run '
                    f'adb disconnect {target} and then adb connect {target}.',
                    'ADB Device Offline\nReconnect ADB, then press Start.',
                )
    if message.startswith('Connection lost.'):
        return message, 'Connection Lost\nCheck LDPlayer, then start again.'
    if message.startswith('Player verification required.'):
        return message, 'Verification Required\nComplete it in LDPlayer.'
    if message == 'Send Hearts could not find the main menu. Check LDPlayer.':
        return message, 'Main Menu Not Found\nOpen the main menu in LDPlayer.'
    if message == 'Heart sending could not continue. Check LDPlayer and the Activity Log.':
        return message, 'Heart Sending Incomplete\nCheck LDPlayer and the Activity Log.'
    if message == 'Gift Draw could not find the bottom-right gift box. Check LDPlayer.':
        return message, 'Gift Box Not Found\nCheck the Gift Draw screen in LDPlayer.'
    return message, None


def run_session(options, stop, events):
    class WindowStatistics(RunStatistics):
        def __init__(self, directory=None):
            super().__init__(directory)
            self.issue_streak = 0
            self.preparing = None
            output.on_line = self.observe_issue
            if log_path is not None:
                self.session['activity_log'] = log_path.name
                self.save()

        def begin(self):
            is_new = self.current is None
            super().begin()
            if is_new:
                if self.preparing:
                    self.current.update(self.preparing)
                    self.save()
                self.preparing = None
                output.emit(f'Round {len(self.session["rounds"])} started.')

        def observe_issue(self, line):
            symbol = LOG_SYMBOL.match(line)
            icon = symbol['icon'] if symbol else ''
            message = line[symbol.end():] if symbol else line
            if message.startswith('Screen must be 1280x720'):
                return
            if (icon in ('⚠', '❌') or
                    message.startswith(('Warning:', 'Error:', 'Timeout:'))):
                severity = 'Error' if icon == '❌' or message.startswith('Error:') else 'Warning'
                message = message.removeprefix('Warning: ').removeprefix('Error: ')
                self.record_issue(severity, message)
            elif message == 'Detected Stage: CONNECTION_LOST':
                self.record_issue('Warning', 'Connection lost in LDPlayer.')
                if self.current is None and self.preparing is not None:
                    self.issue_streak += 1
                    self.preparing = None

        def record_issue(self, severity, message):
            row = self.current if self.current is not None else self.preparing
            if row is None or stop.is_set():
                return
            issues = row.setdefault('round_issues', [])
            entry = f'{severity}: {message}'
            if entry in issues:
                return
            issues.append(entry)
            if len(issues) != 1 or self.issue_streak + 1 < ISSUE_SCREENSHOT_STREAK:
                return
            number = len(self.session['rounds']) + (self.current is None)
            try:
                frame = bot.device_capture_screen(bot.DEVICE_IP, bot.DEVICE_PORT)
                row['issue_screenshot'] = save_evidence(frame, f'round_{number}_issue')
            except KeyboardInterrupt:
                if not stop.is_set():
                    raise
            except Exception as error:
                output.emit(f'Warning: Round {number} issue screenshot unavailable: {error}')
            else:
                output.emit(f'📸 Round {number} issue screenshot saved: {row["issue_screenshot"]}')

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
            if self.current:
                if self.current['status'] == 'running':
                    output.emit(f'Warning: Round {len(self.session["rounds"])} interrupted. {reason}.')
                if self.current.get('round_issues'):
                    self.issue_streak += 1
                elif self.current['status'] == 'completed':
                    self.issue_streak = 0
            super().leave_round(reason)

        def print_summary(self):
            events.put(('summary', (dict(self.session['summary']), session_duration(self.session))))

    token = stop_signal.set(stop)
    message = 'Stopped'
    display = None
    failed = False
    output = ActivityOutput(events)
    log_path = None
    statistics = None

    def new_statistics():
        nonlocal statistics
        statistics = WindowStatistics(STATS_DIR)
        return statistics

    def update_status(state):
        if (state == 'Purchase Item' and statistics is not None and
                statistics.current is None and statistics.preparing is None):
            statistics.preparing = {}
        events.put(('status', state))

    def record_error(error):
        if statistics is not None:
            message, _ = describe_session_error(error)
            statistics.record_issue('Error', message)

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
            mode = options.get('run_mode', 'auto')
            if mode == 'auto':
                bot.save_options(bot.SETTINGS_PATH, options)
            elif mode == 'gifts':
                saved = bot.load_saved_options(bot.SETTINGS_PATH) or {
                    'use_fast_start': False, 'use_cookie_relay': False,
                    'use_desired_random_boost': False, 'detect_relic': False,
                }
                saved['gift_limit'] = options['gift_limit']
                bot.save_options(bot.SETTINGS_PATH, saved)
            with redirect_stdout(output):
                outcome = bot.main(options, stop=stop, on_status=update_status,
                                   statistics_factory=new_statistics, on_error=record_error)
                message = outcome or message
    except Exception as error:
        failed = True
        message, display = describe_session_error(error)
        output.emit(f'Error: {message}')
    finally:
        output.flush()
        if not failed:
            output.emit(message)
        if output.archive is not None:
            output.archive.close()
        stop_signal.reset(token)
        events.put(('done', (message, failed, display)))


def help_circle(parent, size):
    icon = tk.PhotoImage(master=parent, width=size, height=size)
    radius = (size - 2) / 2
    center = (size - 1) / 2
    for y in range(1, size - 1):
        reach = int((radius * radius - (y - center) ** 2) ** 0.5)
        left = int(center) - reach
        icon.put('#3b5378', to=(left, y, size - left, y + 1))
    return icon


def create_run_buttons(parent, start, stop):
    style = {
        'width': 11, 'relief': 'flat', 'font': ('Segoe UI', 12, 'bold'),
        'disabledforeground': '#8893a2', 'highlightthickness': 1,
        'highlightbackground': BORDER, 'highlightcolor': '#b7d4ff',
    }
    return (
        tk.Button(parent, text='Start', command=start, fg='#f4f7ff',
                  activebackground='#207b5b', activeforeground='#f4f7ff', **style),
        tk.Button(parent, text='Stop', command=stop, fg='#f4f7ff',
                  activebackground='#af4653', activeforeground='#f4f7ff', **style),
    )


def enable_run_buttons(start, stop, *, start_enabled, stop_enabled):
    for button, enabled, color in ((start, start_enabled, START_COLOR),
                                   (stop, stop_enabled, STOP_COLOR)):
        button.config(state='normal' if enabled else 'disabled',
                      bg=color if enabled else FIELD,
                      cursor='hand2' if enabled else 'arrow')


class UtilityDialog:
    def __init__(self, owner, mode):
        self.mode = mode
        self.close_when_stopped = False
        self.window = window = tk.Toplevel(owner.root)
        title = 'Send Hearts' if mode == 'hearts' else 'Open Gifts'
        window.title(title)
        window.transient(owner.root)
        window.resizable(False, False)
        window.config(bg=PANEL, padx=16, pady=14)
        window.protocol('WM_DELETE_WINDOW', owner.close_utility)
        window.bind('<Escape>', lambda _event: owner.close_utility())
        owner.label(window, title, 14, bold=True).pack(anchor='w')
        description = ('Sends hearts until none remain or you press Stop.'
                       if mode == 'hearts' else
                       'Open earned gifts, then return to the main menu.')
        tk.Label(window, text=description, bg=PANEL, fg=MUTED, font=('Segoe UI', 10),
                 wraplength=340, justify='left').pack(anchor='w', pady=(4, 12))

        self.gift_limit = None
        if mode == 'gifts':
            count_row = tk.Frame(window, bg=PANEL)
            count_row.pack(fill='x', pady=(0, 10))
            owner.label(count_row, 'Gift Draw Limit', 10).pack(side='left', padx=(0, 10))
            self.gift_limit = tk.Entry(
                count_row, width=7, bg=FIELD, fg=INK, insertbackground=INK,
                disabledbackground=PANEL, disabledforeground=MUTED,
                relief='flat', highlightthickness=1, highlightbackground=BORDER,
                highlightcolor=GREEN, font=('Segoe UI', 10))
            self.gift_limit.insert(0, str(owner.gift_limit))
            self.gift_limit.pack(side='left', ipady=2)

        metric = tk.Frame(window, bg=FIELD, padx=12, pady=8)
        metric.pack(fill='x', pady=(0, 10))
        owner.label(metric, 'Hearts Sent' if mode == 'hearts' else 'Gifts Opened',
                    10, bold=True, bg=FIELD).pack(side='left')
        self.progress_count = owner.label(metric, '0' if mode == 'hearts' else '0 / 1',
                                          17, bold=True, bg=FIELD, fg=GREEN)
        self.progress_count.pack(side='right')
        if mode == 'gifts':
            self.show_progress(0, owner.gift_limit)

        self.status_font = owner.status_font
        self.status_label = tk.Label(window, text='Ready', bg=PANEL, fg=MUTED,
                                     font=self.status_font, justify='left',
                                     anchor='nw', height=2, wraplength=340)
        self.status_label.pack(fill='x', pady=(0, 8))
        self.full_status = 'Ready'
        add_tooltip(self.status_label, lambda: self.full_status
                    if self.status_label.cget('text') != self.full_status else '')
        controls = tk.Frame(window, bg=PANEL)
        controls.pack(fill='x')
        self.start_button, self.stop_button = create_run_buttons(
            controls, owner.start_utility, owner.stop)
        controls.columnconfigure((0, 2), weight=1, uniform='utility-actions')
        controls.columnconfigure(1, minsize=8)
        self.start_button.grid(row=0, column=0, sticky='ew', ipady=3)
        self.stop_button.grid(row=0, column=2, sticky='ew', ipady=3)
        self.set_controls(running=False)

        window.update_idletasks()
        width, height = max(370, window.winfo_reqwidth()), window.winfo_reqheight()
        x = owner.root.winfo_rootx() + (owner.root.winfo_width() - width) // 2
        y = owner.root.winfo_rooty() + (owner.root.winfo_height() - height) // 2
        window.geometry(f'{width}x{height}+{max(0, x)}+{max(0, y)}')
        window.wait_visibility()
        window.grab_set()
        (self.gift_limit or self.start_button).focus_set()

    def set_status(self, message, display, color):
        self.full_status = message
        text = fit_status_text(display, 340, self.status_font.measure)
        self.status_label.config(text=text, fg=color)

    def show_progress(self, count, total=None):
        self.progress_count.config(text=f'{count} / {total}' if total is not None else str(count))

    def set_controls(self, *, running, stopping=False):
        enable_run_buttons(self.start_button, self.stop_button,
                           start_enabled=not running, stop_enabled=running and not stopping)
        if self.gift_limit is not None:
            self.gift_limit.config(state='disabled' if running else 'normal')


class DesktopWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.stop_signal = threading.Event()
        self.worker = None
        self.closing = False
        self.target_rounds = 0
        self.history_window = None
        self.round_details_window = None
        self.logs_window = None
        self.help_window = None
        self.utility = None
        box_icons = {key: tk.PhotoImage(file=ROOT / 'ui_assets' / f'{key}.png')
                     for key in BOX_ORDER}
        self.images = {key: image.subsample(3, 3) for key, image in box_icons.items()}
        self.latest_box_images = {key: image.subsample(4, 4) for key, image in box_icons.items()}
        self.reward_icons = {name: tk.PhotoImage(master=root, file=ROOT / 'ui_assets' / f'{name}.png')
                             for name in REWARD_FIELDS}
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
        style.configure('Dark.Treeview', background=BACK, fieldbackground=BACK,
                        foreground=INK, bordercolor=BORDER, font=('Segoe UI', 10))
        style.configure('Dark.Treeview.Heading', background=FIELD, foreground=INK,
                        font=('Segoe UI', 9, 'bold'))
        style.map('Dark.Treeview', background=[('selected', '#275141')],
                  foreground=[('selected', INK)])
        root.option_add('*TCombobox*Listbox.background', FIELD)
        root.option_add('*TCombobox*Listbox.foreground', INK)
        root.option_add('*TCombobox*Listbox.selectBackground', '#275141')

        header = tk.Frame(root, bg=BACK)
        header.grid(row=0, column=0, columnspan=2, sticky='ew', padx=12, pady=(7, 5))
        header.columnconfigure(0, weight=1)

        title_group = tk.Frame(header, bg=BACK)
        title_group.grid(row=0, column=0, sticky='w')
        self.label(title_group, TITLE, 15, bold=True, bg=BACK).pack(side='left', padx=(0, 8))
        help_font = Font(root=root, family='Segoe UI', size=11, weight='bold')
        self.help_icon = help_circle(title_group, max(26, help_font.metrics('linespace') + 7))
        self.help_button = tk.Button(
            title_group, text='?', image=self.help_icon, compound='center', command=self.show_help,
            font=help_font, fg='#f4f7ff', bg=BACK, activeforeground='white', activebackground=BACK,
            relief='flat', bd=0, padx=0, pady=0, highlightthickness=1,
            highlightbackground=BACK, highlightcolor='#b7d4ff', cursor='hand2')
        self.help_button.pack(side='left', padx=(0, 12))
        add_tooltip(self.help_button, 'Help')

        self.utility_icons = {
            mode: tk.PhotoImage(master=root, file=ROOT / 'ui_assets' / filename)
            for mode, filename in (('hearts', 'send-hearts.png'), ('gifts', 'open-gifts.png'))
        }
        hearts_button = self.small_button(
            title_group, 'Send Hearts', lambda: self.show_utility('hearts'),
            icon=self.utility_icons['hearts'])
        hearts_button.pack(side='left', padx=(0, 6), ipady=3)
        gifts_button = self.small_button(
            title_group, 'Open Gifts', lambda: self.show_utility('gifts'),
            icon=self.utility_icons['gifts'])
        gifts_button.pack(side='left', ipady=3)

        run_controls = tk.Frame(header, bg=BACK)
        run_controls.grid(row=0, column=1, sticky='e', padx=(12, 0))
        self.start_button, self.stop_button = create_run_buttons(run_controls, self.start, self.stop)
        self.set_run_controls(start_enabled=True, stop_enabled=False)
        self.start_button.grid(row=0, column=0, padx=(0, 8), ipady=4)
        self.stop_button.grid(row=0, column=1, ipady=4)

        self.status_font = Font(root=root, family='Segoe UI', size=10)
        sidebar = tk.Frame(root, bg=BACK)
        sidebar.grid(row=1, column=0, sticky='nsew', padx=(12, 5), pady=(0, 10))
        sidebar.columnconfigure(0, weight=1)
        settings = self.panel(sidebar, 2, 'Settings', pady=0)
        choices = tk.Frame(settings, bg=PANEL)
        choices.grid(row=1, column=0, columnspan=2, sticky='ew')
        choices.columnconfigure((0, 1), weight=1, uniform='choices')
        saved = bot.load_saved_options(bot.SETTINGS_PATH) or {}
        self.gift_limit = saved.get('gift_limit', 1)
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
            control.grid(row=row, column=column, sticky='ew')
            add_tooltip(control, tip)
            self.inputs.append(control)
        tk.Frame(settings, bg=BORDER, height=1).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(3, 3))
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
        limit.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(3, 1))
        limit_label = self.label(limit, 'Round Limit', 10)
        limit_label.pack(side='left', padx=(0, 10))
        self.round_limit = tk.Entry(limit, width=6, bg=FIELD, fg=INK, insertbackground=INK,
                                    disabledbackground=PANEL, disabledforeground=MUTED,
                                    relief='flat', highlightthickness=1,
                                    highlightbackground=BORDER, highlightcolor=GREEN,
                                    font=('Segoe UI', 10))
        self.round_limit.insert(0, str(saved.get('round_limit', 0)))
        self.round_limit.pack(side='left', ipady=1)
        for target in (limit_label, self.round_limit):
            add_tooltip(target, 'Stops at the main menu after N completed runs. 0 keeps running until you stop it.')
        self.inputs.append(self.round_limit)
        self.label(limit, '0 = Unlimited', 9, fg=MUTED).pack(side='left', padx=8)

        latest = self.panel(sidebar, 0, 'Latest Round')
        self.latest_text = self.label(latest, 'Awaiting first round', 9, fg=MUTED)
        self.latest_text.grid(row=0, column=1, sticky='e', pady=(0, 2))
        self.latest_detail = ''
        add_tooltip(self.latest_text, lambda: self.latest_detail)
        self.latest_reward_widgets = self.reward_row(latest, 1)
        tk.Frame(latest, bg=BORDER, height=1).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(1, 4))
        self.latest_grades = self.grade_row(latest, 3, compact=True)

        summary = tk.Frame(sidebar, bg=PANEL, padx=4, pady=4,
                           highlightbackground=BORDER, highlightthickness=1)
        summary.grid(row=1, column=0, sticky='ew', pady=(0, 7))
        summary.columnconfigure(0, weight=1)
        self.label(summary, 'Summary', 12, bold=True).grid(
            row=0, column=0, sticky='w', padx=(6, 0), pady=(0, 2))
        self.last_session_button = self.small_button(
            summary, 'History', self.show_last_session)
        self.last_session_button.grid(row=0, column=1, sticky='e', pady=(0, 4))

        summary_body = tk.Frame(summary, bg=PANEL)
        summary_body.grid(row=1, column=0, columnspan=2, sticky='ew', padx=6)
        summary_body.columnconfigure(0, weight=1)
        self.summary_reward_widgets = self.reward_row(summary_body, 0, total=True)
        tk.Frame(summary_body, bg=BORDER, height=1).grid(
            row=1, column=0, columnspan=2, sticky='ew', pady=(2, 5))
        self.metrics = self.metric_row(summary_body, 2)
        tk.Frame(summary_body, bg=BORDER, height=1).grid(
            row=3, column=0, columnspan=2, sticky='ew', pady=(2, 4))
        self.label(summary_body, 'Boxes by type', 9, fg=MUTED).grid(
            row=4, column=0, columnspan=2, sticky='w')
        self.summary_grades = self.grade_row(summary_body, 5)
        self.summary_note = self.label(summary_body, 'Available after Stop', 9, fg=MUTED)
        self.summary_note.config(wraplength=300, justify='left')
        self.summary_note.grid(row=6, columnspan=2, sticky='w')

        self.inputs.extend((hearts_button, gifts_button))

        activity = tk.Frame(root, bg=PANEL, padx=10, pady=4,
                            highlightbackground=BORDER, highlightthickness=1)
        activity.grid(row=1, column=1, sticky='nsew', padx=(5, 12), pady=(0, 10))
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(2, weight=1)
        log_header = tk.Frame(activity, bg=PANEL)
        log_header.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        log_header.columnconfigure(1, weight=1)
        self.label(log_header, 'Activity Log', 12, bold=True).grid(
            row=0, column=0, sticky='w', padx=(0, 9))
        self.status = tk.StringVar(value='Ready · LDPlayer connection checked on Start')
        self.status_text = 'Ready'
        self.status_label = tk.Label(log_header, text=self.status_text, bg=PANEL, fg=MUTED,
                                     font=self.status_font, width=1, height=1, anchor='w',
                                     padx=0, bd=0, justify='left')
        self.status_label.grid(row=0, column=1, sticky='ew', padx=(0, 8))
        self.status_label.bind('<Configure>', self.refresh_status_text)
        add_tooltip(self.status_label, lambda: self.status.get()
                    if self.status_label.cget('text').replace('\n', ' ') != self.status.get() else '')
        log_buttons = tk.Frame(log_header, bg=PANEL)
        log_buttons.grid(row=0, column=2, sticky='e')
        self.small_button(log_buttons, 'Rounds', self.show_rounds).pack(side='left', padx=(0, 5))
        self.small_button(log_buttons, 'Open Logs', self.show_logs).pack(side='left', padx=(0, 5))
        self.progress_label = self.label(activity, '', 9, fg=MUTED)
        self.progress_label.grid(row=1, column=0, sticky='e', pady=(0, 3))
        self.progress_label.grid_remove()
        log_body = tk.Frame(activity, bg=BACK)
        log_body.grid(row=2, column=0, sticky='nsew')
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
        preferred_width = max(760, root.winfo_reqwidth(), round(sidebar.winfo_reqwidth() / 0.4))
        work_left = work_top = 0
        width_limit = max(1, root.winfo_screenwidth() - 24)
        height_limit = max(1, root.winfo_screenheight() - 88)
        if os.name == 'nt':
            from ctypes import byref, windll
            from ctypes.wintypes import RECT

            work_area = RECT()
            if windll.user32.SystemParametersInfoW(0x0030, 0, byref(work_area), 0):
                work_left, work_top = work_area.left, work_area.top
                width_limit = max(1, work_area.right - work_area.left - 24)
                height_limit = max(1, work_area.bottom - work_area.top - 48)
        minimum_height = min(root.winfo_reqheight(), height_limit)
        root.minsize(min(preferred_width, width_limit), minimum_height)
        height = max(minimum_height, min(560, height_limit))
        width = min(max(900, preferred_width), width_limit)
        x = work_left + (width_limit - width) // 2
        y = work_top + (height_limit - height) // 2
        root.geometry(f'{width}x{height}{x:+d}{y:+d}')
        self.root.after(100, self.poll)

    def label(self, parent, text, size, *, bold=False, bg=PANEL, fg=INK):
        return tk.Label(parent, text=text, bg=bg, fg=fg,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'))

    def small_button(self, parent, text, command, *, icon=None):
        return tk.Button(parent, text=text, command=command, image=icon, compound='left',
                         bg=FIELD, fg=INK,
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
                'Press Stop at any time, or set Round Limit to finish at the main menu after that many completed rounds. The header shows your progress when a limit is set. 0 means unlimited.',
            )),
            ('Saved settings', (
                'Open Send Hearts or Open Gifts in the top bar. Each has its own Start and Stop controls and returns to the main menu when finished.',
                'Gift Draw Limit sets how many gifts to open. Each successful draw uses one earned gift.',
                'Fast Start: Buys the boost and taps its opening prompt.',
                'Cookie Relay: Buys Relay and uses it when the relay prompt appears.',
                'Jump 7 times at start: Taps Jump when controls are ready. With Fast Start, skips the jumps if the controls cannot be confirmed afterward.',
                'Random Boost: Tries to buy your selected boost each run. Choose Off to skip this purchase.',
                'Claim Relics: Claims Relic rewards when their screen appears.',
            )),
            ('Automatic behavior', (
                f'Round 1 begins when the menu is ready. Later rounds wait an extra {UI_NEXT_ROUND_DELAY} seconds.',
                f'Every {LIVES_INTERVAL // 60} minutes, at the main menu, the app checks Mailbox → Lives and tries Quick Receive & Send if hearts are available.',
                'The app closes recognized event popups one at a time and checks the screen again after each close.',
                'If Connection Lost appears, the app taps Confirm and waits for the main menu. It retries once if the dialog is still visible.',
                'The app stops if the main menu does not return or if player verification appears.',
            )),
            ('Results and logs', (
                'Latest Round shows Coins, EXP and boxes from the most recent result. A dash marks an unread value.',
                'Summary shows totals after stopping. Coins and EXP include only rounds with confirmed values. History opens earlier summaries.',
                'Rounds shows Coins, EXP and boxes for each completed round in a saved run.',
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

    def panel(self, parent, row, title, *, column=0, sticky='ew', padx=0, pady=(0, 7)):
        panel = tk.Frame(parent, bg=PANEL, padx=10, pady=4,
                         highlightbackground=BORDER, highlightthickness=1)
        panel.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
        panel.columnconfigure(0, weight=1)
        self.label(panel, title, 12, bold=True).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 2))
        return panel

    def grade_row(self, parent, row, *, compact=False):
        strip = tk.Frame(parent, bg=PANEL)
        strip.grid(row=row, column=0, columnspan=2, sticky='ew')
        values = {}
        images = self.latest_box_images if compact else self.images
        for index, key in enumerate(BOX_ORDER):
            strip.columnconfigure(index, weight=1, uniform='grades')
            tile = tk.Frame(strip, bg=PANEL)
            tile.grid(row=0, column=index, sticky='w')
            icon = tk.Label(tile, image=images[key], bg=PANEL)
            icon.pack(side='left')
            value = self.label(tile, 'x0', 11 if compact else 14, bold=True, fg=GREEN)
            value.pack(side='left', padx=(5, 0))
            for target in (icon, value):
                add_tooltip(target, f'{BOX_TYPE_LABELS[key]} Mystery Box')
            values[key] = value
        return values

    def reward_row(self, parent, row, *, total=False):
        rewards = tk.Frame(parent, bg=PANEL)
        rewards.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 2))
        rewards.columnconfigure((0, 1), weight=1, uniform='rewards')
        values = {}
        for column, (name, label) in enumerate((('coins', 'Coins'), ('exp', 'EXP'))):
            tile = tk.Frame(rewards, bg=PANEL)
            tile.grid(row=0, column=column, sticky='w')
            tk.Label(tile, image=self.reward_icons[name], bg=PANEL).grid(
                row=0, column=0, rowspan=2, padx=(0, 5))
            self.label(tile, f'Total {label}' if total else label, 9, fg=MUTED).grid(
                row=0, column=1, sticky='w')
            value = self.label(tile, '0', 15, bold=True, fg=GREEN)
            value.grid(row=1, column=1, sticky='w')
            values[name] = value
        return values

    def show_rewards(self, widgets, amounts):
        for name, widget in widgets.items():
            value = amounts.get(name)
            widget.config(text='-' if value is None else f'{value:,}')

    def metric_row(self, parent, row):
        metrics = tk.Frame(parent, bg=PANEL)
        metrics.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(0, 4))
        widgets = []
        for index, name in enumerate(METRIC_NAMES):
            metrics.columnconfigure(index, weight=1)
            self.label(metrics, name, 9, fg=MUTED).grid(
                row=0, column=index, sticky='w', padx=(0, 6))
            value = self.label(metrics, EMPTY_METRICS[index], 16, bold=True, fg=GREEN)
            value.grid(row=1, column=index, sticky='w')
            widgets.append(value)
        return widgets

    def render_summary(self, summary, duration, metrics, grades, reward_widgets, note_widget):
        completed = summary['completed']
        values = (completed, summary['total_boxes'], duration)
        for widget, value in zip(metrics, values):
            widget.config(text=str(value))
        counts, note = box_display(summary['total_boxes'], summary['box_type_totals'])
        self.show_grades(grades, counts)
        if summary['unknown_box_rounds']:
            unread = f'Unknown box count: {summary["unknown_box_rounds"]} rounds'
            note = ' · '.join(filter(None, (note, unread)))
        rewards = {}
        coverage = {}
        for name, (total, known) in REWARD_FIELDS.items():
            count = summary[known]
            rewards[name] = summary[total]
            if count < completed:
                coverage.setdefault(count, []).append('Coins' if name == 'coins' else 'EXP')
        self.show_rewards(reward_widgets, rewards)
        coverage_notes = []
        unit = 'round' if completed == 1 else 'rounds'
        for count, labels in coverage.items():
            label = ' and '.join(labels)
            if count:
                coverage_notes.append(f'{label} total from {count} of {completed} {unit}')
            else:
                coverage_notes.append(f'{label} unavailable for {completed} {unit}')
        if note_widget is not None:
            note_widget.config(text=' · '.join(filter(None, (note, *coverage_notes))))

    def show_last_session(self):
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.destroy()
        window = self.history_window = tk.Toplevel(self.root)
        window.title('History')
        window.configure(bg=PANEL, padx=14, pady=10)
        window.columnconfigure((0, 1), weight=1)
        window.rowconfigure(0, minsize=34)
        window.rowconfigure(6, weight=1)
        window.transient(self.root)
        window.geometry('340x425')
        window.resizable(False, False)
        self.small_button(window, 'Open Folder',
                          lambda: self.open_session_folder(window)).grid(
                              row=8, column=0, columnspan=2, sticky='e', pady=(8, 0))
        rewards = self.reward_row(window, 1, total=True)
        tk.Frame(window, bg=BORDER, height=1).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(4, 5))
        metrics = self.metric_row(window, 3)
        self.label(window, 'Boxes by type', 9, fg=MUTED).grid(
            row=4, column=0, columnspan=2, sticky='w', pady=(4, 2))
        grades = self.grade_row(window, 5)
        distribution = tk.Frame(window, bg=PANEL)
        distribution.grid(row=6, column=0, columnspan=2, sticky='nsew', pady=(10, 0))
        distribution.columnconfigure(0, weight=1)
        distribution.rowconfigure(0, weight=1)
        style = ttk.Style(window)
        style.configure('BoxCounts.Treeview', background=PANEL, fieldbackground=PANEL, foreground=INK,
                        borderwidth=0, relief='flat', lightcolor=PANEL, darkcolor=PANEL,
                        font=('Segoe UI', 9), rowheight=19)
        style.configure('BoxCounts.Treeview.Heading', background=FIELD, foreground=MUTED,
                        borderwidth=0, relief='flat', lightcolor=FIELD, darkcolor=FIELD,
                        font=('Segoe UI', 9, 'bold'))
        counts = ttk.Treeview(distribution, columns=('boxes', 'share', 'rounds'), show='headings',
                              height=2, selectmode='none', style='BoxCounts.Treeview')
        counts.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(distribution, command=counts.yview, style='Dark.Vertical.TScrollbar')
        scroll.grid(row=0, column=1, sticky='ns')
        counts.configure(yscrollcommand=scroll.set)
        add_tooltip(counts, 'Percent Boxes uses only rounds with a confirmed box count, including zero.')
        for key, label, width in (('boxes', 'Boxes / Round', 107), ('share', 'Percent Boxes', 111),
                                  ('rounds', 'Rounds', 60)):
            anchor = 'w' if key == 'boxes' else 'e'
            counts.heading(key, text=label, anchor=anchor)
            counts.column(key, width=width, anchor=anchor)
        note = self.label(window, '', 9, fg=MUTED)
        note.config(wraplength=308, justify='left')
        note.grid(row=7, column=0, columnspan=2, sticky='w', pady=(8, 0))
        records = finished_sessions(STATS_DIR / 'sessions')
        if not records:
            self.label(window, 'No history yet', 13, bold=True).grid(
                row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
            note.config(text='Results appear here after a run ends.')
            return
        dates = tuple(record[0].strftime(SESSION_DATETIME_FORMAT) for record in records)
        selector = ttk.Combobox(window, values=dates, state='readonly', style='Dark.TCombobox')
        selector.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        selector.current(0)
        def refresh(_event=None):
            _, summary, duration, _, _ = records[selector.current()]
            self.render_summary(summary, duration, metrics, grades, rewards, note_widget=None)
            notice = history_result_notes(summary)
            if notice:
                note.config(text=notice, fg=AMBER)
                note.grid()
            else:
                note.grid_remove()
            counts.delete(*counts.get_children())
            for bucket in summary['distribution']:
                count = bucket['boxes']
                label = 'box' if count == 1 else 'boxes'
                counts.insert('', 'end', values=(f'{count} {label}', f'{bucket["percent_of_known"]:g}%',
                                                 f'{bucket["rounds"]:,}'))

        selector.bind('<<ComboboxSelected>>', refresh)
        refresh()

    def show_rounds(self):
        if self.round_details_window is not None and self.round_details_window.winfo_exists():
            self.round_details_window.destroy()
        window = self.round_details_window = tk.Toplevel(self.root)
        window.title('Rounds')
        window.transient(self.root)
        window.geometry('540x330')
        window.minsize(420, 260)
        window.configure(bg=PANEL, padx=12, pady=10)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        window.bind('<Escape>', lambda _event: window.destroy())
        records = finished_sessions(STATS_DIR / 'sessions')
        if not records:
            self.label(window, 'No completed rounds yet', 11, fg=MUTED).grid(
                row=1, column=0, sticky='n')
            return

        dates = tuple(record[0].strftime(SESSION_DATETIME_FORMAT) for record in records)
        selector = ttk.Combobox(window, values=dates, state='readonly', style='Dark.TCombobox')
        selector.grid(row=0, column=0, sticky='w', pady=(0, 7))
        selector.current(0)

        table = ttk.Treeview(window, columns=('round', 'coins', 'exp', 'boxes'),
                             show='headings', height=7, selectmode='browse',
                             style='Dark.Treeview')
        table.grid(row=1, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(window, command=table.yview, style='Dark.Vertical.TScrollbar')
        scroll.grid(row=1, column=1, sticky='ns')
        table.configure(yscrollcommand=scroll.set)
        for key, label, width in (('round', 'Round', 68), ('coins', 'Coins', 128),
                                  ('exp', 'EXP', 128), ('boxes', 'Boxes', 84)):
            anchor = 'center' if key == 'round' else 'e'
            table.heading(key, text=label, anchor=anchor)
            table.column(key, width=width, minwidth=55, anchor=anchor)
        rows = {}

        footer = tk.Frame(window, bg=PANEL)
        footer.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        box_details = tk.Frame(footer, bg=PANEL)
        box_details.pack(side='left', anchor='w')
        box_details.columnconfigure(0, weight=1)
        grades = self.grade_row(box_details, 0, compact=True)
        detail = self.label(box_details, '', 9, fg=MUTED)
        detail.config(wraplength=275, justify='left')
        detail.grid(row=1, column=0, sticky='w')

        def open_screenshot():
            selected = table.selection()
            path = round_screenshot(rows[selected[0]], STATS_DIR / 'screenshots') if selected else None
            if path is not None:
                try:
                    os.startfile(path)
                except OSError as error:
                    messagebox.showerror('Could not open screenshot', str(error), parent=window)
            refresh_selection()

        screenshot_button = self.small_button(footer, 'Open Screenshot', open_screenshot)
        screenshot_button.pack(side='right')

        def show_issues():
            selected = table.selection()
            if selected:
                row = rows[selected[0]]
                messagebox.showwarning('Round Issues', '\n\n'.join(row.get('round_issues', ())),
                                       parent=window)

        issue_button = self.small_button(window, 'Round Issues', show_issues)
        issue_button.grid(row=0, column=0, columnspan=2, sticky='e', pady=(0, 7))

        def refresh_selection(_event=None):
            selected = table.selection()
            row = rows[selected[0]] if selected else {}
            path = round_screenshot(row, STATS_DIR / 'screenshots')
            screenshot_button.config(state='normal' if path else 'disabled')
            issues = row.get('round_issues', ())
            issue_button.config(state='normal' if issues else 'disabled',
                                text=f'Round Issues ({len(issues)})' if issues else 'Round Issues')
            counts, note = box_display(row.get('boxes'), row.get('box_types'))
            self.show_grades(grades, counts)
            text = note or ('No screenshot saved' if not path else '')
            detail.config(text=text)
            if text:
                detail.grid()
            else:
                detail.grid_remove()

        def show_selected_run(_event=None):
            table.delete(*table.get_children())
            rows.clear()
            for number, row in records[selector.current()][3]:
                amounts = [row.get(key) for key in ('coins', 'exp', 'boxes')]
                values = [f'{amount:,}' if type(amount) is int and amount >= 0 else '-'
                          for amount in amounts]
                rows[table.insert('', 'end', values=(number, *values))] = row
            first = next(iter(rows))
            table.selection_set(first)
            table.focus(first)
            table.see(first)
            refresh_selection()

        table.bind('<<TreeviewSelect>>', refresh_selection)
        selector.bind('<<ComboboxSelected>>', show_selected_run)
        show_selected_run()
        table.focus_set()

    def open_session_folder(self, parent):
        directory = STATS_DIR / 'sessions'
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.startfile(directory)
        except OSError as error:
            messagebox.showerror('Could not open folder', str(error), parent=parent)

    def copy_log(self, widget):
        text = widget.get('1.0', 'end-1c')
        if not text:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        return True

    def show_logs(self):
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
        copied = tk.StringVar(window)
        tk.Label(window, textvariable=copied, bg=PANEL, fg=GREEN, anchor='e',
                 font=('Segoe UI', 9)).grid(row=2, column=0, sticky='ew', pady=(4, 0))
        ended = {record[4]: record[0] for record in finished_sessions(STATS_DIR / 'sessions')
                 if isinstance(record[4], str)}
        entries = sorted(((ended.get(path.name) or activity_log_end(path), path)
                          for path in (STATS_DIR / 'logs').glob('*.log')), reverse=True)
        paths = [path for _, path in entries]
        dates = [date.strftime(SESSION_DATETIME_FORMAT) for date, _ in entries]
        selector = ttk.Combobox(controls, values=('Current Activity', *dates),
                                width=29, state='readonly', style='Dark.TCombobox')
        selector.current(1 if paths else 0)
        selector.pack(side='left')
        issues_only = tk.BooleanVar(window, False)
        filter_button = tk.Checkbutton(controls, text='Error & Warnings', variable=issues_only,
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
            copied.set('')
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
            has_messages = view.index('end-1c') != '1.0'
            copy_button.config(state='normal' if has_messages else 'disabled')
            if not has_messages:
                view.insert('end', 'No matching log messages.')
            elif not issues_only.get():
                view.see('end')
            view.config(state='disabled')

        def copy_visible_log():
            if self.copy_log(view):
                copied.set('Log copied')

        selector.bind('<<ComboboxSelected>>', refresh)
        filter_button.config(command=refresh)
        self.small_button(controls, 'Refresh', refresh).pack(side='right')
        copy_button = self.small_button(controls, 'Copy Log', copy_visible_log)
        copy_button.pack(side='right', padx=5)
        refresh()

    def show_grades(self, widgets, values, *, missing=None):
        for key, widget in widgets.items():
            value = values.get(key, missing)
            widget.config(text='-' if value is None else f'x{value}')

    def append_log(self, timestamp, message):
        follow = self.log.yview()[1] >= 0.999
        self.log.config(state='normal')
        insert_log_line(self.log, message, timestamp.strftime('%Y-%m-%d %H:%M:%S') if message else None)
        if int(self.log.index('end-1c').split('.')[0]) > 2001:
            self.log.delete('1.0', '2.0')
        self.log.config(state='disabled')
        if follow:
            self.log.see('end')

    def refresh_status_text(self, _event=None):
        width = self.status_label.winfo_width()
        if width > 1:
            text = ' · '.join(self.status_text.splitlines())
            measure = self.status_font.measure
            if measure(text) > width:
                cutoff = bisect_right(range(len(text) + 1), width,
                                      key=lambda index: measure(text[:index] + '…')) - 1
                text = text[:max(0, cutoff)].rstrip() + '…'
            self.status_label.config(text=text)

    def set_status(self, message, color=MUTED, display=None):
        self.status.set(message)
        self.status_text = message if display is None else display
        self.status_label.config(fg=color)
        self.refresh_status_text()
        if self.utility is not None:
            self.utility.set_status(message, self.status_text, color)

    def show_progress(self, completed):
        target = self.target_rounds
        if target:
            self.progress_label.config(text=f'{completed} / {target} rounds completed')
            self.progress_label.grid()
        else:
            self.progress_label.grid_remove()

    def show_utility(self, mode):
        if self.utility is not None:
            self.utility.window.lift()
        elif self.worker is None:
            self.utility = UtilityDialog(self, mode)

    def close_utility(self):
        if self.utility is None:
            return
        if self.worker is not None:
            self.utility.close_when_stopped = True
            self.stop()
            return
        self.utility.window.destroy()
        self.utility = None

    def start_utility(self):
        if self.worker is not None or self.utility is None:
            return
        mode = self.utility.mode
        options = {'run_mode': mode, 'detect_relic': False}
        if mode == 'gifts':
            field = self.utility.gift_limit
            value = field.get().strip()
            limit = int(value) if value.isascii() and value.isdecimal() and len(value) <= 4 else 0
            if not 1 <= limit <= 9999:
                message = 'Enter a Gift Draw limit from 1 to 9999.'
                self.utility.set_status(message, message, RED)
                field.focus_set()
                return
            self.gift_limit = options['gift_limit'] = limit
        self.utility.show_progress(0, options.get('gift_limit'))
        self.start_session(options)

    def start(self):
        if self.worker is not None or self.utility is not None:
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
                       desired_boost_template=dict(bot.BOOST_CHOICES).get(name),
                       round_limit=round_limit, gift_limit=self.gift_limit)
        self.latest_text.config(text='Awaiting first round')
        self.latest_detail = ''
        self.summary_note.config(text='Available after Stop')
        for metric, value in zip(self.metrics, EMPTY_METRICS):
            metric.config(text=value)
        self.show_grades(self.latest_grades, {}, missing=0)
        self.show_grades(self.summary_grades, {}, missing=0)
        self.show_rewards(self.latest_reward_widgets, dict.fromkeys(REWARD_FIELDS, 0))
        self.show_rewards(self.summary_reward_widgets, dict.fromkeys(REWARD_FIELDS, 0))
        self.target_rounds = round_limit
        self.show_progress(0)
        self.start_session(options)

    def start_session(self, options):
        self.set_run_controls(start_enabled=False, stop_enabled=self.utility is None)
        if self.utility is not None:
            self.utility.set_controls(running=True)
        self.boost.config(state='disabled')
        for control in self.inputs:
            control.config(state='disabled')
        self.set_status('Connecting to LDPlayer…', AMBER)
        self.stop_signal = threading.Event()
        self.worker = threading.Thread(target=run_session, args=(options, self.stop_signal, self.events))
        self.worker.start()

    def stop(self):
        if self.stop_signal.is_set():
            return
        self.stop_signal.set()
        self.set_run_controls(start_enabled=False, stop_enabled=False)
        if self.utility is not None:
            self.utility.set_controls(running=True, stopping=True)
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
            elif kind == 'status':
                if self.utility is not None and payload.startswith('Gift Draw · '):
                    count, total = payload.split(' · ', 1)[1].split('/')
                    self.utility.show_progress(int(count), int(total))
                elif self.utility is not None and payload.startswith('Hearts Sent · '):
                    self.utility.show_progress(int(payload.split(' · ', 1)[1]))
                elif self.stop_signal.is_set():
                    continue
                elif payload in ('กรุณา Login', 'Waiting for Main Menu', 'Sending Hearts', 'Opening Gifts'):
                    self.set_status(payload, AMBER)
                elif payload.startswith('Reconnecting'):
                    self.set_status(payload, AMBER, display=f'Connection Lost\n{payload}…')
                else:
                    color = AMBER if payload == 'Waiting for next round' else GREEN
                    self.set_status(f'LDPlayer connected · {payload}', color)
            elif kind == 'progress':
                self.show_progress(payload)
            elif kind == 'round':
                number, row = payload
                count = row['boxes']
                quantity = 'Boxes: -' if count is None else f'{count} Box' + ('es' if count != 1 else '')
                grades, self.latest_detail = box_display(count, row.get('box_types'))
                self.latest_text.config(text=f'Round {number} · {quantity}')
                self.show_grades(self.latest_grades, grades)
                self.show_rewards(self.latest_reward_widgets, row)
            elif kind == 'summary':
                summary, duration = payload
                self.render_summary(summary, duration, self.metrics,
                                    self.summary_grades, self.summary_reward_widgets, self.summary_note)
            elif kind == 'done':
                self.worker = None
                if self.closing:
                    self.root.destroy()
                    return
                message, failed, display = payload
                self.set_status(message, RED if failed else MUTED, display=display)
                self.set_run_controls(start_enabled=True, stop_enabled=False)
                if self.utility is not None:
                    if self.utility.close_when_stopped:
                        self.close_utility()
                    else:
                        self.utility.set_controls(running=False)
                self.boost.config(state='readonly')
                for control in self.inputs:
                    control.config(state='normal')
        self.root.after(100, self.poll)

    def set_run_controls(self, *, start_enabled, stop_enabled):
        enable_run_buttons(self.start_button, self.stop_button,
                           start_enabled=start_enabled, stop_enabled=stop_enabled)

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
