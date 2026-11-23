"""Persistent per-run statistics. Unknown box counts are never counted as zero."""
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BOX_TYPE_NAMES = ('wood', 'silver', 'gold', 'rainbow', 'unknown')
REPORT_TYPE_NAMES = ('rainbow', 'gold', 'silver', 'wood', 'unknown')
BOX_TYPE_LABELS = {'wood': 'Wooden', 'silver': 'Silver', 'gold': 'Gold',
                   'rainbow': 'Rainbow', 'unknown': 'Unknown type'}
REWARD_FIELDS = {'coins': ('total_coins', 'known_coin_rounds'),
                 'exp': ('total_exp', 'known_exp_rounds')}


def format_summary(summary, title):
    lines = [title, f'Completed rounds: {summary["completed"]}']
    for bucket in reversed(summary['distribution']):
        noun = 'box' if bucket['boxes'] == 1 else 'boxes'
        rounds = 'round' if bucket['rounds'] == 1 else 'rounds'
        lines.append(f'{bucket["boxes"]} {noun}: {bucket["rounds"]} {rounds} '
                     f'({bucket["percent_of_completed"]:g}%)')
    if summary['unknown_box_rounds']:
        lines.append(f'Unknown box count: {summary["unknown_box_rounds"]} rounds')
    types = [f'{BOX_TYPE_LABELS[name]}: {summary["box_type_totals"][name]}'
             for name in REPORT_TYPE_NAMES
             if name != 'unknown' or summary['box_type_totals'][name]]
    lines.append(f'Total Mystery Boxes: {summary["total_boxes"]} -> ' + ', '.join(types))
    for name, (total, known) in REWARD_FIELDS.items():
        completed = summary['completed']
        count = summary[known]
        value = f'{summary[total]:,}' if count or not completed else 'Unknown'
        suffix = f' ({count}/{completed} rounds read)' if count < completed else ''
        lines.append(f'Total {"Coins" if name == "coins" else "EXP"}: {value}{suffix}')
    return '\n'.join(lines)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _summary(completed, distribution, type_totals, rewards):
    known = sum(distribution.values())
    total_boxes = sum(count * occurrences for count, occurrences in distribution.items())
    return {
        'completed': completed,
        'known_box_rounds': known,
        'unknown_box_rounds': completed - known,
        'total_boxes': total_boxes,
        **rewards,
        'box_type_totals': type_totals,
        'box_type_percentages': {
            name: round(100 * count / total_boxes, 2) if total_boxes else 0.0
            for name, count in type_totals.items()
        },
        'distribution': [
            {'boxes': count, 'rounds': occurrences,
             'percent_of_completed': round(100 * occurrences / completed, 2),
             'percent_of_known': round(100 * occurrences / known, 2)}
            for count, occurrences in sorted(distribution.items())
        ],
    }


def summarize(rounds):
    completed = 0
    distribution = Counter()
    type_totals = dict.fromkeys(BOX_TYPE_NAMES, 0)
    rewards = dict.fromkeys((key for fields in REWARD_FIELDS.values() for key in fields), 0)
    for row in rounds:
        if row['status'] != 'completed':
            continue
        completed += 1
        for name, (total, known) in REWARD_FIELDS.items():
            amount = row.get(name)
            if type(amount) is int and amount >= 0:
                rewards[total] += amount
                rewards[known] += 1
        count = row['boxes']
        if count is None:
            continue
        distribution[count] += 1
        counts = row.get('box_types')
        if counts is None:
            type_totals['unknown'] += count
        else:
            for name in BOX_TYPE_NAMES:
                type_totals[name] += counts.get(name, 0)
    return _summary(completed, distribution, type_totals, rewards)


def combine_summaries(summaries):
    completed = 0
    distribution = Counter()
    type_totals = Counter(dict.fromkeys(BOX_TYPE_NAMES, 0))
    rewards = dict.fromkeys((key for fields in REWARD_FIELDS.values() for key in fields), 0)
    for summary in summaries:
        completed += summary['completed']
        type_totals.update(summary['box_type_totals'])
        for key in rewards:
            rewards[key] += summary.get(key, 0)
        for bucket in summary['distribution']:
            distribution[bucket['boxes']] += bucket['rounds']
    return _summary(completed, distribution, dict(type_totals), rewards)


