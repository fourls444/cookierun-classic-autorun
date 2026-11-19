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
    if summary['interrupted']:
        lines.append(f'Interrupted rounds: {summary["interrupted"]}')
    return '\n'.join(lines)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def summarize(rounds):
    completed = [row for row in rounds if row['status'] == 'completed']
    known = [row for row in completed if row['boxes'] is not None]
    distribution = Counter(row['boxes'] for row in known)
    total = len(completed)
    type_totals = {name: 0 for name in BOX_TYPE_NAMES}
    for row in known:
        counts = row.get('box_types')
        if counts is None:
            type_totals['unknown'] += row['boxes']
        else:
            for name in BOX_TYPE_NAMES:
                type_totals[name] += counts.get(name, 0)
    total_boxes = sum(row['boxes'] for row in known)
    return {
        'started': len(rounds),
        'completed': total,
        'interrupted': sum(row['status'] == 'interrupted' for row in rounds),
        'unfinished': sum(row['status'] == 'running' for row in rounds),
        'known_box_rounds': len(known),
        'unknown_box_rounds': total - len(known),
        'total_boxes': total_boxes,
        'box_type_totals': type_totals,
        'box_type_percentages': {
            name: round(100 * count / total_boxes, 2) if total_boxes else 0.0
            for name, count in type_totals.items()
        },
        'distribution': [
            {'boxes': count, 'rounds': occurrences,
             'percent_of_completed': round(100 * occurrences / total, 2),
             'percent_of_known': round(100 * occurrences / len(known), 2)}
            for count, occurrences in sorted(distribution.items())
        ],
    }


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
        self.save()

    def begin(self):
        if self.current is not None:
            return
        row = {'id': uuid.uuid4().hex, 'started_at': now(), 'ended_at': None,
               'status': 'running', 'boxes': None, 'box_source': None,
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

    def leave_round(self, reason='Returned to menu'):
        if self.current is None:
            return
        if self.current['status'] == 'running':
            self.current['status'] = 'interrupted'
            self.current['ended_at'] = now()
            self.current['note'] = reason
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

    def save(self):
        self.session['summary'] = summarize(self.session['rounds'])
        write_json(self.path, self.session)
        all_rounds = []
        for path in sorted((self.directory / 'sessions').glob('*.json')):
            try:
                all_rounds.extend(json.loads(path.read_text(encoding='utf-8'))['rounds'])
            except (OSError, ValueError, KeyError):
                print(f'⚠️ Could not read statistics file: {path.name}')
        write_json(self.directory / 'summary.json', {
            'updated_at': now(), 'current_session': self.session['summary'],
            'all_sessions': summarize(all_rounds),
        })
        lines = [format_summary(self.session['summary'], 'SESSION SUMMARY'), '',
                 format_summary(summarize(all_rounds), 'ALL-TIME SUMMARY')]
        temporary = self.directory / 'summary.txt.tmp'
        temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
        os.replace(temporary, self.directory / 'summary.txt')

    def print_summary(self):
        print(format_summary(self.session['summary'], 'SESSION SUMMARY'))

    def print_round(self):
        row = self.current
        if row is None or row['status'] != 'completed' or row['id'] in self.reported_rounds:
            return
        number = next(index for index, item in enumerate(self.session['rounds'], 1)
                      if item['id'] == row['id'])
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
