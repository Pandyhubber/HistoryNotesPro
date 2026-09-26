"""The real app with a real Tk event loop, driven through its handlers. One temp folder per test."""
import csv
import shutil
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from support import (notes, new_dir, make_app, close_app, pump, type_text, set_editor, db_note,
                     note_id_by_title, Ev, REPO)

TODAY = date.today()


def d(day: date) -> str:
    return f"{day:%d.%m.%Y}"


class GuiCase(unittest.TestCase):
    def setUp(self):
        self.dir = new_dir()
        self.app = make_app(self.dir)
        self.tb = self.app.editor._textbox

    def tearDown(self):
        if self.app is not None:
            try:
                close_app(self.app)
            except Exception:
                pass

    def reopen(self):
        close_app(self.app)
        self.app = make_app(self.dir)
        self.tb = self.app.editor._textbox

    def new_note(self, title, content=""):
        nid = self.app.vault.create_note(title, content)
        self.app.refresh_sidebar()
        return nid

    def text(self):
        return self.app._editor_text()


class StartupTests(GuiCase):
    def test_fresh_start_and_restart(self):
        titles = sorted(t for _, t, *_ in self.app.vault.fetch_sidebar_notes('', False))
        self.assertEqual(titles, ["Timetracking", "Timetracking Clients", "Welcome!"])
        self.assertEqual(self.app.vault.get_setting('tt_note_id', ''), str(self.app._tt_id))
        clients = db_note(self.app, self.app._clients_id)[1]
        self.assertIn("ACME = Acme Corp", clients)
        self.assertEqual(self.app.current_note_id, self.app._clients_id)   # newest active note is loaded
        tt, cl = self.app._tt_id, self.app._clients_id
        self.reopen()
        self.assertEqual((self.app._tt_id, self.app._clients_id), (tt, cl))
        self.assertEqual(len(self.app.vault.fetch_sidebar_notes('', False)), 3)

    def test_resource_path_prefers_local_then_meipass(self):
        meipass = new_dir()
        shutil.copy(REPO / 'app_icon.ico', meipass / 'app_icon.ico')
        with mock.patch.object(notes.sys, '_MEIPASS', str(meipass), create=True):
            self.assertEqual(notes.resource_path('app_icon.ico'), meipass / 'app_icon.ico')
            shutil.copy(REPO / 'app_icon.ico', self.dir / 'app_icon.ico')
            self.assertEqual(notes.resource_path('app_icon.ico'), self.dir / 'app_icon.ico')

    def test_window_icon_set_from_bundle(self):
        meipass = new_dir()
        shutil.copy(REPO / 'app_icon.ico', meipass / 'app_icon.ico')
        close_app(self.app)
        with mock.patch.object(notes.sys, '_MEIPASS', str(meipass), create=True):
            self.app = make_app(self.dir)
        self.assertTrue(self.app._iconbitmap_method_called)

    def reopen_with_saved_geometry(self, geo):
        close_app(self.app)                        # closing saves the current geometry, so write after it
        vault = notes.NoteVault(self.dir / 'notes_vault.db')
        vault.set_setting('window_geometry', geo)
        vault.close()
        self.app = make_app(self.dir)

    def test_geometry_from_disconnected_monitor_is_not_restored(self):
        # Saved on a left-hand second monitor that is no longer there
        self.reopen_with_saved_geometry('1936x1096+-1959+37')
        self.assertFalse(self.app.geometry().endswith('+-1959+37'))

    def test_geometry_on_connected_monitor_is_restored(self):
        self.reopen_with_saved_geometry('900x600+120+80')
        self.assertTrue(self.app.geometry().endswith('+120+80'))   # withdrawn in tests, so Tk reports its own size