class RunStatistics:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path(__file__).parent / 'stats')
        sessions = self.directory / 'sessions'
        sessions.mkdir(parents=True, exist_ok=True)
        self.session = {'version': 2, 'id': uuid.uuid4().hex,
                        'started_at': now(), 'ended_at': None, 'rounds': []}
        self.path = sessions / (self.session['id'] + '.json')
        self.current = None
        self.reported_rounds = set()
        self.closed = False
        self._history_cache = {}
        self._history_summary = summarize([])
        self.save()

    def begin(self):
        if self.current is not None:
            return
        row = {'id': uuid.uuid4().hex, 'started_at': now(), 'ended_at': None,
               'status': 'running', 'boxes': None, 'box_source': None,
               'coins': None, 'exp': None,
               'note': None, 'box_types': None, 'box_types_source': None}
        self.session['rounds'].append(row)
        self.current = row
        self.save()

    def complete(self):
        if self.current is None:
            self.begin()
            self.current['note'] = 'Start was not observed; attached at result screen.'
        if self.current['status'] == 'completed':
            return
        self.current['status'] = 'completed'
        self.current['ended_at'] = now()
        self.save()

    def record_boxes(self, count, source):
        if self.current is None or self.current['status'] != 'completed':
            return
        if type(count) is not int or not 0 <= count <= 20:
            raise ValueError('Box count must be an integer from 0 to 20.')
        if self.current['boxes'] is not None:
            return
        self.current['boxes'] = count
        self.current['box_source'] = source
        self.save()

    def record_rewards(self, amounts):
        if self.current is None or self.current['status'] != 'completed':
            return
        if any(name not in REWARD_FIELDS or type(amount) is not int or amount < 0
               for name, amount in amounts.items()):
            raise ValueError('Rewards must be nonnegative integer Coins or EXP amounts.')
        new = {name: amount for name, amount in amounts.items()
               if self.current.get(name) is None}
        if new:
            self.current.update(new)
            self.save()

    def leave_round(self, reason='Returned to menu'):
        if self.current is None:
            return
        if self.current['status'] == 'running':
            self.session['rounds'].pop()
        else:
            if self.current['boxes'] and self.current.get('box_types') is None:
                self.current['box_types_note'] = reason + ': no confirmed box-type screen was recorded.'
            self.print_round()
        self.current = None
        self.save()

    def record_box_types(self, counts, source):
        if self.current is None or self.current['status'] != 'completed':
            return False
        if self.current.get('box_types') is not None or self.current['boxes'] is None:
            return False
        if set(counts) != set(BOX_TYPE_NAMES):
            raise ValueError('Box type counts must contain all five categories.')
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError('Box type counts must be nonnegative integers.')
        if sum(counts.values()) != self.current['boxes']:
            raise ValueError('Box type counts must match the confirmed round total.')
        self.current['box_types'] = dict(counts)
        self.current['box_types_source'] = source
        if counts['unknown']:
            self.current['box_types_note'] = 'Some visible boxes did not match a type confidently.'
        self.save()
        return True

    def _historical_summary(self):
        cached = self._history_cache
        current = {}
        # Directory entries can supply Windows file metadata without opening each file.
        with os.scandir(self.path.parent) as entries:
            for entry in entries:
                if entry.name == self.path.name or not entry.name.lower().endswith('.json'):
                    continue
                try:
                    metadata = entry.stat()
                    signature = (metadata.st_mtime_ns, metadata.st_size, metadata.st_ctime_ns)
                    record = cached.get(entry.name)
                    if record is None or record[0] != signature:
                        rows = json.loads(Path(entry.path).read_text(encoding='utf-8'))['rounds']
                        record = (signature, summarize(rows))
                    current[entry.name] = record
                except (OSError, ValueError, KeyError, TypeError):
                    print(f'⚠️ Could not read statistics file: {entry.name}')
        if current != cached:
            self._history_cache = current
            self._history_summary = combine_summaries(entry[1] for entry in current.values())
        return self._history_summary

    def save(self):
        summary = self.session['summary'] = summarize(self.session['rounds'])
        write_json(self.path, self.session)
        all_time = combine_summaries((self._historical_summary(), summary))
        write_json(self.directory / 'summary.json', {
            'updated_at': now(), 'current_session': summary, 'all_sessions': all_time,
        })
        lines = [format_summary(summary, 'SESSION SUMMARY'), '',
                 format_summary(all_time, 'ALL-TIME SUMMARY')]
        temporary = self.directory / 'summary.txt.tmp'
        temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
        os.replace(temporary, self.directory / 'summary.txt')

    def print_summary(self):
        print(format_summary(self.session['summary'], 'SESSION SUMMARY'))

    def print_round(self):
        row = self.current
        if row is None or row['status'] != 'completed' or row['id'] in self.reported_rounds:
            return
        number = len(self.session['rounds'])
        count = row['boxes']
        if count is None:
            report = f'Round {number} Complete Mystery Boxes: unknown'
        else:
            noun = 'Mystery Box' if count == 1 else 'Mystery Boxes'
            report = f'Round {number} Complete {count} {noun}'
            types = row.get('box_types') or {'unknown': count}
            details = [f'{BOX_TYPE_LABELS[name]}: {types.get(name, 0)}'
                       for name in REPORT_TYPE_NAMES if types.get(name, 0)]
            if details:
                report += ' -> ' + ', '.join(details)
        print(report)
        self.reported_rounds.add(row['id'])

    def close(self):
        if self.closed:
            return
        self.leave_round('Bot stopped')
        self.session['ended_at'] = now()
        self.save()
        self.print_summary()
        self.closed = True


if __name__ == '__main__':
    path = Path(__file__).parent / 'stats' / 'summary.txt'
    print(path.read_text(encoding='utf-8-sig') if path.exists()
          else 'No statistics yet. Run the bot first.')
