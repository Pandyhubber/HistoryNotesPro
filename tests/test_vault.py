"""Database layer, schema migration from V21, and running V21 again on a migrated database."""
import sqlite3
import unittest
from datetime import date, timedelta

from support import notes, new_dir, load_old_module, make_app, close_app, set_editor, HAVE_V21


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.dir = new_dir()
        self.v = notes.NoteVault(self.dir / 'notes_vault.db')

    def tearDown(self):
        self.v.close()

    def q(self, sql, *params):
        self.v.flush()
        return self.v._rconn.execute(sql, params).fetchall()

    def test_fresh_schema(self):
        self.assertEqual(self.q("SELECT MAX(version) FROM schema_version")[0][0], 2)
        cols = [r[1] for r in self.q("PRAGMA table_info(summary_history)")]
        self.assertEqual(cols, ['date', 'content', 'created_at', 'entries_json'])
        self.assertIn('idx_history_note', [r[0] for r in self.q("SELECT name FROM sqlite_master WHERE type='index'")])
        self.assertEqual(self.q("SELECT title FROM note_list"), [('Welcome!',)])
        self.assertEqual(self.q("PRAGMA journal_mode")[0][0], 'wal')

    def test_create_note_ids(self):
        a = self.v.create_note("A", "x")
        b = self.v.create_note("B")
        self.assertEqual(b, a + 1)
        self.assertEqual(self.v.get_note(b), ('B', '', 0))

    def test_write_error_raises_and_writer_survives(self):
        with self.assertLogs(notes.log, 'ERROR') as logs:
            with self.assertRaises(sqlite3.OperationalError):
                self.v._write_sync([("INSERT INTO missing_table VALUES (?)", ("SECRET NOTE TEXT",))])
        self.assertNotIn("SECRET NOTE TEXT", '\n'.join(logs.output))   # content stays out of the log
        self.assertIsNotNone(self.v.create_note("after error"))

    def test_failed_batch_is_atomic(self):
        nid = self.v.create_note("T", "before")
        with self.assertRaises(sqlite3.OperationalError):
            self.v._write_sync([("UPDATE note_list SET last_content = 'after' WHERE id = ?", (nid,)),
                                ("INSERT INTO missing_table VALUES (1)", ())])
        self.assertEqual(self.v.get_note(nid)[1], "before")

    def test_many_async_writes_then_flush(self):
        nid = self.v.create_note("T")
        for i in range(500):
            self.v.save_note(nid, "T", f"content {i}", add_history=(i % 10 == 0))
        self.v.flush()
        self.assertEqual(self.v.get_note(nid)[1], "content 499")
        self.assertEqual(self.v.get_history_count(nid), 50)
        self.assertEqual(self.v.get_last_history_content(nid), "content 490")

    def test_search_is_unicode_case_insensitive_and_literal(self):
        ids = {
            'aerger': self.v.create_note("Ärger im Büro", "x"),
            'strasse': self.v.create_note("Hauptstraße 5", "x"),
            'oel': self.v.create_note("Einkauf", "ÖL und Brot"),
            'pct': self.v.create_note("Rabatt", "50% off"),
            'plain': self.v.create_note("abc_def", "x"),
        }
        hits = lambda term: {r[0] for r in self.v.fetch_sidebar_notes(term, False)}
        self.assertEqual(hits("ärger"), {ids['aerger']})
        self.assertEqual(hits("ÄRGER"), {ids['aerger']})
        self.assertEqual(hits("STRASSE"), {ids['strasse']})      # ß casefolds to ss
        self.assertEqual(hits("öl"), {ids['oel']})               # found in the content
        self.assertEqual(hits("%"), {ids['pct']})                # literal, no LIKE wildcard
        self.assertEqual(hits("c_d"), {ids['plain']})
        self.assertEqual(hits("x_y"), set())
        self.assertEqual(len(hits("")), 6)

    def test_hard_delete_removes_history_too(self):
        nid = self.v.create_note("T")
        self.v.save_note(nid, "T", "v1", add_history=True)
        self.v.delete_note_hard(nid)
        self.assertIsNone(self.v.get_note(nid))
        self.assertEqual(self.q("SELECT COUNT(*) FROM history WHERE note_id = ?", nid)[0][0], 0)

    def test_soft_delete_restore_pin(self):
        nid = self.v.create_note("T")
        self.v.toggle_pin(nid)
        self.assertEqual(self.v.fetch_sidebar_notes('', False)[0][:3], (nid, 'T', 1))
        self.v.delete_note_soft(nid)          # archiving unpins
        self.assertEqual(self.v.fetch_sidebar_notes('', True), [(nid, 'T', 0, 1)])
        self.v.restore_note(nid)
        self.assertIn(nid, [r[0] for r in self.v.fetch_sidebar_notes('', False)])

    def test_summary_rows(self):
        self.v.save_summary_snapshots([("01/09/2026", "text", "[]"), ("02/09/2026", "t2", None)])
        self.v.save_summary_snapshots([("01/09/2026", "text v2", '[["","A","A-1",1.0,""]]')])
        self.v.flush()
        rows = sorted(self.v.get_summary_rows())
        self.assertEqual(rows, [("01/09/2026", "text v2", '[["","A","A-1",1.0,""]]'), ("02/09/2026", "t2", None)])