class SaveTests(GuiCase):
    def test_small_edits_are_saved_history_only_for_bigger_ones(self):
        self.app.create_new_note()
        nid = self.app.current_note_id
        self.app.title_entry.insert(0, "Plan")
        type_text(self.app, "Buy 1.5h of milk today")
        self.app.auto_save()
        self.assertEqual(db_note(self.app, nid)[:2], ("Plan", "Buy 1.5h of milk today"))
        self.assertEqual(self.app.vault.get_history_count(nid), 1)

        self.tb.delete("1.4", "1.5")          # 1.5h -> 2.5h: same length, one char
        self.tb.insert("1.4", "2")
        self.app.on_key_release(Ev('2'))
        self.app.auto_save()
        self.assertEqual(db_note(self.app, nid)[1], "Buy 2.5h of milk today")   # V21 skipped this save
        self.assertEqual(self.app.vault.get_history_count(nid), 1)

        type_text(self.app, " and bread", at="end-1c")
        self.app.auto_save()
        self.app.vault.flush()
        self.assertEqual(self.app.vault.get_history_count(nid), 2)
        self.assertEqual(self.app.vault.get_last_history_content(nid), "Buy 2.5h of milk today and bread")

    def test_debounced_autosave_fires(self):
        nid = self.new_note("Deb", "")
        self.app.load_note(nid)
        type_text(self.app, "x")
        pump(self.app, 1400)
        self.assertEqual(db_note(self.app, nid)[1], "x")

    def test_title_rename_shows_in_sidebar_at_once(self):
        nid = self.new_note("Old title", "body")
        self.app.load_note(nid)
        self.app.title_entry.delete(0, "end")
        self.app.title_entry.insert(0, "New title")
        self.app.auto_save()
        self.assertEqual(self.app._sidebar_cache[nid]._last_text, "New title")

    def test_close_flushes_pending_edit(self):
        nid = self.new_note("Close", "a")
        self.app.load_note(nid)
        type_text(self.app, "bc", at="end-1c")      # no auto-save yet
        self.reopen()
        self.assertEqual(db_note(self.app, nid)[1], "abc")

    def test_manual_save_and_timestamp(self):
        nid = self.new_note("TS", "")
        self.app.load_note(nid)
        self.app.insert_timestamp()
        self.assertRegex(db_note(self.app, nid)[1], r"^\n--- \d{2}\.\d{2}\.\d{4}, \d{2}:\d{2} ---\n$")
        self.app.load_note(self.app._tt_id)
        self.app.insert_timestamp()
        self.assertIn(f"--- {d(TODAY)} ---", self.text())
        self.app.manual_save()
        self.app.update()


class UndoTests(GuiCase):
    def test_undo_never_reaches_into_previous_note(self):
        a = self.new_note("A", "content of A")
        b = self.new_note("B", "content of B")
        self.app.load_note(a)
        self.app.load_note(b)
        for _ in range(3):
            self.tb.event_generate("<<Undo>>")      # what Ctrl+Z sends
        self.assertEqual(self.text(), "content of B")
        self.app.auto_save()
        self.assertEqual(db_note(self.app, b)[1], "content of B")

    def load_tt(self, content):
        self.app.vault.save_note(self.app._tt_id, "Timetracking", content)
        self.app.load_note(self.app._tt_id)

    def test_tt_undo_after_totals_refresh_is_not_empty(self):
        base = f"--- {d(TODAY)} --- [1h]\n1h ABC-1 a\n"
        self.load_tt(base)
        type_text(self.app, "0.5h ABC-2 b", at="end-1c")
        self.app._refresh_tt_totals()
        typed = base.replace("[1h]", "[1.5h]") + "0.5h ABC-2 b"
        self.assertEqual(self.text(), typed)

        self.tb.event_generate("<<Undo>>")
        self.assertEqual(self.text(), base)                  # V21: empty editor
        self.app._refresh_tt_totals()                        # consistent again: nothing to change
        self.assertEqual(self.text(), base)

        self.tb.event_generate("<<Redo>>")
        self.assertEqual(self.text(), typed)                 # totals came back with the entry
        self.tb.event_generate("<<Undo>>")
        self.assertEqual(self.text(), base)

    def test_tt_undo_steps_through_several_edits(self):
        base = f"--- {d(TODAY)} --- [0h]\n"
        self.load_tt(base)
        type_text(self.app, "1h A-1\n", at="end-1c")
        self.app._refresh_tt_totals()
        self.tb.mark_set("insert", "1.3")                    # cursor move: Tk closes the undo group
        self.tb.edit_separator()
        type_text(self.app, "2h A-2\n", at="end-1c")
        self.app._refresh_tt_totals()
        self.assertTrue(self.text().startswith(f"--- {d(TODAY)} --- [3h]"))
        self.app._undo()
        self.assertEqual(self.text(), f"--- {d(TODAY)} --- [1h]\n1h A-1\n")
        self.app._undo()
        self.assertEqual(self.text(), base)
        self.app._undo()                                     # nothing left: stays put
        self.assertEqual(self.text(), base)

    def test_totals_refresh_keeps_cursor_and_emoji_text(self):
        content = f"--- {d(TODAY)} --- 🎉 Feier\n1h A-1 🎉 cake\n\n\n"
        self.load_tt(content)
        self.tb.mark_set("insert", "1.5")
        self.app._refresh_tt_totals()
        self.assertEqual(self.text(), notes.TimetrackingEngine().inject_totals(content))
        self.assertTrue(self.text().endswith("\n\n\n"))      # V21 dropped a trailing blank line here
        self.assertEqual(self.tb.index("insert"), "1.5")

    def test_format_undo_is_one_step(self):
        nid = self.new_note("F", "hello world")
        self.app.load_note(nid)
        self.tb.tag_add("sel", "1.0", "1.5")
        self.app._apply_format("**", "**")
        self.assertEqual(self.text(), "**hello** world")
        self.app._undo()
        self.assertEqual(self.text(), "hello world")        # V21: " world" after the first undo
        self.tb.tag_add("sel", "1.6", "1.11")
        self.app._apply_color("sage_green")
        self.assertEqual(self.text(), "hello [sage_green]world[/sage_green]")
        self.tb.tag_add("sel", "1.0", "end-1c")
        self.app._remove_color()
        self.assertEqual(self.text(), "hello world")
        self.app._undo()
        self.assertEqual(self.text(), "hello [sage_green]world[/sage_green]")


