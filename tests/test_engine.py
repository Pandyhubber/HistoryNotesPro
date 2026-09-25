"""Pure logic: helpers, timetracking engine, archive selection. Includes randomized equivalence against V21."""
import random
import re
import unittest
from datetime import date

from support import notes, new_dir, load_old_module, HAVE_V21

E = notes.TimetrackingEngine()
S_EN = notes.STR_TABLE['EN']
S_DE = notes.STR_TABLE['DE']


class HelperTests(unittest.TestCase):
    def test_fmt_hours(self):
        cases = {0: '0', 1: '1', 2.0: '2', 10.0: '10', 2.5: '2.5', 0.25: '0.25', 0.75: '0.75',
                 1.25: '1.25', 2.1: '2.1', 0.1 + 0.2: '0.3', 7.999: '8', 100.5: '100.5'}
        for value, expected in cases.items():
            self.assertEqual(notes.fmt_hours(value), expected, value)

    def test_changed_chars(self):
        c = notes.changed_chars
        self.assertEqual(c('abc', 'abc'), 0)
        self.assertEqual(c('1.5h X-1', '2.5h X-1'), 1)
        self.assertEqual(c('', 'hello'), 5)
        self.assertEqual(c('hello', ''), 5)
        self.assertEqual(c('aaaa', 'aaaaa'), 1)          # repeated chars, pure insert
        self.assertEqual(c('abcdef', 'abXYZdef'), 3)
        self.assertEqual(c('abcdef', 'aXcdeY'), 5)       # two edits far apart span the middle
        rnd = random.Random(1)
        for _ in range(300):
            a = ''.join(rnd.choice('ab\n') for _ in range(rnd.randint(0, 30)))
            b = ''.join(rnd.choice('ab\n') for _ in range(rnd.randint(0, 30)))
            p = 0
            while p < min(len(a), len(b)) and a[p] == b[p]:
                p += 1
            s = 0
            while s < min(len(a), len(b)) - p and a[-1 - s] == b[-1 - s]:
                s += 1
            self.assertEqual(c(a, b), max(len(a), len(b)) - p - s if a != b else 0, (a, b))

    def test_period_range(self):
        pr = notes.period_range
        self.assertEqual(pr('daily', date(2026, 9, 25)), (date(2026, 9, 25), date(2026, 9, 25)))
        self.assertEqual(pr('weekly', date(2026, 9, 25)), (date(2026, 9, 21), date(2026, 9, 27)))  # Mon-Sun
        self.assertEqual(pr('weekly', date(2026, 9, 21)), (date(2026, 9, 21), date(2026, 9, 27)))
        self.assertEqual(pr('weekly', date(2026, 9, 27)), (date(2026, 9, 21), date(2026, 9, 27)))
        self.assertEqual(pr('weekly', date(2027, 1, 1)), (date(2026, 12, 28), date(2027, 1, 3)))
        self.assertEqual(pr('monthly', date(2028, 2, 10)), (date(2028, 2, 1), date(2028, 2, 29)))
        self.assertEqual(pr('monthly', date(2026, 12, 31)), (date(2026, 12, 1), date(2026, 12, 31)))

    def test_shift_anchor(self):
        sa = notes.shift_anchor
        self.assertEqual(sa('daily', date(2026, 12, 31), 1), date(2027, 1, 1))
        self.assertEqual(sa('weekly', date(2026, 9, 25), -1), date(2026, 9, 18))
        self.assertEqual(sa('monthly', date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(sa('monthly', date(2028, 1, 31), 1), date(2028, 2, 29))
        self.assertEqual(sa('monthly', date(2026, 1, 15), -1), date(2025, 12, 15))
        self.assertEqual(sa('monthly', date(2026, 12, 15), 1), date(2027, 1, 15))
        self.assertEqual(sa('monthly', date(2026, 3, 15), -27), date(2023, 12, 15))

    def test_safe_filename(self):
        used = set()
        self.assertEqual(notes.safe_filename('Plan', used), 'Plan.txt')
        self.assertEqual(notes.safe_filename('plan', used), 'plan (2).txt')      # case-insensitive clash
        self.assertEqual(notes.safe_filename('Plan', used), 'Plan (3).txt')
        self.assertEqual(notes.safe_filename('a/b:c*?', used), 'a_b_c__.txt')
        self.assertEqual(notes.safe_filename('', used), 'note.txt')
        self.assertEqual(notes.safe_filename(None, used), 'note (2).txt')
        self.assertEqual(notes.safe_filename('CON', used), '_CON.txt')
        self.assertEqual(notes.safe_filename('trailing. ', used), 'trailing.txt')


class EngineTests(unittest.TestCase):
    NOTE = (
        "******PROJECT A******\n"
        "--- 22.09.2026 ---\n"
        "1.5h ABC-1 fix login\n"
        "0,25h ABC 2 review\n"
        "some text line\n"
        "0.75h XYZ-7\n"
        "--- 23.09.2026 --- [9h]\n"
        "2h ABC-1 fix login\n"
        "2h ABC-1 tests\n"
        "******PROJECT B******\n"
        "--- 22.09.2026 ---\n"
        "1h INT meeting\n"
    )

    def test_parse_entries_formats_and_sections(self):
        entries, warnings = E.parse_entries(self.NOTE)
        self.assertEqual(warnings, [])
        got = [(e['date'].day, e['section'], e['prefix'], e['ticket'], e['hours'], e['description']) for e in entries]
        self.assertEqual(got, [
            (22, 'PROJECT A', 'ABC', 'ABC-1', 1.5, 'fix login'),
            (22, 'PROJECT A', 'ABC', 'ABC-2', 0.25, 'review'),
            (22, 'PROJECT A', 'XYZ', 'XYZ-7', 0.75, ''),
            (23, 'PROJECT A', 'ABC', 'ABC-1', 2.0, 'fix login'),
            (23, 'PROJECT A', 'ABC', 'ABC-1', 2.0, 'tests'),
            (22, 'PROJECT B', 'INT', 'meeting', 1.0, ''),   # "PREFIX word": the word becomes the ticket (V21 rule)
        ])

    def test_warnings(self):
        text = "1h ABC-1 before any date\n--- 31.02.2026 ---\n--- 01.03.2026 ---\n1.5 ABC-1 no h\n7 apples\n2h ABC-2 ok"
        entries, warnings = E.parse_entries(text)
        self.assertEqual([w[:2] for w in warnings], [('undated', 1), ('bad_date', 2), ('unparseable', 4), ('unparseable', 5)])
        self.assertEqual(len(entries), 1)
        report = E.render_report('x', entries, {}, S_DE, False, warnings=warnings)
        self.assertIn('Zeile 2: ungültige Datumszeile  "--- 31.02.2026 ---"', report)

    def test_totals_per_section_and_format(self):
        out = E.inject_totals(self.NOTE)
        lines = out.split('\n')
        self.assertEqual(lines[1], '--- 22.09.2026 --- [2.5h]')     # was "[2.50h]" in V21
        self.assertEqual(lines[6], '--- 23.09.2026 --- [4h]')       # stale [9h] replaced
        self.assertEqual(lines[10], '--- 22.09.2026 --- [1h]')      # own section only
        self.assertEqual(E.inject_totals(out), out)                 # idempotent
        self.assertEqual(E.totals_updates(out), [])
        self.assertEqual(E.strip_totals(out), E.strip_totals(self.NOTE))
        quarter = E.inject_totals("--- 01.01.2026 ---\n0.25h A-1\n")
        self.assertEqual(quarter, "--- 01.01.2026 --- [0.25h]\n0.25h A-1\n")

    def test_totals_keep_indent_and_trailing_newline(self):
        out = E.inject_totals("  --- 01.01.2026 ---   \n1h A-1\n")
        self.assertEqual(out, "  --- 01.01.2026 --- [1h]\n1h A-1\n")

    def test_report_quarter_hours_add_up(self):
        entries, _ = E.parse_entries("--- 22.09.2026 ---\n0.25h ABC-1 a\n0.25h ABC-1 b\n0.75h ABC-2\n1.25h XYZ-1\n")
        report = E.render_report('label', entries, {'ABC': 'Acme'}, S_EN, False)
        row = lambda left, hours, desc='': f"  {left:<18} {hours + 'h':>7}   {desc}".rstrip()
        self.assertIn(row('ABC-1', '0.5', 'a / b'), report)
        self.assertIn(row('ABC-2', '0.75') + '\n', report)
        self.assertIn(row('Client total:', '1.25'), report)
        self.assertIn(row('XYZ-1', '1.25'), report)
        self.assertIn('Unknown (XYZ)', report)
        self.assertIn(f"  {'TOTAL LOGGED:':<18} {'2.5h':>7}", report)
        self.assertNotIn('0.2h', report)
        self.assertNotIn('0.8h', report)

    def test_report_per_day_and_sections(self):
        entries, _ = E.parse_entries(self.NOTE)
        report = E.render_report('KW 39', entries, {}, S_DE, True, per_day=True)
        self.assertIn(f"Pro Tag\n  Di 22.09.2026  {'3.5h':>7}\n  Mi 23.09.2026  {'4h':>7}\n", report)
        self.assertIn('****** PROJECT A ******', report)
        self.assertIn('****** PROJECT B ******', report)
        self.assertIn(f"  {'GESAMT ERFASST:':<18} {'7.5h':>7}", report)

    def test_csv_rows(self):
        entries, _ = E.parse_entries(self.NOTE)
        rows = E.csv_rows(entries, {'ABC': 'Acme'})
        self.assertIn((date(2026, 9, 22), 'PROJECT A', 'Acme', 'ABC', 'ABC-1', 1.5, 'fix login'), rows)
        self.assertIn((date(2026, 9, 23), 'PROJECT A', 'Acme', 'ABC', 'ABC-1', 4.0, 'fix login / tests'), rows)
        self.assertEqual(sum(r[5] for r in rows), 7.5)
        self.assertEqual([r[0] for r in rows], sorted(r[0] for r in rows))

    def test_clients(self):
        m = E.parse_clients("# comment\nACME = Acme Corp\n int = Internal \nbad line\n")
        self.assertEqual(m, {'ACME': 'Acme Corp', 'INT': 'Internal'})

    def test_clients_default_holds_only_placeholder_examples(self):
        for lang in ('EN', 'DE'):
            text = notes.STR_TABLE[lang]['clients_default']
            self.assertEqual(E.parse_clients(text), {})          # every line is a comment
            examples = [line[2:] for line in text.splitlines() if re.match(r'# [A-Z]+ = ', line)]
            self.assertEqual([e.split(' = ')[0] for e in examples], ['ACME', 'INT'])

    def test_string_tables_match(self):
        self.assertEqual(set(S_EN), set(S_DE))
        for key in S_EN:
            self.assertEqual(type(S_EN[key]), type(S_DE[key]), key)
            if isinstance(S_EN[key], list):
                self.assertEqual(len(S_EN[key]), len(S_DE[key]), key)
            if isinstance(S_EN[key], str):
                self.assertEqual(S_EN[key].count('{'), S_DE[key].count('{'), key)


class ArchiveSelectionTests(unittest.TestCase):
    def _e(self, d, h, ticket='A-1'):
        return {'date': d, 'section': '', 'prefix': ticket.split('-')[0], 'ticket': ticket, 'hours': h, 'description': ''}

    def test_json_roundtrip(self):
        entries = [self._e(date(2026, 9, 1), 1.5), {**self._e(date(2026, 9, 1), 0.25), 'description': 'Ü "q"', 'section': 'S'}]
        js = notes.entries_to_json(entries)
        self.assertEqual(notes.entries_from_json(date(2026, 9, 1), js), entries)
        self.assertIsNone(notes.entries_from_json(date(2026, 9, 1), None))
        self.assertIsNone(notes.entries_from_json(date(2026, 9, 1), '{broken'))

    def test_snapshot_updates_only_changed_days(self):
        d1, d2 = date(2026, 9, 1), date(2026, 9, 2)
        entries = [self._e(d1, 1), self._e(d2, 2)]
        known = {d1: notes.entries_to_json([self._e(d1, 1)]), d2: None}
        self.assertEqual([u[0] for u in notes.snapshot_updates(entries, known)], [d2])
        entries[0]['hours'] = 1.25                      # correction on a past day
        self.assertEqual([u[0] for u in notes.snapshot_updates(entries, known)], [d1, d2])

    def test_moved_away_days(self):
        parse = lambda text: E.parse_entries(text)[0]
        before = parse("--- 01.09.2026 ---\n1h INT standup\n2h ABC-1 work\n--- 02.09.2026 ---\n1h INT standup\n")
        # corrected date marker of the first day: moved
        moved = parse("--- 03.09.2026 ---\n1h INT standup\n2h ABC-1 work\n--- 02.09.2026 ---\n1h INT standup\n")
        self.assertEqual(notes.moved_away_days(before, moved), [date(2026, 9, 1)])
        # pruning the first day, even though its standup line also exists elsewhere: not moved
        pruned = parse("--- 02.09.2026 ---\n1h INT standup\n")
        self.assertEqual(notes.moved_away_days(before, pruned), [])
        # pruning while typing a new, identical standup on another day: work entry vanished, not moved
        pruned_and_typed = parse("--- 02.09.2026 ---\n1h INT standup\n--- 04.09.2026 ---\n1h INT standup\n")
        self.assertEqual(notes.moved_away_days(before, pruned_and_typed), [])
        self.assertEqual(notes.moved_away_days(None, moved), [])

    def test_select_note_truth_and_pruned_days(self):
        d = lambda day: date(2026, 9, day)
        live = [self._e(d(10), 1), self._e(d(12), 2)]                 # note starts on the 10th
        archive = {
            d(3): ('t3', [self._e(d(3), 5)]),                          # pruned from the note
            d(4): ('t4', None),                                        # pre-JSON row
            d(11): ('t11', [self._e(d(11), 7)]),                       # stale: moved away, note is truth
            d(12): ('t12', [self._e(d(12), 9)]),                       # stale copy of a live day
        }
        entries, archived, legacy = notes.select_period_entries(live, archive, d(1), d(30))
        self.assertEqual(sum(e['hours'] for e in entries), 5 + 1 + 2)
        self.assertEqual(archived, [d(3)])
        self.assertEqual(legacy, [d(4)])
        entries, archived, legacy = notes.select_period_entries([], archive, d(1), d(30))
        self.assertEqual(sum(e['hours'] for e in entries), 5 + 7 + 9)   # empty note: all from archive
        entries, _, _ = notes.select_period_entries(live, archive, d(12), d(12))
        self.assertEqual([e['hours'] for e in entries], [2])


@unittest.skipUnless(HAVE_V21, "needs the git history (V21 source)")
class V21EquivalenceTests(unittest.TestCase):
    """Randomized notes: the new engine must parse exactly like V21 and total like V21 (modulo the fixed format)."""

    @classmethod
    def setUpClass(cls):
        cls.old = load_old_module(new_dir())
        cls.old_engine = cls.old.TimetrackingEngine()

    @staticmethod
    def random_note(rnd):
        lines = []
        for _ in range(rnd.randint(0, 40)):
            kind = rnd.random()
            if kind < 0.12:
                lines.append(f"{' ' * rnd.randint(0, 2)}--- {rnd.randint(1, 31):02d}.{rnd.randint(1, 12):02d}.2026 ---"
                             + rnd.choice(['', ' [3h]', ' [1.50h]', '  ']))
            elif kind < 0.17:
                lines.append(rnd.choice(['******', '******PROJECT A******', '******PROJECT B******']))
            elif kind < 0.7:
                h = rnd.choice(['1', '0.25', '0,5', '1.5', '2', '0.75', '10', '1.1'])
                ticket = rnd.choice(['ABC-1', 'ABC 12', 'XYZ-7', 'INT', 'INT meeting', 'abc-3'])
                desc = rnd.choice(['', ' fix', ' review code', ' ümlaut'])
                lines.append(f"{h}{rnd.choice(['h', 'H'])} {ticket}{desc}")
            elif kind < 0.8:
                lines.append(rnd.choice(['1.5 ABC-1', '7 apples', '3']))
            else:
                lines.append(rnd.choice(['', 'plain text', '# heading', '- list']))
        return '\n'.join(lines) + rnd.choice(['', '\n'])

    def test_parse_matches_v21(self):
        rnd = random.Random(42)
        code = {'invalid date marker': 'bad_date', 'unparseable (no ticket)': 'no_ticket',
                'unparseable': 'unparseable', 'undated entry': 'undated'}
        for _ in range(500):
            text = self.random_note(rnd)
            old_entries, old_warn = self.old_engine.parse_entries(text, {})
            new_entries, new_warn = E.parse_entries(text)
            self.assertEqual(new_entries, old_entries, text)
            old_codes = []
            for w in old_warn:
                m = re.match(r'Line (\d+): (invalid date marker|unparseable \(no ticket\)|unparseable|undated entry)', w)
                old_codes.append((code[m.group(2)], int(m.group(1))))
            self.assertEqual([w[:2] for w in new_warn], old_codes, text)

    def test_totals_match_v21(self):
        rnd = random.Random(7)
        for _ in range(500):
            text = self.random_note(rnd)
            old = self.old_engine.inject_totals(text)
            # V21 printed fractional totals as "x.y0h"; the new format drops the trailing zero
            old = re.sub(r'\[(\d+\.\d)0h\]', r'[\1h]', old)
            new = E.inject_totals(text)
            if text.endswith('\n\n'):
                # V21 bug: splitlines() dropped one trailing blank line on every refresh
                self.assertEqual(len(new) - len(new.rstrip('\n')), len(text) - len(text.rstrip('\n')))
                new, old = new.rstrip('\n'), old.rstrip('\n')
            self.assertEqual(new, old, text)

    def test_aggregate_matches_v21(self):
        rnd = random.Random(3)
        for _ in range(200):
            entries, _ = E.parse_entries(self.random_note(rnd))
            old = self.old_engine.aggregate_by_section(entries, {})
            new = E.aggregate(entries, by_section=True)
            self.assertEqual(list(new), list(old))
            for sec in new:
                self.assertEqual({p: t for p, t in new[sec].items()}, {p: v['tickets'] for p, v in old[sec].items()})


if __name__ == '__main__':
    unittest.main()