@unittest.skipUnless(HAVE_V21, "needs the git history (V21 source)")
class MigrationTests(unittest.TestCase):
    """A database written by V21 opens in the new build, and V21 still runs on it afterwards."""

    def build_v21_db(self, folder):
        old = load_old_module(folder)
        ov = old.NoteVault(folder / 'notes_vault.db')
        ids = {'alpha': ov.create_note("Alpha", "alpha v1")}
        ov.save_snapshot(ids['alpha'], "Alpha", "alpha v1", force_history=True)
        ov.save_snapshot(ids['alpha'], "Alpha", "alpha v2 longer", force_history=True)
        today = date.today()
        tt_text = (f"--- {today - timedelta(days=1):%d.%m.%Y} --- [2h]\n2h ABC-1 yesterday\n"
                   f"--- {today:%d.%m.%Y} --- [1.50h]\n1.5h ABC-2 today\n")
        ids['tt'] = ov.create_note("Timetracking", tt_text)
        ids['clients'] = ov.create_note("Timetracking Clients", "ABC = Acme")
        ids['archived_tt'] = ov.create_note("Timetracking", "an archived older TT note")
        ov.delete_note_soft(ids['archived_tt'])
        ids['dup_tt'] = ov.create_note("Timetracking", "imported duplicate")
        ov.save_summary_snapshot("01/01/2026", "LEGACY TEXT JANUARY")
        ov._write_sync("SELECT 1")
        ov.close()
        return old, ids, tt_text

    def test_upgrade_then_downgrade_then_upgrade(self):
        folder = new_dir()
        old, ids, tt_text = self.build_v21_db(folder)
        db = folder / 'notes_vault.db'

        # 1) new vault migrates additively, data untouched
        nv = notes.NoteVault(db)
        nv.flush()
        self.assertEqual(nv._rconn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0], 2)
        self.assertEqual(nv.get_note(ids['alpha'])[1], "alpha v2 longer")
        self.assertEqual(nv.get_history_count(ids['alpha']), 2)
        self.assertEqual(nv.get_summary_rows(), [("01/01/2026", "LEGACY TEXT JANUARY", None)])
        nv.close()

        # 2) new app adopts the lowest active "Timetracking" note, like V21's LIMIT 1 did
        app = make_app(folder)
        self.assertEqual(app._tt_id, ids['tt'])
        self.assertEqual(app._clients_id, ids['clients'])
        titles = [t for _, t, *_ in app.vault.fetch_sidebar_notes('', False)]
        self.assertEqual(titles.count("Timetracking"), 2)            # nothing new created
        app.load_note(ids['tt'])
        app.force_save()                                             # syncs the per-day archive
        app.vault.flush()
        rows = {d: js for d, _, js in app.vault.get_summary_rows()}
        self.assertIsNone(rows["01/01/2026"])                        # legacy row kept as is
        self.assertEqual(len([js for js in rows.values() if js]), 2)  # both note days now structured
        close_app(app)

        # 3) V21 still starts, reads and writes the migrated database
        old_app = old.HistoryNotesApp()
        old_app.withdraw()
        old_app.update()
        self.assertEqual(old_app.vault.get_note_by_title("Timetracking")[0], ids['tt'])
        old_app.load_note(ids['tt'])
        old_app.editor.insert("end-1c", "0.5h ABC-3 written by V21\n")
        old_app._last_tt_content_hash = ""
        old_app.force_save()
        old_app._snapshot_current_summary()
        old_app.open_summary_history()
        old_app.update()
        old_app._on_app_close()

        # 4) back on the new build: V21's rows (entries_json NULL) get structured again
        app = make_app(folder)
        self.assertEqual(app._tt_id, ids['tt'])
        app.load_note(ids['tt'])
        self.assertIn("written by V21", app._editor_text())
        set_editor(app, app._editor_text() + "0.25h ABC-4 back on new\n")
        app.auto_save()
        app.vault.flush()
        rows = {d: js for d, _, js in app.vault.get_summary_rows()}
        today_key = date.today().strftime('%d/%m/%Y')
        today_entries = notes.entries_from_json(date.today(), rows[today_key])
        self.assertEqual(sorted(e['ticket'] for e in today_entries), ['ABC-2', 'ABC-3', 'ABC-4'])
        close_app(app)


if __name__ == '__main__':
    unittest.main()