class SliderTests(GuiCase):
    def make_versions(self):
        nid = self.new_note("S", "")
        self.app.load_note(nid)
        for version in ("version one", "version two is longer", "version three is the longest"):
            set_editor(self.app, version)
            self.app.auto_save()
        set_editor(self.app, "version three is the longest!")   # live, too small for a history entry
        self.app.auto_save()
        return nid

    def test_viewing_old_version_and_moving_keys_does_not_save(self):
        nid = self.make_versions()
        self.app._on_slider_move(0)
        self.assertEqual(self.text(), "version one")
        self.app.on_key_release(Ev('Left'))
        self.app.auto_save()
        self.assertEqual(db_note(self.app, nid)[1], "version three is the longest!")
        self.app._on_slider_move(99)                            # back to Live
        self.assertEqual(self.text(), "version three is the longest!")
        self.assertFalse(self.app._viewing_history)

    def test_typing_in_old_version_restores_and_keeps_live_in_history(self):
        nid = self.make_versions()
        self.app._on_slider_move(1)
        type_text(self.app, " (restored)", at="end-1c")
        self.app.auto_save()
        self.assertEqual(db_note(self.app, nid)[1], "version two is longer (restored)")
        history = [c for _, c in self.app.vault.get_history(nid)]
        self.assertIn("version three is the longest!", history)  # the replaced live text is kept
        self.assertEqual(self.app.version_info.cget("text"), "Live")

    def test_switching_away_from_old_version_restores_like_v21(self):
        nid = self.make_versions()
        other = self.new_note("Other", "x")
        self.app._on_slider_move(0)
        self.app.load_note(other)
        self.assertEqual(db_note(self.app, nid)[1], "version one")
        history = [c for _, c in self.app.vault.get_history(nid)]
        self.assertEqual(history[-1], "version three is the longest!")
        self.app.load_note(nid)
        self.assertEqual(self.text(), "version one")
        self.app._on_slider_move(len(history) - 1)
        self.assertEqual(self.text(), "version three is the longest!")


class SidebarTests(GuiCase):
    def test_search_umlaut(self):
        nid = self.new_note("Ärger mit dem Drucker", "x")
        self.app.search_bar.insert(0, "ärger")
        self.app._on_search_key(None)
        self.assertEqual(self.app._sidebar_order, [nid])
        self.app.search_bar.delete(0, "end")
        self.app._on_search_key(None)
        self.assertEqual(len(self.app._sidebar_order), 4)

    def test_archive_restore_hard_delete(self):
        nid = self.new_note("Doomed", "text")
        self.app.load_note(nid)
        set_editor(self.app, "text edited")
        self.app.auto_save()
        self.app.handle_delete_action()
        self.assertNotIn(nid, self.app._sidebar_order)
        self.app.toggle_archive_view()
        self.assertIn(nid, self.app._sidebar_order)
        self.assertEqual(self.app.archive_toggle_btn.cget("fg_color"), notes.CLR_ARCHIVE_ACTIVE)
        self.assertEqual(self.app.del_btn.cget("text"), "Delete Permanently")
        self.app.restore_note()
        self.assertFalse(self.app.show_archived)
        self.assertEqual(self.app.archive_toggle_btn.cget("fg_color"), notes.CLR_ARCHIVE_IDLE)  # V21 left it lit
        self.assertIn(nid, self.app._sidebar_order)
        self.app.handle_delete_action()
        with mock.patch.object(notes.messagebox, 'askyesno', return_value=True):
            self.app.handle_delete_action()
        self.assertIsNone(db_note(self.app, nid))
        self.assertEqual(self.app.vault.get_history_count(nid), 0)
        self.assertIsNone(self.app.current_note_id)
        self.assertEqual(self.text(), "")

    def test_pin_moves_to_top(self):
        nid = self.new_note("Pin me", "x")
        self.app.toggle_pin(self.app._tt_id)
        self.assertEqual(self.app._sidebar_order[0], self.app._tt_id)
        self.app.toggle_pin(nid)
        self.assertEqual(set(self.app._sidebar_order[:2]), {nid, self.app._tt_id})
        self.assertEqual(self.app._sidebar_pinned_count, 2)

    def test_language_toggle_everywhere(self):
        self.app.toggle_language()
        self.assertEqual(self.app.new_btn.cget("text"), "+ Neue Notiz")
        self.assertEqual(self.app.menubar.entrycget(self.app._menu_file_idx, "label"), "Datei")
        self.assertEqual(self.app.menubar.entrycget(self.app._menu_help_idx, "label"), "Hilfe")
        self.assertEqual(self.app.help_menu.entrycget(0, "label"), "── Tastenkürzel ──")
        self.assertEqual(self.app.file_menu.entrycget(0, "label"), "Export (.zip)")
        self.reopen()
        self.assertEqual(self.app.lang, "DE")
        self.assertEqual(self.app.tt_history_btn.cget("text"), "📊 Verlauf")


class ExportImportTests(GuiCase):
    def test_export_unique_safe_names_and_reimport(self):
        self.new_note("Plan", "one")
        self.new_note("plan", "two")
        self.new_note("a/b: c?", "three")
        zpath = self.dir / "export.zip"
        with mock.patch.object(notes.filedialog, 'asksaveasfilename', return_value=str(zpath)):
            self.app.export_notes()
        with zipfile.ZipFile(zpath) as z:
            names = sorted(z.namelist())
            self.assertIn("a_b_ c_.txt", names)
            self.assertIn("Plan.txt", names)
            self.assertIn("plan (2).txt", names)
            self.assertIn("Timetracking.txt", names)
            self.assertEqual(len(names), len(set(n.casefold() for n in names)))

        tt = self.app._tt_id
        with mock.patch.object(notes.filedialog, 'askopenfilename', return_value=str(zpath)):
            self.app.import_notes()
        titles = [t for _, t, *_ in self.app.vault.fetch_sidebar_notes('', False)]
        self.assertEqual(titles.count("Timetracking"), 2)
        self.assertEqual(self.app._tt_id, tt)            # the imported copy is just a note
        self.reopen()
        self.assertEqual(self.app._tt_id, tt)

    def test_import_zip_with_folders_bom_and_upper_case(self):
        zpath = self.dir / "in.zip"
        with zipfile.ZipFile(zpath, 'w') as z:
            z.writestr("sub/", "")
            z.writestr("sub/Deep Note.TXT", "﻿Ümlaut body".encode('utf-8'))
            z.writestr("readme.md", "skip")
        with mock.patch.object(notes.filedialog, 'askopenfilename', return_value=str(zpath)):
            self.app.import_notes()
        nid = note_id_by_title(self.app, "Deep Note")
        self.assertEqual(db_note(self.app, nid)[1], "Ümlaut body")
        self.assertIsNone(note_id_by_title(self.app, "readme"))

    def test_import_single_txt(self):
        p = self.dir / "Single.txt"
        p.write_text("single body", encoding='utf-8')
        with mock.patch.object(notes.filedialog, 'askopenfilename', return_value=str(p)):
            self.app.import_notes()
        self.assertEqual(db_note(self.app, note_id_by_title(self.app, "Single"))[1], "single body")


class TimetrackingTests(GuiCase):
    def put_tt(self, content, clients="ABC = Acme\nXYZ = Xylo\n"):
        self.app.load_note(self.app._clients_id)
        set_editor(self.app, clients)
        self.app.auto_save()
        self.app.load_note(self.app._tt_id)
        set_editor(self.app, content)
        self.app.auto_save()
        self.app.vault.flush()

    def archive(self):
        self.app.vault.flush()
        return {k: notes.entries_from_json(notes.datetime.strptime(k, '%d/%m/%Y').date(), js)
                for k, _, js in self.app.vault.get_summary_rows()}

    def test_bound_by_id_through_rename_and_archive(self):
        tt = self.app._tt_id
        self.app.load_note(tt)
        self.assertEqual(self.app.tt_history_btn.winfo_manager(), 'pack')
        self.app.title_entry.delete(0, "end")
        self.app.title_entry.insert(0, "Zeiten")
        self.app.auto_save()
        self.app.handle_delete_action()                 # archive it
        self.reopen()
        self.assertEqual(self.app._tt_id, tt)
        self.assertIsNone(note_id_by_title(self.app, "Timetracking"))   # V21 would have created a new one
        self.app.load_note(tt)
        self.assertEqual(self.app.tt_history_btn.winfo_manager(), 'pack')
        other = self.new_note("Normal", "")
        self.app.load_note(other)
        self.assertEqual(self.app.tt_history_btn.winfo_manager(), '')

    def test_archive_follows_saved_text_and_past_corrections(self):
        d1, d2 = TODAY - timedelta(days=10), TODAY - timedelta(days=3)
        content = f"--- {d(d1)} ---\n1h ABC-1 old\n--- {d(d2)} ---\n2h ABC-2 mid\n--- {d(TODAY)} ---\n3h XYZ-1 now\n"
        self.put_tt(content)
        arch = self.archive()
        self.assertEqual({k: sum(e['hours'] for e in v) for k, v in arch.items()},
                         {d1.strftime('%d/%m/%Y'): 1, d2.strftime('%d/%m/%Y'): 2, TODAY.strftime('%d/%m/%Y'): 3})
        # correct a past day by one character: saved and re-archived (V21: neither)
        set_editor(self.app, self.text().replace("1h ABC-1 old", "4h ABC-1 old"))
        self.app.auto_save()
        self.assertEqual(sum(e['hours'] for e in self.archive()[d1.strftime('%d/%m/%Y')]), 4)

    def test_report_note_truth_pruning_and_moves(self):
        d1, d2 = TODAY - timedelta(days=10), TODAY - timedelta(days=3)
        self.put_tt(f"--- {d(d1)} ---\n1h ABC-1 old\n--- {d(d2)} ---\n2h ABC-2 mid\n--- {d(TODAY)} ---\n3h XYZ-1 now\n")
        span = (d1 - timedelta(days=1), TODAY)
        total = lambda: sum(r[5] for r in self.app._tt_period_report('weekly', *span)[1])
        self.assertEqual(total(), 6)
        # prune the oldest day from the note: still counted from the archive
        set_editor(self.app, f"--- {d(d2)} ---\n2h ABC-2 mid\n--- {d(TODAY)} ---\n3h XYZ-1 now\n")
        self.app.auto_save()
        text, rows = self.app._tt_period_report('weekly', *span)
        self.assertEqual(sum(r[5] for r in rows), 6)
        self.assertIn(f"From archive (no longer in the note): {d(d1)}", text)
        # correct the date of the note's first day: no double count, old day empty
        moved = d2 + timedelta(days=1)
        set_editor(self.app, f"--- {d(moved)} ---\n2h ABC-2 mid\n--- {d(TODAY)} ---\n3h XYZ-1 now\n")
        self.app.auto_save()
        self.assertEqual(total(), 6)
        self.assertEqual(self.app._tt_period_report('daily', d2, d2)[0], notes.STR_TABLE['EN']['no_history'])
        self.assertNotIn(d(d2), self.app._tt_period_report('weekly', *span)[0].split("From archive")[-1])
        # the same holds after a restart (previous state comes from the loaded note)
        self.reopen()
        self.app.load_note(self.app._tt_id)
        set_editor(self.app, f"--- {d(moved + timedelta(days=1))} ---\n2h ABC-2 mid\n--- {d(TODAY)} ---\n3h XYZ-1 now\n")
        self.app.auto_save()
        self.assertEqual(sum(r[5] for r in self.app._tt_period_report('weekly', *span)[1]), 6)

    def test_legacy_text_rows(self):
        old_day = TODAY - timedelta(days=40)
        self.app.vault.save_summary_snapshots([(old_day.strftime('%d/%m/%Y'), "OLD STORED SUMMARY", None)])
        self.put_tt(f"--- {d(TODAY)} ---\n1h ABC-1 now\n")
        self.assertEqual(self.app._tt_period_report('daily', old_day, old_day)[0], "OLD STORED SUMMARY")
        text, rows = self.app._tt_period_report('monthly', old_day, TODAY)
        self.assertIn(f"Text-only archive, not in the totals: {d(old_day)}", text)
        self.assertEqual(sum(r[5] for r in rows), 1)

    def test_history_window_modes_navigation_copy_csv(self):
        monday = TODAY - timedelta(days=TODAY.weekday())
        last_week = monday - timedelta(days=7)
        self.put_tt(
            "******PROJECT A******\n"
            f"--- {d(last_week)} ---\n2h ABC-1 last week\n"
            f"--- {d(monday)} ---\n1.5h ABC-1 a\n0.25h XYZ-2 b\n"
            f"--- {d(TODAY)} ---\n1h ABC-1 c\n"
            "******PROJECT B******\n"
            f"--- {d(TODAY)} ---\n0.75h ABC-9 other section\n"
            "1.5 broken line\n")
        app = self.app
        app.open_summary_history()
        app.update()
        self.assertIn("ABC-9", app._hist_text)
        self.assertIn('Line ', app._hist_text)                       # warnings still listed
        day_total = 1 + 0.75 + (1.75 if TODAY == monday else 0)
        self.assertEqual(sum(r[5] for r in app._hist_rows), day_total)

        app._set_history_mode('weekly')
        self.assertEqual(app._hist_mode_btn.get(), "Weekly")
        self.assertEqual(sum(r[5] for r in app._hist_rows), 1.5 + 0.25 + 1 + 0.75)
        self.assertIn("Per day", app._hist_text)
        self.assertIn(f"Week {monday.isocalendar()[1]} ", app._hist_period_label.cget("text"))
        app._navigate_history(-1)
        self.assertEqual(sum(r[5] for r in app._hist_rows), 2)
        app._navigate_history(1)

        app._set_history_mode('monthly')
        in_month = [(last_week, 2), (monday, 1.75), (TODAY, 1.75)]
        expected = sum(h for day, h in in_month if (day.year, day.month) == (TODAY.year, TODAY.month))
        self.assertEqual(sum(r[5] for r in app._hist_rows), expected)

        app._hist_date_entry.insert(0, "99.99.2020")
        app._hist_jump_to_date()
        self.assertEqual(app._hist_status.cget("text"), "Invalid date")
        app._hist_date_entry.delete(0, "end")
        app._hist_date_entry.insert(0, d(last_week).replace('.', '/'))   # old dd/mm/yyyy input still works
        app._set_history_mode('daily')
        app._hist_jump_to_date()
        self.assertEqual(sum(r[5] for r in app._hist_rows), 2)

        app._hist_copy()
        self.assertEqual(app.clipboard_get(), app._hist_text)

        app.toggle_language()
        self.assertEqual(app._hist_mode_btn.get(), "Täglich")
        self.assertIn("TIMETRACKING ÜBERSICHT", app._hist_text)
        app._set_history_mode('weekly')
        app._navigate_history(1)
        out = self.dir / "week.csv"
        with mock.patch.object(notes.filedialog, 'asksaveasfilename', return_value=str(out)):
            app._hist_export_csv()
        raw = out.read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))                  # BOM for Excel
        rows = list(csv.reader(raw.decode('utf-8-sig').splitlines(), delimiter=';'))
        self.assertEqual(rows[0], ["Datum", "Bereich", "Kunde", "Präfix", "Ticket", "Stunden", "Beschreibung"])
        self.assertIn([d(monday), "PROJECT A", "Xylo", "XYZ", "XYZ-2", "0,25", "b"], rows)
        self.assertEqual(sum(float(r[5].replace(',', '.')) for r in rows[1:]), 1.5 + 0.25 + 1 + 0.75)
        self.assertEqual(app._hist_status.cget("text"), f"{len(rows) - 1} Zeilen exportiert")

        # the open window follows edits of the note
        type_text(app, f"--- {d(TODAY)} ---\n0.5h ABC-10 late\n", at="end-1c")
        app.auto_save()
        self.assertIn("ABC-10", app._hist_text)
        app._on_history_close()
        self.assertIsNone(app._history_window)


if __name__ == '__main__':
    unittest.main()
