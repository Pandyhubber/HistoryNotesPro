import tkinter as tk
import customtkinter as ctk
import sqlite3
import zipfile
import re
import csv
import json
import webbrowser
import sys
import ctypes
import ctypes.wintypes
import logging
import threading
import queue
import hashlib
import calendar
from collections import Counter
from pathlib import Path, PurePosixPath
from datetime import datetime, date, timedelta
from tkinter import messagebox, filedialog


# ==========================================
# PATHS
# ==========================================
def app_dir() -> Path:
    """Folder that holds the database and the log: next to the .exe when frozen, else next to notes.py."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    """Read-only bundled file. A copy next to the app wins, else the one PyInstaller
    unpacked from --add-data into sys._MEIPASS."""
    local = app_dir() / name
    if local.exists():
        return local
    return Path(getattr(sys, '_MEIPASS', app_dir())) / name


# ==========================================
# LOGGING SETUP
# ==========================================
def _setup_logging():
    handlers = [logging.FileHandler(app_dir() / 'historynotespro.log', encoding='utf-8', delay=True)]
    if sys.stdout:  # None in a --noconsole build
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers,
    )

_setup_logging()
log = logging.getLogger(__name__)

# ==========================================
# TASKBAR ICON FIX (AppUserModelID)
# ==========================================
try:
    myappid = 'historynotespro'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

# ==========================================
# 1. LOCALIZATION & CONFIG
# ==========================================
STR_TABLE = {
    "EN": {
        "title": "HistoryNotes PRO", "new": "+ New Note", "del": "Archive", "final_del": "Delete Permanently",
        "restore": "Restore", "pin": "Pin", "unpin": "Unpin", "live": "Live",
        "lang_btn": "Language: EN", "export": "Export (.zip)",
        "import": "Import (.txt/.zip)", "stats": "Words: {} | Chars: {}",
        "confirm_del": "Delete note permanently?", "history_label": "History Version",
        "menu_file_label": "File", "menu_help_label": "Help", "saved": "Saved", "new_note_default": "New Note",
        "welcome_title": "Welcome!", "welcome_text": "This is your first note.\n\nYou can simply edit this text or click '+ New Note' above.",
        "clients_default": "# One line per client: PREFIX = Client Name\n# Example:\n# ACME = Acme Corp\n# INT = Internal\n",
        # Help menu
        "help_shortcuts": "── Keyboard shortcuts ──", "help_syntax": "── Formatting syntax ──",
        "help_shortcut_items": [("Save", "Ctrl+S"), ("Search", "Ctrl+F"), ("Insert timestamp", "Ctrl+T"),
                                ("Bold / fat text", "Ctrl+B")],
        "help_syntax_items": [("Heading", "# text"), ("Orange highlight", "**text**"), ("Fat / bold", "+++text+++"),
                              ("Underline", "__text__"), ("Strikethrough", "~~text~~"), ("Color", "right-click menu"),
                              ("List item", "- text  or  * text")],
        # Editor context menu
        "ctx_cut": "Cut", "ctx_copy": "Copy", "ctx_paste": "Paste", "ctx_bold": "Bold",
        "ctx_underline": "Underline", "ctx_strike": "Strikethrough", "ctx_color": "Color  ▶",
        "ctx_remove_color": "Remove color",
        "color_slate_blue": "Slate Blue", "color_sage_green": "Sage Green", "color_warm_amber": "Warm Amber",
        "color_dusty_rose": "Dusty Rose", "color_muted_teal": "Muted Teal", "color_steel_gray": "Steel Gray",
        # Timetracking history window
        "history_btn": "📊 History", "hist_title": "Timetracking History",
        "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
        "hist_date": "Date (dd.mm.yyyy):", "hist_go": "Go", "hist_copy": "Copy", "hist_csv": "Export CSV",
        "hist_close": "Close", "hist_copied": "Copied to clipboard", "hist_csv_done": "Exported {} rows",
        "hist_csv_empty": "Nothing to export", "hist_bad_date": "Invalid date",
        "no_history": "No historical data available for this period.",
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                   "September", "October", "November", "December"],
        "week_label": "Week {week} ({start}-{end})",
        # Timetracking summary
        "sum_title": "TIMETRACKING SUMMARY", "sum_client_total": "Client total:", "sum_total": "TOTAL LOGGED:",
        "sum_general": "General", "sum_unknown": "Unknown ({})", "sum_per_day": "Per day",
        "sum_archived": "From archive (no longer in the note): {}",
        "sum_legacy": "Text-only archive, not in the totals: {}",
        "sum_warnings": "⚠ Warnings:",
        "warn_bad_date": 'Line {}: invalid date marker  "{}"', "warn_unparseable": 'Line {}: unparseable  "{}"',
        "warn_no_ticket": 'Line {}: unparseable (no ticket)  "{}"', "warn_undated": 'Line {}: undated entry  "{}"',
        "csv_header": ["Date", "Section", "Client", "Prefix", "Ticket", "Hours", "Description"],
    },
    "DE": {
        "title": "HistoryNotes PRO", "new": "+ Neue Notiz", "del": "Archivieren", "final_del": "Endgültig Löschen",
        "restore": "Wiederherstellen", "pin": "Pinnen", "unpin": "Entpinnen", "live": "Live",
        "lang_btn": "Sprache: DE", "export": "Export (.zip)",
        "import": "Import (.txt/.zip)", "stats": "Wörter: {} | Zeichen: {}",
        "confirm_del": "Notiz wirklich endgültig löschen?", "history_label": "Versionsverlauf",
        "menu_file_label": "Datei", "menu_help_label": "Hilfe", "saved": "Gespeichert", "new_note_default": "Neue Notiz",
        "welcome_title": "Willkommen!", "welcome_text": "Dies ist deine erste Notiz.\n\nDu kannst diesen Text einfach löschen oder oben auf '+ Neue Notiz' klicken.",
        "clients_default": "# Eine Zeile pro Kunde: PRÄFIX = Kundenname\n# Beispiel:\n# ACME = Acme Corp\n# INT = Intern\n",
        # Help menu
        "help_shortcuts": "── Tastenkürzel ──", "help_syntax": "── Formatierung ──",
        "help_shortcut_items": [("Speichern", "Strg+S"), ("Suchen", "Strg+F"), ("Zeitstempel einfügen", "Strg+T"),
                                ("Fett", "Strg+B")],
        "help_syntax_items": [("Überschrift", "# Text"), ("Orange Hervorhebung", "**Text**"), ("Fett", "+++Text+++"),
                              ("Unterstrichen", "__Text__"), ("Durchgestrichen", "~~Text~~"), ("Farbe", "Rechtsklick-Menü"),
                              ("Listenpunkt", "- Text  oder  * Text")],
        # Editor context menu
        "ctx_cut": "Ausschneiden", "ctx_copy": "Kopieren", "ctx_paste": "Einfügen", "ctx_bold": "Hervorheben",
        "ctx_underline": "Unterstreichen", "ctx_strike": "Durchstreichen", "ctx_color": "Farbe  ▶",
        "ctx_remove_color": "Farbe entfernen",
        "color_slate_blue": "Schieferblau", "color_sage_green": "Salbeigrün", "color_warm_amber": "Bernstein",
        "color_dusty_rose": "Altrosa", "color_muted_teal": "Petrol", "color_steel_gray": "Stahlgrau",
        # Timetracking history window
        "history_btn": "📊 Verlauf", "hist_title": "Timetracking-Verlauf",
        "daily": "Täglich", "weekly": "Wöchentlich", "monthly": "Monatlich",
        "hist_date": "Datum (TT.MM.JJJJ):", "hist_go": "Los", "hist_copy": "Kopieren", "hist_csv": "CSV exportieren",
        "hist_close": "Schließen", "hist_copied": "In die Zwischenablage kopiert", "hist_csv_done": "{} Zeilen exportiert",
        "hist_csv_empty": "Nichts zu exportieren", "hist_bad_date": "Ungültiges Datum",
        "no_history": "Keine historischen Daten für diesen Zeitraum verfügbar.",
        "weekdays": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
                   "September", "Oktober", "November", "Dezember"],
        "week_label": "KW {week} ({start}-{end})",
        # Timetracking summary
        "sum_title": "TIMETRACKING ÜBERSICHT", "sum_client_total": "Kunde gesamt:", "sum_total": "GESAMT ERFASST:",
        "sum_general": "Allgemein", "sum_unknown": "Unbekannt ({})", "sum_per_day": "Pro Tag",
        "sum_archived": "Aus dem Archiv (nicht mehr in der Notiz): {}",
        "sum_legacy": "Nur als Text archiviert, nicht in den Summen: {}",
        "sum_warnings": "⚠ Warnungen:",
        "warn_bad_date": 'Zeile {}: ungültige Datumszeile  "{}"', "warn_unparseable": 'Zeile {}: nicht lesbar  "{}"',
        "warn_no_ticket": 'Zeile {}: nicht lesbar (kein Ticket)  "{}"', "warn_undated": 'Zeile {}: Eintrag ohne Datum  "{}"',
        "csv_header": ["Datum", "Bereich", "Kunde", "Präfix", "Ticket", "Stunden", "Beschreibung"],
    }
}

# UI colour constants -- single source of truth
CLR_BTN_DELETE           = "#882222"
CLR_BTN_DELETE_HARD      = "#FF0000"
CLR_BTN_RESTORE          = "#228844"
CLR_BTN_TT_HISTORY       = "#2b5b84"
CLR_BTN_TT_HISTORY_HOVER = "#3a7ab5"
CLR_ARCHIVE_ACTIVE       = "#445566"
CLR_ARCHIVE_IDLE         = "gray25"
CLR_SIDEBAR_HOVER        = "gray30"
CLR_VERSION_LIVE         = "white"
CLR_VERSION_OLD          = "#ffcc00"

# Text colours for [key]...[/key]. The key is stored in the note text, so it must never change.
FORMAT_COLORS = [
    ("slate_blue", "#7B9EC9"),
    ("sage_green", "#7EAA7E"),
    ("warm_amber", "#C9A84C"),
    ("dusty_rose", "#B87A7A"),
    ("muted_teal", "#5FA8A0"),
    ("steel_gray", "#8A9BB0"),
]

HIST_MODES = ('daily', 'weekly', 'monthly')


# ==========================================
# HELPERS
# ==========================================
def fmt_hours(hours: float) -> str:
    """At most two decimals, trailing zeros dropped: 2 -> '2', 2.5 -> '2.5', 0.25 -> '0.25'."""
    return f"{hours:.2f}".rstrip("0").rstrip(".")


def _match_len(matches, limit: int) -> int:
    """Largest k <= limit for which matches(k) holds; matches must be monotone."""
    lo, hi = 0, limit
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if matches(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


def changed_chars(old: str, new: str) -> int:
    """Size of the edited region: what is left after stripping the common prefix and suffix."""
    if old == new:
        return 0
    limit = min(len(old), len(new))
    p = _match_len(lambda k: old[:k] == new[:k], limit)
    s = _match_len(lambda k: old[len(old) - k:] == new[len(new) - k:], limit - p)
    return max(len(old), len(new)) - p - s


def period_range(mode: str, anchor: date):
    """(first, last) day of the daily, weekly (Mon-Sun) or monthly period containing anchor."""
    if mode == 'daily':
        return anchor, anchor
    if mode == 'weekly':
        monday = anchor - timedelta(days=anchor.weekday())
        return monday, monday + timedelta(days=6)
    first = anchor.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def shift_anchor(mode: str, anchor: date, steps: int) -> date:
    """Move anchor by whole periods; a month step keeps the day where the month allows it."""
    if mode == 'daily':
        return anchor + timedelta(days=steps)
    if mode == 'weekly':
        return anchor + timedelta(weeks=steps)
    months = anchor.year * 12 + anchor.month - 1 + steps
    year, month = months // 12, months % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


_INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED_FILENAMES = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_filename(title: str, used: set) -> str:
    """Windows-safe, unique .txt name for a note title. `used` collects the names handed out so far."""
    base = _INVALID_FILENAME_RE.sub("_", title or "").strip().rstrip(". ") or "note"
    if base.upper() in _RESERVED_FILENAMES:
        base = f"_{base}"
    name, n = base, 2
    while name.casefold() in used:
        name = f"{base} ({n})"
        n += 1
    used.add(name.casefold())
    return f"{name}.txt"


_GEOMETRY_RE = re.compile(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)')
_TITLE_BAR_PROBE_Y = 10      # px below the window's top edge, inside the title bar
_TITLE_BAR_PROBE_X = 60      # px in from the left edge, next to the icon


def monitor_at(x: int, y: int) -> bool:
    """True if the screen point lies on a connected monitor (Windows, all monitors incl. negative coordinates)."""
    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    MONITOR_DEFAULTTONULL = 0
    return bool(user32.MonitorFromPoint(ctypes.wintypes.POINT(x, y), MONITOR_DEFAULTTONULL))


def geometry_reachable(geo: str, scaling: float, on_screen) -> bool:
    """Is the title bar of a saved window geometry grabbable on the current monitors?

    geo is CTk's geometry(): width/height divided by the DPI scaling, x/y in screen pixels.
    A geometry saved with a monitor that is no longer connected fails, so the window
    is not restored into the void.
    """
    m = _GEOMETRY_RE.fullmatch(geo or "")
    if not m:
        return False
    width, _, x, y = map(int, m.groups())
    probe_y = y + _TITLE_BAR_PROBE_Y
    return any(on_screen(px, probe_y) for px in (x + _TITLE_BAR_PROBE_X, x + round(width * scaling) // 2))


def _casefold(value):
    return value.casefold() if isinstance(value, str) else ""


# ==========================================
# 2. DATA ACCESS LAYER
# ==========================================
class NoteVault:
    """
    Thread-safe SQLite access.
    - WAL mode is set once on the main-thread read connection before the
      writer thread starts, so there is no lock contention on startup.
    - All writes are serialised through a queue served by a single writer
      thread; reads run on the caller (main) thread. A queue item is a list
      of statements that commit together.
    - flush() waits until every queued write is committed, for reads that
      must see them.
    """
    SCHEMA_VERSION = 2

    def __init__(self, db_path: Path):
        self._db_path = db_path
        # Open + configure the read connection first, while no writer exists yet
        self._rconn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        self._rconn.execute("PRAGMA journal_mode=WAL")
        self._rconn.commit()
        # Python-side case folding: SQLite's LOWER() only knows ASCII, so "Ä" never matched "ä"
        self._rconn.create_function("casefold", 1, _casefold, deterministic=True)
        # Now start the writer thread (it opens its own connection, WAL already set)
        self._write_queue: queue.Queue = queue.Queue()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        self._setup_db()

    # ------------------------------------------------------------------
    # Writer thread
    # ------------------------------------------------------------------
    def _writer_loop(self):
        wconn = sqlite3.connect(str(self._db_path), timeout=30, check_same_thread=False)
        while True:
            item = self._write_queue.get()
            if item is None:          # poison pill
                wconn.close()
                break
            ops, evt, box = item
            try:
                cur = None
                with wconn:
                    for sql, params in ops:
                        cur = wconn.execute(sql, params)
                if box is not None:
                    box.append(cur.lastrowid if cur else None)
            except Exception as e:
                # SQL only: the parameters carry note content, which does not belong in a log file
                log.error("DB write error: %s | sql=%s", e, [sql for sql, _ in ops])
                if box is not None:
                    box.append(e)
            finally:
                if evt:
                    evt.set()

    def _write(self, ops: list):
        """Fire-and-forget write."""
        self._write_queue.put((ops, None, None))

    def _write_sync(self, ops: list, timeout: float = 5):
        """Blocking write -- waits for completion, returns the last rowid, re-raises on error."""
        evt = threading.Event()
        box: list = []
        self._write_queue.put((ops, evt, box))
        if not evt.wait(timeout=timeout):
            log.error("_write_sync timed out | sql=%s", [sql for sql, _ in ops])
            return None
        if box and isinstance(box[0], Exception):
            raise box[0]
        return box[0] if box else None

    def flush(self):
        """Barrier: returns once every write queued before it is committed."""
        self._write_sync([])

    def close(self):
        self._write_queue.put(None)
        self._writer_thread.join(timeout=3)
        self._rconn.close()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------
    def _setup_db(self):
        self._write_sync([(sql, ()) for sql in [
            'CREATE TABLE IF NOT EXISTS note_list (id INTEGER PRIMARY KEY, title TEXT, pinned INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0, last_content TEXT, last_updated TEXT)',
            'CREATE TABLE IF NOT EXISTS history (note_id INTEGER, content TEXT, timestamp TEXT)',
            'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)',
            'CREATE TABLE IF NOT EXISTS summary_history (date TEXT PRIMARY KEY, content TEXT, created_at TEXT)',
            'CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)',
            'CREATE INDEX IF NOT EXISTS idx_history_note ON history (note_id, timestamp)',
        ]])
        self._migrate()
        if self._rconn.execute("SELECT COUNT(*) FROM note_list").fetchone()[0] == 0:
            lang = self.get_setting("lang", "EN")
            s = STR_TABLE.get(lang, STR_TABLE["EN"])
            self.create_note(s["welcome_title"], s["welcome_text"])

    def _migrate(self):
        """Additive only, so an older build still opens a migrated database."""
        version = self._rconn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
        ops = []
        if version < 1:
            ops.append(("INSERT OR IGNORE INTO schema_version (version) VALUES (1)", ()))
        if version < 2:
            # v2: per-day timetracking entries as JSON next to the rendered text
            cols = {row[1] for row in self._rconn.execute("PRAGMA table_info(summary_history)")}
            if 'entries_json' not in cols:
                ops.append(("ALTER TABLE summary_history ADD COLUMN entries_json TEXT", ()))
            ops.append(("INSERT OR IGNORE INTO schema_version (version) VALUES (2)", ()))
        if ops:
            self._write_sync(ops)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str) -> str:
        res = self._rconn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res[0] if res else default

    def set_setting(self, key: str, value: str):
        self._write([("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))])

    def fetch_sidebar_notes(self, search_term: str, show_archived: bool):
        q = "SELECT id, title, pinned, is_deleted FROM note_list WHERE is_deleted = ?"
        p = [1 if show_archived else 0]
        if search_term:
            needle = search_term.casefold()
            q += " AND (instr(casefold(title), ?) > 0 OR instr(casefold(last_content), ?) > 0)"
            p += [needle, needle]
        q += " ORDER BY pinned DESC, last_updated DESC"
        return self._rconn.execute(q, p).fetchall()

    def get_note(self, nid: int):
        return self._rconn.execute("SELECT title, last_content, is_deleted FROM note_list WHERE id = ?", (nid,)).fetchone()

    def find_active_note_id(self, title: str):
        row = self._rconn.execute(
            "SELECT id FROM note_list WHERE title = ? AND is_deleted = 0 ORDER BY id LIMIT 1", (title,)
        ).fetchone()
        return row[0] if row else None

    def get_history(self, nid: int):
        rows = self._rconn.execute(
            "SELECT timestamp, content FROM history WHERE note_id = ? ORDER BY timestamp ASC, rowid ASC", (nid,)
        ).fetchall()
        return [(r[0][11:16] if 'T' in r[0] else r[0][:16], r[1]) for r in rows]

    def get_history_count(self, nid: int) -> int:
        row = self._rconn.execute("SELECT COUNT(*) FROM history WHERE note_id = ?", (nid,)).fetchone()
        return row[0] if row else 0

    def get_last_history_content(self, nid: int):
        row = self._rconn.execute(
            "SELECT content FROM history WHERE note_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 1", (nid,)
        ).fetchone()
        return row[0] if row else None

    def save_note(self, nid: int, title: str, content: str, add_history: bool = False):
        now_str = datetime.now().isoformat()
        ops = [("UPDATE note_list SET title = ?, last_content = ?, last_updated = ? WHERE id = ?",
                (title, content, now_str, nid))]
        if add_history:
            ops.append(("INSERT INTO history (note_id, content, timestamp) VALUES (?, ?, ?)",
                        (nid, content, now_str)))
        self._write(ops)

    def add_history(self, nid: int, content: str):
        self._write([("INSERT INTO history (note_id, content, timestamp) VALUES (?, ?, ?)",
                      (nid, content, datetime.now().isoformat()))])

    def create_note(self, title: str, content: str = ""):
        """Synchronous insert so we can return the new id."""
        return self._write_sync([("INSERT INTO note_list (title, last_content, last_updated) VALUES (?, ?, ?)",
                                  (title, content, datetime.now().isoformat()))])

    def delete_note_soft(self, nid: int):
        self._write_sync([("UPDATE note_list SET is_deleted = 1, pinned = 0 WHERE id = ?", (nid,))])

    def delete_note_hard(self, nid: int):
        self._write_sync([("DELETE FROM note_list WHERE id = ?", (nid,)),
                          ("DELETE FROM history WHERE note_id = ?", (nid,))])

    def restore_note(self, nid: int):
        self._write_sync([("UPDATE note_list SET is_deleted = 0 WHERE id = ?", (nid,))])

    def toggle_pin(self, nid: int):
        self._write_sync([("UPDATE note_list SET pinned = 1 - pinned WHERE id = ?", (nid,))])

    def get_latest_active_id(self):
        row = self._rconn.execute(
            "SELECT id FROM note_list WHERE is_deleted = 0 ORDER BY pinned DESC, last_updated DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def get_export_data(self):
        return self._rconn.execute("SELECT title, last_content FROM note_list WHERE is_deleted = 0").fetchall()

    # === Timetracking summary archive ===
    # date is 'dd/mm/yyyy' as in every earlier version; range filtering happens in Python.
    def get_summary_rows(self):
        return self._rconn.execute("SELECT date, content, entries_json FROM summary_history").fetchall()

    def save_summary_snapshots(self, rows: list):
        """rows: [(date_key, content, entries_json)], written in one transaction."""
        now_str = datetime.now().isoformat()
        self._write([(
            "INSERT OR REPLACE INTO summary_history (date, content, created_at, entries_json) VALUES (?, ?, ?, ?)",
            (date_key, content, now_str, entries_json),
        ) for date_key, content, entries_json in rows])


# ==========================================
# 3. UI COMPONENTS
# ==========================================
class NoteButton(ctk.CTkFrame):
    def __init__(self, master, note_id, title, pinned, is_deleted, select_cmd, pin_cmd, get_str_cmd):
        super().__init__(master, fg_color="transparent")
        self.note_id = note_id
        self.get_str = get_str_cmd
        self._pinned = pinned
        self._pin_cmd = pin_cmd
        self._is_deleted = is_deleted

        self.btn = ctk.CTkButton(self, anchor="w", text="", fg_color="transparent", hover_color=CLR_SIDEBAR_HOVER,
                                 command=lambda: select_cmd(note_id))
        self.btn.pack(side="left", fill="x", expand=True)
        self._last_text = None  # tracked independently of CTk internals
        self.update_data(title, pinned)

        if not is_deleted:
            self.btn.bind("<Button-3>", self._show_pin_menu)
            self.bind("<Button-3>", self._show_pin_menu)

    def _show_pin_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        label = self.get_str("unpin") if self._pinned else self.get_str("pin")
        menu.add_command(label=label, command=lambda: self._pin_cmd(self.note_id))
        menu.tk_popup(event.x_root, event.y_root)

    def update_data(self, title, pinned):
        display = (title if title and title.strip() else "...").replace("\n", " ")
        new_text = f"{'📌 ' if pinned else ''}{display}"
        if pinned == self._pinned and self._last_text == new_text:
            return  # nothing changed, skip unnecessary configure call
        self._pinned = pinned
        self._last_text = new_text
        self.btn.configure(text=new_text)


# ==========================================
# 4. TIMETRACKING ENGINE
# ==========================================
class TimetrackingEngine:
    """
    Parses a Timetracking note and a Clients mapping note.
    Produces a structured summary: per-client ticket lines, totals, warnings.

    Entry formats supported (one per line):
        1.5h PREFIX-123 description
        0.5h PREFIX 123 description
        0.5h PREFIX-123            (no description)

    Date marker format (inserted by Ctrl+T in Timetracking note):
        --- DD.MM.YYYY ---

    Section header, e.g. ******PROJECT A******, ******PROJECT B******.
    A bare ****** line also acts as a section separator.

    Client mapping format (one per line in Timetracking Clients note):
        PREFIX = Client Name

    Lines are split on '\n' only, so line numbers match the Tk text widget.
    """

    # Matches a time value at the start: 1h, 1.5h, 1,5h, 0.5h etc.
    _TIME_RE = re.compile(r'^(\d+(?:[.,]\d+)?)h\s+', re.IGNORECASE)
    # Looks like a time entry but may be malformed
    _LOOKS_LIKE_ENTRY_RE = re.compile(r'^\d')
    # Date marker: --- DD.MM.YYYY --- (optionally followed by a total annotation)
    _DATE_RE = re.compile(r'^---\s*(\d{2})\.(\d{2})\.(\d{4})\s*---')
    _SECTION_RE = re.compile(r'^\*{6}(?:.*\*{6})?$')
    # Client mapping line: PREFIX = Name
    _CLIENT_RE = re.compile(r'^\s*([A-Z0-9]+)\s*=\s*(.+)$', re.IGNORECASE)
    # The total annotation we append to a date line
    _TOTAL_ANNOTATION_RE = re.compile(r'\s*\[[\d.,]+h\]$')

    def parse_clients(self, clients_content: str) -> dict:
        """Returns {PREFIX_UPPER: display_name}"""
        mapping = {}
        for line in clients_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = self._CLIENT_RE.match(line)
            if m:
                mapping[m.group(1).upper()] = m.group(2).strip()
        return mapping

    def uses_sections(self, tt_content: str) -> bool:
        return any(self._SECTION_RE.match(raw.strip()) for raw in tt_content.split('\n'))

    def parse_entries(self, tt_content: str):
        """
        Returns:
            entries  : list of dicts {date, section, prefix, ticket, hours, description}, in note order
            warnings : list of (code, lineno, line); code is bad_date, unparseable, no_ticket or undated
        """
        entries = []
        warnings = []
        current_date = None
        current_section = ''

        for lineno, raw in enumerate(tt_content.split('\n'), start=1):
            line = raw.strip()
            if not line:
                continue

            # Section header (******TEXT******): entries below it belong to this section only.
            if self._SECTION_RE.match(line):
                current_section = line.strip('*').strip()
                continue

            dm = self._DATE_RE.match(line)
            if dm:
                day, month, year = dm.group(1), dm.group(2), dm.group(3)
                try:
                    current_date = date(int(year), int(month), int(day))
                except ValueError:
                    warnings.append(('bad_date', lineno, raw.rstrip()))
                continue

            if not self._LOOKS_LIKE_ENTRY_RE.match(line):
                continue  # plain text / description line, ignore silently

            tm = self._TIME_RE.match(line)
            if not tm:
                warnings.append(('unparseable', lineno, raw.rstrip()))
                continue

            hours = float(tm.group(1).replace(',', '.'))
            rest = line[tm.end():].strip()
            if not rest:
                warnings.append(('no_ticket', lineno, raw.rstrip()))
                continue

            parts = rest.split()
            first = parts[0]
            if '-' in first:
                # Format: PREFIX-123 description
                prefix = first.split('-', 1)[0].upper()
                ticket = first  # keep full "PREFIX-123" as ticket id
                description = ' '.join(parts[1:])
            else:
                # Format: PREFIX 123 description  or  PREFIX description
                prefix = first.upper()
                if len(parts) > 1:
                    ticket = f"{prefix}-{parts[1]}" if parts[1].isdigit() else parts[1]
                    description = ' '.join(parts[2:])
                else:
                    ticket = prefix
                    description = ''

            if current_date is None:
                warnings.append(('undated', lineno, raw.rstrip()))
                continue

            entries.append({
                'date': current_date,
                'section': current_section,
                'prefix': prefix,
                'ticket': ticket,
                'hours': hours,
                'description': description,
            })

        return entries, warnings

    @staticmethod
    def aggregate(entries: list, by_section: bool = True) -> dict:
        """
        { section: { prefix: { ticket: {'hours': float, 'descriptions': [str]} } } }
        Sections keep the order in which they first appear; without by_section
        everything lands in section ''.
        """
        result = {}
        for e in entries:
            section = e['section'] if by_section else ''
            tickets = result.setdefault(section, {}).setdefault(e['prefix'], {})
            t = tickets.setdefault(e['ticket'], {'hours': 0.0, 'descriptions': []})
            t['hours'] += e['hours']
            if e['description']:
                t['descriptions'].append(e['description'])
        return result

    # ------------------------------------------------------------------
    # Date-line totals
    # ------------------------------------------------------------------
    def _date_line_totals(self, lines: list) -> dict:
        """
        {line index: hours} for every date-marker line. A marker only sums the
        entries below it within its own section, so the same date can appear in
        several sections and each marker shows only its own hours.
        """
        totals = {}
        current = None  # index of the most recent date marker in this section
        for idx, raw in enumerate(lines):
            line = raw.strip()
            if not line:
                continue
            # A section header finalises the previous date marker: entries below it
            # belong to the new section and must not leak into that total.
            if self._SECTION_RE.match(line):
                current = None
                continue
            if self._DATE_RE.match(line):
                current = idx
                totals[idx] = 0.0
                continue
            if current is not None:
                tm = self._TIME_RE.match(line)
                if tm:
                    totals[current] += float(tm.group(1).replace(",", "."))
        return totals

    def _date_line_base(self, raw: str) -> str:
        """Date line without its annotation and trailing blanks, leading indent kept."""
        leading = raw[: len(raw) - len(raw.lstrip())]
        return leading + self._TOTAL_ANNOTATION_RE.sub("", raw.strip()).rstrip()

    def totals_updates(self, content: str) -> list:
        """[(line index, new line)] for every date-marker line whose annotation is missing or outdated.
            --- 21.05.2026 ---  ->  --- 21.05.2026 --- [4.25h]"""
        lines = content.split('\n')
        updates = []
        for idx, hours in self._date_line_totals(lines).items():
            new_line = f"{self._date_line_base(lines[idx])} [{fmt_hours(hours)}h]"
            if new_line != lines[idx]:
                updates.append((idx, new_line))
        return updates

    def inject_totals(self, content: str) -> str:
        """Content with every date-marker line annotated with its summed hours."""
        lines = content.split('\n')
        for idx, new_line in self.totals_updates(content):
            lines[idx] = new_line
        return '\n'.join(lines)

    def strip_totals(self, content: str) -> str:
        """Content with the annotations removed, to tell real edits from totals refreshes."""
        return '\n'.join(self._date_line_base(raw) if self._DATE_RE.match(raw.strip()) else raw
                         for raw in content.split('\n'))

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    def render_report(self, label: str, entries: list, client_map: dict, s: dict, use_sections: bool,
                      per_day: bool = False, warnings=(), footer=()) -> str:
        """Plain-text summary. s is the STR_TABLE entry of the UI language."""
        def hrs(value):
            return f"{fmt_hours(value) + 'h':>7}"

        lines = [f"{s['sum_title']}  ·  {label}", ""]

        if per_day:
            day_totals = {}
            for e in entries:
                day_totals[e['date']] = day_totals.get(e['date'], 0.0) + e['hours']
            if day_totals:
                lines.append(s['sum_per_day'])
                for d in sorted(day_totals):
                    lines.append(f"  {s['weekdays'][d.weekday()]} {d:%d.%m.%Y}  {hrs(day_totals[d])}")
                lines.append("")

        total_hours = 0.0
        for section, prefixes in self.aggregate(entries, by_section=use_sections).items():
            if use_sections:
                lines.append(f"****** {section or s['sum_general']} ******")
            for prefix in sorted(prefixes):
                tickets = prefixes[prefix]
                name = client_map.get(prefix) or s['sum_unknown'].format(prefix)
                client_total = sum(t['hours'] for t in tickets.values())
                total_hours += client_total
                lines.append(f"── {name} ({prefix}) " + "─" * max(2, 44 - len(name) - len(prefix)))
                for ticket in sorted(tickets):
                    tdata = tickets[ticket]
                    desc_str = ' / '.join(dict.fromkeys(tdata['descriptions']))  # deduplicate, preserve order
                    desc_str = (desc_str[:50] + '…') if len(desc_str) > 50 else desc_str
                    lines.append(f"  {ticket:<18} {hrs(tdata['hours'])}   {desc_str}".rstrip())
                lines.append(f"  {s['sum_client_total']:<18} {hrs(client_total)}")
                lines.append("")
            if use_sections:
                lines.append("")

        lines.append("═" * 48)
        lines.append(f"  {s['sum_total']:<18} {hrs(total_hours)}")
        lines.append("")

        if footer:
            lines.extend(footer)
            lines.append("")

        if warnings:
            lines.append(s['sum_warnings'])
            for code, lineno, raw in warnings:
                lines.append(f"  {s['warn_' + code].format(lineno, raw)}")

        return '\n'.join(lines)

    @staticmethod
    def csv_rows(entries: list, client_map: dict) -> list:
        """One row per day, section and ticket: (date, section, client, prefix, ticket, hours, description)."""
        rows = {}
        for e in sorted(entries, key=lambda e: e['date']):  # stable: note order within a day
            r = rows.setdefault((e['date'], e['section'], e['prefix'], e['ticket']),
                                {'hours': 0.0, 'descriptions': []})
            r['hours'] += e['hours']
            if e['description']:
                r['descriptions'].append(e['description'])
        return [(d, section, client_map.get(prefix, ''), prefix, ticket, r['hours'],
                 ' / '.join(dict.fromkeys(r['descriptions'])))
                for (d, section, prefix, ticket), r in rows.items()]


# === Timetracking archive: per-day entries stored in summary_history ===
def entries_to_json(day_entries: list) -> str:
    return json.dumps([[e['section'], e['prefix'], e['ticket'], e['hours'], e['description']] for e in day_entries],
                      ensure_ascii=False, separators=(',', ':'))


def entries_from_json(day: date, raw: str):
    """None when the row predates the JSON column or cannot be read."""
    if not raw:
        return None
    try:
        return [{'date': day, 'section': sec, 'prefix': prefix, 'ticket': ticket, 'hours': float(hours),
                 'description': desc} for sec, prefix, ticket, hours, desc in json.loads(raw)]
    except (ValueError, TypeError) as e:
        log.warning("Unreadable timetracking archive row %s: %s", day, e)
        return None


def snapshot_updates(entries: list, known: dict) -> list:
    """[(date, entries_json, day_entries)] for every date whose entries differ from the archive.
    known: {date: entries_json or None}"""
    per_day = {}
    for e in entries:
        per_day.setdefault(e['date'], []).append(e)
    updates = []
    for d, day_entries in per_day.items():
        js = entries_to_json(day_entries)
        if known.get(d) != js:
            updates.append((d, js, day_entries))
    return updates


def moved_away_days(previous, current: list) -> list:
    """
    Days that left the note in one edit while all their entries showed up under
    another date in that same edit: a corrected date marker, not pruning. Their
    archive rows must be emptied, or period totals would count those hours twice.
    previous: entries at the last sync, None when unknown.
    """
    if previous is None:
        return []
    def key(e):
        return (e['section'], e['prefix'], e['ticket'], e['hours'], e['description'])
    added = (Counter((e['date'],) + key(e) for e in current)
             - Counter((e['date'],) + key(e) for e in previous))
    added_anywhere = Counter()
    for k, n in added.items():
        added_anywhere[k[1:]] += n
    current_days = {e['date'] for e in current}
    moved = []
    for day in sorted({e['date'] for e in previous} - current_days):
        left = Counter(key(e) for e in previous if e['date'] == day)
        if not (left - added_anywhere):
            moved.append(day)
    return moved


def select_period_entries(live_entries: list, archive: dict, start: date, end: date):
    """
    The Timetracking note is the source of truth for every date from its
    earliest entry on: corrections and moved date markers count as they are
    now. Older dates come from the archive, so pruning old lines from the note
    loses nothing.
    archive: {date: (text, entries or None)}; None marks a text-only row from
    before the JSON column.
    Returns (entries, archived_dates, legacy_dates).
    """
    note_start = min((e['date'] for e in live_entries), default=None)
    archived_entries, archived, legacy = [], [], []
    for d in sorted(archive):
        if not (start <= d <= end) or (note_start is not None and d >= note_start):
            continue
        day_entries = archive[d][1]
        if day_entries is None:
            legacy.append(d)
        elif day_entries:
            archived_entries.extend(day_entries)
            archived.append(d)
    live = [e for e in live_entries if start <= e['date'] <= end]
    return archived_entries + live, archived, legacy


# ==========================================
# 5. MAIN APPLICATION
# ==========================================
class HistoryNotesApp(ctk.CTk):
    TITLE_TT      = "Timetracking"
    TITLE_CLIENTS = "Timetracking Clients"
    TITLE_MAX_LEN = 40
    FORMAT_DELAY_MS = 50
    SAVE_DELAY_MS   = 1000
    TOTALS_DELAY_MS = 800
    HISTORY_MIN_CHANGE = 5   # changed characters since the last history version

    # Regex: matches [colorname]...[/colorname]
    _COLOR_TAG_RE = re.compile(r'\[([a-z_]+)\](.*?)\[/\1\]', re.DOTALL)
    _COLOR_TAGS = ["color_" + key for key, _ in FORMAT_COLORS]
    _MARKDOWN_TAGS = ["h1", "bold", "list", "timestamp", "url", "search_match",
                      "underline", "strikethrough"] + _COLOR_TAGS

    def __init__(self):
        super().__init__()

        self.vault = NoteVault(app_dir() / 'notes_vault.db')

        # Set Window/Taskbar Icon
        icon_path = resource_path('app_icon.ico')
        if icon_path.exists():
            self.iconbitmap(str(icon_path))

        self.lang = self.vault.get_setting("lang", "EN")
        if self.lang not in STR_TABLE:
            self.lang = "EN"
        self.current_note_id = None
        self.show_archived = False
        self.current_title_cache = ""
        self.history_snapshots = []
        self.is_loading = False

        self._saved_content = ""               # editor text as last saved or shown from history
        self._last_history_content = None      # newest history version of the current note
        self._history_count = 0
        self._viewing_history = False          # slider shows an older version

        self._after_id_format = None
        self._after_id_save = None
        self._after_id_totals = None
        self._sidebar_cache: dict = {}   # note_id -> NoteButton widget
        self._sidebar_order: list = []   # ordered list of currently visible note_ids
        self._sidebar_pinned_count: int = 0  # how many pinned notes are at the top of _sidebar_order

        # Timetracking
        self._tt_engine = TimetrackingEngine()
        self._tt_id = None
        self._clients_id = None
        self._history_window = None      # Reference to the history popup window
        self._last_tt_hash: str = ""     # skip redundant archive syncs
        self._archive_known = None       # {date: entries_json}, loaded on first sync
        self._tt_prev_entries = None     # entries at the last sync, to tell moved days from pruned ones

        self.geometry("1100x850")
        ctk.set_appearance_mode("dark")

        self._init_ui()
        self.update_ui_texts()
        self._ensure_special_notes()
        self.refresh_sidebar()
        self.load_latest_or_empty()

        # Restore window geometry from last session, unless its monitor is gone
        saved_geo = self.vault.get_setting("window_geometry", "")
        if saved_geo and geometry_reachable(saved_geo, self._get_window_scaling(), self._on_screen):
            try:
                self.geometry(saved_geo)
            except Exception:
                pass

        self.bind("<Control-f>", self.focus_search)
        self.bind("<Control-s>", self.manual_save)
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _init_ui(self):
        self.menubar = tk.Menu(self)
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(menu=self.file_menu)
        self._menu_file_idx = self.menubar.index("end")
        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(menu=self.help_menu)
        self._menu_help_idx = self.menubar.index("end")
        self.config(menu=self.menubar)

        self.paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#1a1a1a", sashwidth=2, borderwidth=0)
        self.paned_window.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(self.paned_window, width=280, corner_radius=0)
        self.paned_window.add(self.sidebar, width=280, minsize=180)

        self.new_btn = ctk.CTkButton(self.sidebar, command=self.create_new_note)
        self.new_btn.pack(pady=10, padx=10)

        self.search_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.search_frame.pack(fill="x", padx=10)
        self.search_bar = ctk.CTkEntry(self.search_frame)
        self.search_bar.pack(side="left", fill="x", expand=True, pady=5)
        self.search_bar.bind("<KeyRelease>", self._on_search_key)

        self.archive_toggle_btn = ctk.CTkButton(self.search_frame, text="📦", width=35, fg_color=CLR_ARCHIVE_IDLE,
                                                command=self.toggle_archive_view)
        self.archive_toggle_btn.pack(side="right", padx=(5, 0))

        self.note_list_frame = ctk.CTkScrollableFrame(self.sidebar, label_text="Notes")
        self.note_list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.lang_btn = ctk.CTkButton(self.sidebar, fg_color="gray20", command=self.toggle_language)
        self.lang_btn.pack(side="bottom", pady=10)

        self.main_content = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        self.paned_window.add(self.main_content, minsize=400)
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(0, weight=1)

        self.editor_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.editor_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=10)
        self.editor_container.grid_columnconfigure(0, weight=1)
        self.editor_container.grid_rowconfigure(2, weight=1)

        self.top_bar = ctk.CTkFrame(self.editor_container, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", pady=(0,5))

        self.del_btn = ctk.CTkButton(self.top_bar, fg_color=CLR_BTN_DELETE, width=140, command=self.handle_delete_action)
        self.del_btn.pack(side="right")
        self.restore_btn = ctk.CTkButton(self.top_bar, fg_color=CLR_BTN_RESTORE, width=140, command=self.restore_note)

        self.title_entry = ctk.CTkEntry(self.editor_container, font=("Segoe UI", 22, "bold"), fg_color="transparent", border_width=0)
        self.title_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.title_entry.bind("<KeyRelease>", self.on_key_release)
        self.title_entry.bind("<Tab>", lambda e: self.editor.focus_set() or "break")

        self.editor = ctk.CTkTextbox(self.editor_container, font=("Consolas", 16), undo=True, fg_color="#121212")
        self.editor.grid(row=2, column=0, sticky="nsew")

        self.status_bar = ctk.CTkLabel(self.editor_container, text="", font=("Segoe UI", 11), text_color="gray")
        self.status_bar.grid(row=3, column=0, sticky="w", pady=2)

        self.history_panel = ctk.CTkFrame(self.main_content, height=80)
        self.history_panel.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        self.hist_label = ctk.CTkLabel(self.history_panel, font=("Segoe UI", 12, "bold"))
        self.hist_label.pack(side="top", pady=2)

        self.slider_frame = ctk.CTkFrame(self.history_panel, fg_color="transparent")
        self.slider_frame.pack(fill="x", padx=20, pady=5)
        self.history_slider = ctk.CTkSlider(self.slider_frame, from_=0, to=1, number_of_steps=1, command=self._on_slider_move)
        self.history_slider.pack(side="left", fill="x", expand=True)
        self.version_info = ctk.CTkLabel(self.slider_frame, width=120)
        self.version_info.pack(side="right", padx=10)

        # History button for timetracking (hidden by default, shown only on TT note)
        self.tt_history_btn = ctk.CTkButton(
            self.slider_frame,
            width=100,
            height=28,
            fg_color=CLR_BTN_TT_HISTORY,
            hover_color=CLR_BTN_TT_HISTORY_HOVER,
            command=self.open_summary_history
        )

        self._setup_markdown_tags()

    def _setup_markdown_tags(self):
        tb = self.editor._textbox
        self.editor.tag_config("h1", foreground="#569CD6", underline=True)
        self.editor.tag_config("bold", foreground="#CE9178")
        self.editor.tag_config("list", foreground="#B5CEA8")
        self.editor.tag_config("timestamp", foreground="#A0A0A0")
        self.editor.tag_config("url", foreground="#4DA6FF", underline=True)
        self.editor.tag_config("search_match", background="#FFFF00", foreground="#000000")
        self.editor.tag_config("underline", underline=True)
        self.editor.tag_config("strikethrough", overstrike=True)
        tb.tag_config("bold_weight", font=("Consolas", 16, "bold"))
        # elide tags -- used to hide syntax markers for __, ~~, +++, and [color]
        tb.tag_config("color_hidden", elide=True)
        tb.tag_config("fmt_hidden", elide=True)
        for key, hex_color in FORMAT_COLORS:
            self.editor.tag_config("color_" + key, foreground=hex_color)
        tb.tag_bind("url", "<Button-1>", self.open_url)
        tb.tag_bind("url", "<Enter>", lambda e: tb.configure(cursor="hand2"))
        tb.tag_bind("url", "<Leave>", lambda e: tb.configure(cursor="xterm"))
        self.editor.bind("<KeyRelease>", self.on_key_release)
        self.editor.bind("<Control-t>", self.insert_timestamp)
        self.editor.bind("<Control-b>", lambda e: self._apply_format("+++", "+++") or "break")
        tb.bind("<<Undo>>", self._undo)
        tb.bind("<<Redo>>", self._redo)
        tb.bind("<MouseWheel>", lambda e: self.apply_markdown())
        tb.bind("<Button-3>", self._show_context_menu)

    # ==========================================
    # LOGIC & EVENTS
    # ==========================================
    @property
    def _s(self) -> dict:
        return STR_TABLE[self.lang]

    def get_str(self, key):
        return self._s.get(key, "")

    def update_ui_texts(self):
        s = self._s
        self.title(s["title"])
        self.new_btn.configure(text=s["new"])
        self.lang_btn.configure(text=s["lang_btn"])
        self.hist_label.configure(text=s["history_label"])
        if not self._viewing_history:
            self.version_info.configure(text=s["live"])
        self.tt_history_btn.configure(text=s["history_btn"])
        self.menubar.entryconfig(self._menu_file_idx, label=s["menu_file_label"])
        self.menubar.entryconfig(self._menu_help_idx, label=s["menu_help_label"])
        self.file_menu.delete(0, "end")
        self.file_menu.add_command(label=s["export"], command=self.export_notes)
        self.file_menu.add_command(label=s["import"], command=self.import_notes)
        self._build_help_menu()
        self.update_delete_button_state()

    def _on_search_key(self, event):
        self.refresh_sidebar()
        self.apply_markdown(full_scan=True)

    def focus_search(self, event=None):
        self.search_bar.focus_set()
        self.search_bar.select_range(0, 'end')
        self.search_bar.icursor('end')
        return "break"

    def manual_save(self, event=None):
        if self.current_note_id:
            self.force_save()
            self.show_save_popup()
            self.update_stats()
        return "break"

    def show_save_popup(self):
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-alpha", 0.7, "-topmost", True)
        lbl = ctk.CTkLabel(popup, text=self.get_str("saved"), text_color="#4DA6FF", font=("Segoe UI", 13, "bold"))
        lbl.pack(padx=10, pady=5)
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (popup.winfo_width() // 2)
        y = self.winfo_y() + 60
        popup.geometry(f"+{x}+{y}")
        self.after(2000, popup.destroy)

    def open_url(self, event):
        tb = self.editor._textbox
        try:
            index = tb.index(f"@{event.x},{event.y}")
            ranges = tb.tag_ranges("url")
            for i in range(0, len(ranges), 2):
                if tb.compare(ranges[i], "<=", index) and tb.compare(index, "<=", ranges[i+1]):
                    url = self.editor.get(ranges[i], ranges[i+1])
                    if not url.startswith(('http://', 'https://')): url = 'https://' + url
                    webbrowser.open(url)
                    break
        except Exception as e:
            log.warning("open_url error: %s", e)

    def _editor_text(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def _title_from_entry(self) -> str:
        return (self.title_entry.get().strip() or self.get_str("new_note_default"))[:self.TITLE_MAX_LEN]

    def _is_tt_note(self) -> bool:
        return self.current_note_id is not None and self.current_note_id == self._tt_id

    # ------------------------------------------------------------------
    # History slider
    # ------------------------------------------------------------------
    def _on_slider_move(self, val):
        if not self.current_note_id:
            return
        self._ensure_history_snapshots_loaded()
        if not self.history_snapshots:
            return
        idx = int(round(val))
        self.is_loading = True
        try:
            if idx >= len(self.history_snapshots):
                self.version_info.configure(text=self.get_str("live"), text_color=CLR_VERSION_LIVE)
                self.vault.flush()
                res = self.vault.get_note(self.current_note_id)
                if res:
                    self._update_editor_silently(res[1] or "")
                self._viewing_history = False
            else:
                ts, content = self.history_snapshots[idx]
                self.version_info.configure(text=ts, text_color=CLR_VERSION_OLD)
                self._update_editor_silently(content)
                self._viewing_history = True
        finally:
            self.is_loading = False

    def _update_editor_silently(self, content):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.editor._textbox.edit_reset()
        self.apply_markdown(full_scan=True)
        self.update_stats()
        self._saved_content = content

    def _update_history_data(self):
        """Slider range from the cached count, parked on Live."""
        self.history_snapshots = []   # lazy: loaded on first slider touch
        count = self._history_count
        steps = max(count, 1)
        self.history_slider.configure(from_=0, to=steps, number_of_steps=steps)
        self.history_slider.set(steps)
        self.version_info.configure(text=self.get_str("live"), text_color=CLR_VERSION_LIVE)

    def _ensure_history_snapshots_loaded(self):
        """Load full snapshot content only when the slider is actually moved."""
        if not self.history_snapshots and self.current_note_id:
            self.vault.flush()
            self.history_snapshots = self.vault.get_history(self.current_note_id)

    # ------------------------------------------------------------------
    # Editing, undo, saving
    # ------------------------------------------------------------------
    def on_key_release(self, e):
        if self.is_loading or e.keysym in ("Control_L", "Control_R"): return
        self._on_edited()

    def _on_edited(self):
        """Debounced follow-ups of any text change: formatting, auto-save, TT totals."""
        self._debounce('_after_id_format', self.FORMAT_DELAY_MS, self.apply_markdown)
        self._debounce('_after_id_save', self.SAVE_DELAY_MS, self.auto_save)
        self.update_stats()
        if self._is_tt_note():
            self._debounce('_after_id_totals', self.TOTALS_DELAY_MS, self._refresh_tt_totals)

    def _debounce(self, attr: str, delay_ms: int, callback):
        pending = getattr(self, attr)
        if pending:
            self.after_cancel(pending)
        setattr(self, attr, self.after(delay_ms, callback))

    def _undo(self, event=None):
        self._step_edit_history(undo=True)
        return "break"

    def _redo(self, event=None):
        self._step_edit_history(undo=False)
        return "break"

    def _step_edit_history(self, undo: bool):
        """
        One undo/redo step. In the Timetracking note the date-line totals live
        in undo groups of their own; they are stepped over, so undo lands on the
        previous real edit instead of flipping totals back and forth.
        """
        tb = self.editor._textbox
        step, back = (tb.edit_undo, tb.edit_redo) if undo else (tb.edit_redo, tb.edit_undo)
        norm = self._tt_engine.strip_totals if self._is_tt_note() else (lambda text: text)

        def try_step(fn) -> bool:
            try:
                fn()
                return True
            except tk.TclError:  # nothing left to undo/redo
                return False

        before = norm(self._editor_text())
        changed = False
        while try_step(step):
            if norm(self._editor_text()) != before:
                changed = True
                break
        if changed and not undo:
            # Redo: take the totals groups that followed this edit along, stop before the next edit
            while True:
                current = norm(self._editor_text())
                if not try_step(step):
                    break
                if norm(self._editor_text()) != current:
                    try_step(back)
                    break
        tb.see("insert")
        self.apply_markdown(full_scan=True)
        self._on_edited()

    def _replace_as_one_step(self, start: str, end: str, text: str):
        """Replace a range as a single undo step; plain delete+insert undoes in two steps
        and leaves the range empty after the first."""
        tb = self.editor._textbox
        tb.edit_separator()
        tb.configure(autoseparators=False)
        try:
            tb.delete(start, end)
            tb.insert(start, text)
        finally:
            tb.configure(autoseparators=True)
            tb.edit_separator()

    def _refresh_tt_totals(self):
        """Update the hour totals on the Timetracking note's date-marker lines, line by line,
        in an undo group of their own (see _step_edit_history)."""
        self._after_id_totals = None
        if not self._is_tt_note() or self.is_loading:
            return
        updates = self._tt_engine.totals_updates(self._editor_text())
        if not updates:
            return
        tb = self.editor._textbox
        cursor = tb.index("insert")
        cursor_line = int(cursor.split(".")[0])
        tb.edit_separator()
        tb.configure(autoseparators=False)
        try:
            for idx, new_line in updates:
                line = idx + 1
                tb.delete(f"{line}.0", f"{line}.end")
                tb.insert(f"{line}.0", new_line)
                if line == cursor_line:
                    tb.mark_set("insert", cursor)
        finally:
            tb.configure(autoseparators=True)
            tb.edit_separator()
        self.apply_markdown()

    def auto_save(self):
        self._after_id_save = None
        self._save(with_history=True)

    def force_save(self):
        """Always writes, as on note switch, Ctrl+S and close."""
        self._save(with_history=False, always=True)

    def _save(self, with_history: bool, always: bool = False):
        if not self.current_note_id or self.is_loading: return
        content = self._editor_text()
        new_title = self._title_from_entry()
        title_changed = new_title != self.current_title_cache
        if not always and not title_changed and content == self._saved_content:
            return

        restoring = self._viewing_history
        if restoring:
            # The shown older version is about to become the live text
            self._archive_live_version()
            self._viewing_history = False

        if self._is_tt_note():
            self._sync_tt_archive(content)

        add_history = with_history and (
            self._last_history_content is None
            or changed_chars(self._last_history_content, content) >= self.HISTORY_MIN_CHANGE)
        self.vault.save_note(self.current_note_id, new_title, content, add_history)
        if add_history:
            self._last_history_content = content
            self._history_count += 1
        self.current_title_cache = new_title
        self._saved_content = content
        if with_history or restoring:
            self._update_history_data()
        if not with_history:
            return

        # Refresh sidebar if title changed or note moved in order
        unpinned = self._sidebar_order[self._sidebar_pinned_count:]
        if title_changed or not unpinned or unpinned[0] != self.current_note_id:
            self.vault.flush()
            self.refresh_sidebar()

    def _archive_live_version(self):
        """Keep the current live text reachable in the slider before an older version replaces it."""
        self.vault.flush()
        res = self.vault.get_note(self.current_note_id)
        live = res[1] if res else None
        if live and live != self._last_history_content:
            self.vault.add_history(self.current_note_id, live)
            self._last_history_content = live
            self._history_count += 1

    def load_note(self, nid):
        if self.current_note_id is not None: self.force_save()
        self.vault.flush()
        res = self.vault.get_note(nid)
        if not res:
            return
        self.is_loading = True
        try:
            title, content, is_deleted = res
            content = content or ""
            self.current_note_id = nid
            self.current_title_cache = title
            self.title_entry.delete(0, "end")
            if title and title != self.get_str("new_note_default"): self.title_entry.insert(0, title)

            if self._is_tt_note():
                self.tt_history_btn.pack(side="right", padx=(10, 0))
                self._tt_prev_entries = self._tt_engine.parse_entries(content)[0]
            else:
                self.tt_history_btn.pack_forget()

            self.editor.configure(state="normal")
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", content)
            # A fresh undo stack: undo must never reach into the previously open note
            self.editor._textbox.edit_reset()
            self.editor._textbox.see("1.0")
            self.apply_markdown(full_scan=True)
            self.update_stats()
            self.update_delete_button_state(is_deleted)

            self._saved_content = content
            self._last_history_content = self.vault.get_last_history_content(nid)
            self._history_count = self.vault.get_history_count(nid)
            self._viewing_history = False
            self._update_history_data()
        finally:
            self.is_loading = False

    def _clear_editor(self):
        self.current_note_id = None
        self.current_title_cache = ""
        self.title_entry.delete(0, "end")
        self.editor.delete("1.0", "end")
        self.editor._textbox.edit_reset()
        self.tt_history_btn.pack_forget()
        self._saved_content = ""
        self._last_history_content = None
        self._history_count = 0
        self._viewing_history = False
        self._update_history_data()
        self.update_stats()

    def handle_delete_action(self):
        if not self.current_note_id: return
        res = self.vault.get_note(self.current_note_id)
        if res and res[2] == 1:
            if messagebox.askyesno(self.get_str("final_del"), self.get_str("confirm_del")):
                self.vault.delete_note_hard(self.current_note_id)
                self._clear_editor()
        else:
            self.vault.delete_note_soft(self.current_note_id)
        self.refresh_sidebar()
        self.update_delete_button_state()

    def restore_note(self):
        if not self.current_note_id: return
        self.vault.restore_note(self.current_note_id)
        self._set_archive_view(False)
        self.update_delete_button_state()

    def insert_timestamp(self, e=None):
        if self._is_tt_note():
            stamp = datetime.now().strftime("--- %d.%m.%Y ---")
        else:
            stamp = datetime.now().strftime("--- %d.%m.%Y, %H:%M ---")
        self.editor.insert(tk.INSERT, f"\n{stamp}\n")
        self.apply_markdown(full_scan=True)
        self.auto_save()
        return "break"

    def refresh_sidebar(self):
        rows = self.vault.fetch_sidebar_notes(self.search_bar.get(), self.show_archived)
        new_data = {nid: (title, pinned, is_del) for nid, title, pinned, is_del in rows}
        new_order = [nid for nid, *_ in rows]

        # Remove widgets no longer in results
        removed = [nid for nid in list(self._sidebar_cache) if nid not in new_data]
        for nid in removed:
            self._sidebar_cache[nid].destroy()
            del self._sidebar_cache[nid]

        # Update or create widgets
        for nid, title, pinned, is_del in rows:
            if nid in self._sidebar_cache:
                self._sidebar_cache[nid].update_data(title, pinned)
            else:
                btn = NoteButton(self.note_list_frame, nid, title, pinned, is_del,
                                 self.load_note, self.toggle_pin, self.get_str)
                self._sidebar_cache[nid] = btn

        # Reorder if the visible sequence changed
        if new_order != self._sidebar_order:
            for nid in new_order:
                self._sidebar_cache[nid].pack_forget()
            for nid in new_order:
                self._sidebar_cache[nid].pack(fill="x", pady=2)

        self._sidebar_order = new_order
        self._sidebar_pinned_count = sum(1 for nid in new_order if new_data[nid][1])

    def update_delete_button_state(self, is_deleted=None):
        if not self.current_note_id:
            self.del_btn.configure(text=self.get_str("del"), fg_color=CLR_BTN_DELETE)
            self.restore_btn.pack_forget()
            return
        if is_deleted is None:
            res = self.vault.get_note(self.current_note_id)
            is_deleted = res[2] if res else 0
        if is_deleted == 1:
            self.del_btn.configure(text=self.get_str("final_del"), fg_color=CLR_BTN_DELETE_HARD)
            self.restore_btn.pack(side="right", padx=(0, 10))
            self.restore_btn.configure(text=self.get_str("restore"))
        else:
            self.del_btn.configure(text=self.get_str("del"), fg_color=CLR_BTN_DELETE)
            self.restore_btn.pack_forget()

    def apply_markdown(self, full_scan=False):
        tb = self.editor._textbox
        try:
            if full_scan:
                start_idx, end_idx = "1.0", "end"
            else:
                start_idx = tb.index(f"{tb.index('@0,0')} linestart -5 lines")
                if tb.compare(start_idx, "<", "1.0"): start_idx = "1.0"
                end_idx = tb.index(f"{tb.index(f'@0,{self.editor.winfo_height()}')} lineend +5 lines")

            for tag in self._MARKDOWN_TAGS:
                self.editor.tag_remove(tag, start_idx, end_idx)
            tb.tag_remove("bold_weight", start_idx, end_idx)
            self.editor.tag_remove("color_hidden", start_idx, end_idx)
            self.editor.tag_remove("fmt_hidden",   start_idx, end_idx)
            content = self.editor.get(start_idx, end_idx)

            # Simple full-span rules (markers are part of the style, no elide needed)
            simple_rules = [
                ("h1",        r"^# .*",                                          re.M),
                ("bold",      r"\*\*.*?\*\*",                                    0),
                ("list",      r"^[ \t]*[-*+] .*",                                re.M),
                ("timestamp", r"--- \d{2}\.\d{2}\.\d{4}(?:, \d{2}:\d{2})? ---", 0),
                ("url",       r"\b(?:https?://)?(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?\b", 0),
            ]
            for tag, pattern, flag in simple_rules:
                try:
                    for m in re.finditer(pattern, content, flag):
                        self.editor.tag_add(tag, f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")
                except Exception as e:
                    log.debug("apply_markdown simple_rule error tag=%s: %s", tag, e)

            # Inner-text rules: apply style to group(1), elide the markers
            # Each tuple: (tag, compiled_regex)
            inner_rules = [
                ("underline",     re.compile(r'__(.*?)__',         re.DOTALL)),
                ("strikethrough", re.compile(r'~~(.*?)~~',         re.DOTALL)),
                ("bold_weight",   re.compile(r'\+\+\+(.*?)\+\+\+', re.DOTALL)),
            ]
            for tag, rx in inner_rules:
                tb_ref = tb if tag == "bold_weight" else self.editor
                try:
                    for m in rx.finditer(content):
                        inner_s = m.start(1)
                        inner_e = m.end(1)
                        tb_ref.tag_add(tag,          f"{start_idx} + {inner_s} chars", f"{start_idx} + {inner_e} chars")
                        self.editor.tag_add("fmt_hidden", f"{start_idx} + {m.start()} chars", f"{start_idx} + {inner_s} chars")
                        self.editor.tag_add("fmt_hidden", f"{start_idx} + {inner_e} chars",   f"{start_idx} + {m.end()} chars")
                except Exception as e:
                    log.debug("apply_markdown inner_rule error tag=%s: %s", tag, e)

            # Colour tags: color inner text only, hide the [tag]...[/tag] markers
            for m in self._COLOR_TAG_RE.finditer(content):
                tag_name = "color_" + m.group(1)
                if tag_name not in self._COLOR_TAGS:
                    continue
                inner_start = m.start(2)
                inner_end   = m.end(2)
                self.editor.tag_add(tag_name,      f"{start_idx} + {inner_start} chars", f"{start_idx} + {inner_end} chars")
                self.editor.tag_add("color_hidden", f"{start_idx} + {m.start()} chars",  f"{start_idx} + {inner_start} chars")
                self.editor.tag_add("color_hidden", f"{start_idx} + {inner_end} chars",  f"{start_idx} + {m.end()} chars")

            search_query = self.search_bar.get()
            if search_query:
                for m in re.finditer(re.escape(search_query), content, re.I):
                    self.editor.tag_add("search_match", f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")
        except Exception as e:
            log.debug("apply_markdown error: %s", e)

    def create_new_note(self):
        nid = self.vault.create_note(self.get_str("new_note_default"))
        self.search_bar.delete(0, "end")
        self.refresh_sidebar()
        if nid is not None:
            self.load_note(nid)
        self.title_entry.focus_set()

    def toggle_pin(self, nid):
        self.vault.toggle_pin(nid)
        self.refresh_sidebar()

    def toggle_archive_view(self):
        self._set_archive_view(not self.show_archived)

    def _set_archive_view(self, archived: bool):
        self.show_archived = archived
        self.archive_toggle_btn.configure(fg_color=CLR_ARCHIVE_ACTIVE if archived else CLR_ARCHIVE_IDLE)
        self.refresh_sidebar()

    def export_notes(self):
        path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP Archive", "*.zip")])
        if not path: return
        self._save(with_history=False)  # pending edits, without bumping an unchanged note
        self.vault.flush()
        used = set()
        with zipfile.ZipFile(path, 'w') as z:
            for t, ct in self.vault.get_export_data():
                z.writestr(safe_filename(t, used), ct or "")

    def import_notes(self):
        path = filedialog.askopenfilename(filetypes=[("Text/ZIP", "*.txt *.zip")])
        if not path: return
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path, 'r') as z:
                for info in z.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".txt"):
                        continue
                    content = z.read(info).decode('utf-8-sig', errors='ignore')
                    self.vault.create_note(PurePosixPath(info.filename).stem, content)
        else:
            with open(path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                self.vault.create_note(Path(path).stem, f.read())
        self.refresh_sidebar()

    def toggle_language(self):
        self.lang = "DE" if self.lang == "EN" else "EN"
        self.vault.set_setting('lang', self.lang)
        self.update_ui_texts()
        self.refresh_sidebar()
        if self._history_window_open():
            self._hist_apply_texts()
            self._update_history_display()

    def update_stats(self):
        text = self._editor_text()
        self.status_bar.configure(text=self.get_str("stats").format(len(text.split()), len(text)))

    def _build_help_menu(self):
        s = self._s
        m = self.help_menu
        m.delete(0, "end")
        m.add_command(label=s["help_shortcuts"], state="disabled")
        for label, key in s["help_shortcut_items"]:
            m.add_command(label=f"{label:<22}{key}", state="disabled")
        m.add_separator()
        m.add_command(label=s["help_syntax"], state="disabled")
        for label, syntax_str in s["help_syntax_items"]:
            m.add_command(label=f"{label:<22}{syntax_str}", state="disabled")

    def _on_screen(self, x: int, y: int) -> bool:
        try:
            return monitor_at(x, y)
        except Exception:
            # No Win32: Tk only knows the primary screen
            return 0 <= x < self.winfo_screenwidth() and 0 <= y < self.winfo_screenheight()

    def _on_app_close(self):
        """Flush pending edits before exit -- no keystrokes lost."""
        try:
            for after_id in (self._after_id_save, self._after_id_format, self._after_id_totals):
                if after_id:
                    self.after_cancel(after_id)
            self.force_save()
            self.vault.set_setting("window_geometry", self.geometry())
            self.vault.close()
        except Exception as e:
            log.error("Shutdown error: %s", e)
        finally:
            self.destroy()

    def load_latest_or_empty(self):
        nid = self.vault.get_latest_active_id()
        if nid: self.load_note(nid)

    # ==========================================
    # RIGHT-CLICK CONTEXT MENU & INLINE FORMATTING
    # ==========================================
    def _show_context_menu(self, event):
        s = self._s
        tb = self.editor._textbox
        style = dict(tearoff=0, bg="#2b2b2b", fg="#d4d4d4", activebackground="#3a3a3a",
                     activeforeground="#ffffff", bd=0, relief="flat")
        menu = tk.Menu(self, **style)

        # Standard edit actions
        menu.add_command(label=s["ctx_cut"],   command=lambda: tb.event_generate("<<Cut>>"))
        menu.add_command(label=s["ctx_copy"],  command=lambda: tb.event_generate("<<Copy>>"))
        menu.add_command(label=s["ctx_paste"], command=lambda: tb.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label=s["ctx_bold"],      command=lambda: self._apply_format("**", "**"))
        menu.add_command(label=s["ctx_underline"], command=lambda: self._apply_format("__", "__"))
        menu.add_command(label=s["ctx_strike"],    command=lambda: self._apply_format("~~", "~~"))
        menu.add_separator()
        # Colour submenu
        color_menu = tk.Menu(menu, **style)
        for key, _ in FORMAT_COLORS:
            color_menu.add_command(label=s["color_" + key], command=lambda k=key: self._apply_color(k))
        color_menu.add_separator()
        color_menu.add_command(label=s["ctx_remove_color"], command=self._remove_color)
        menu.add_cascade(label=s["ctx_color"], menu=color_menu)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _selection(self):
        """(start, end, text) of the editor selection, or None."""
        tb = self.editor._textbox
        try:
            sel_start = tb.index("sel.first")
            sel_end   = tb.index("sel.last")
        except tk.TclError:
            return None  # nothing selected
        selected = tb.get(sel_start, sel_end)
        return (sel_start, sel_end, selected) if selected else None

    def _replace_selection(self, sel, new_text):
        self._replace_as_one_step(sel[0], sel[1], new_text)
        self.apply_markdown(full_scan=True)
        self._on_edited()

    def _apply_format(self, open_tag: str, close_tag: str):
        """Wrap or unwrap selected text with open_tag/close_tag markers."""
        sel = self._selection()
        if not sel:
            return
        selected = sel[2]
        # Toggle: strip if already wrapped
        if selected.startswith(open_tag) and selected.endswith(close_tag) and len(selected) > len(open_tag) + len(close_tag):
            new_text = selected[len(open_tag):-len(close_tag)]
        else:
            new_text = f"{open_tag}{selected}{close_tag}"
        self._replace_selection(sel, new_text)

    def _apply_color(self, tag_key: str):
        """Wrap selected text in [tag_key]...[/tag_key]. Replaces existing color if present."""
        sel = self._selection()
        if not sel:
            return
        m = self._COLOR_TAG_RE.fullmatch(sel[2])
        inner = m.group(2) if m else sel[2]
        self._replace_selection(sel, f"[{tag_key}]{inner}[/{tag_key}]")

    def _remove_color(self):
        """Strip all [color]...[/color] wrappers from selection."""
        sel = self._selection()
        if not sel:
            return
        new_text = self._COLOR_TAG_RE.sub(r'\2', sel[2])
        if new_text != sel[2]:
            self._replace_selection(sel, new_text)

    # ==========================================
    # TIMETRACKING
    # ==========================================
    def _ensure_special_notes(self):
        """Bind the Timetracking notes by id, so renaming, archiving or importing a
        same-named note never swaps them. First run: adopt the note found by
        title, as earlier versions did, else create it."""
        self._tt_id = self._resolve_special_note("tt_note_id", self.TITLE_TT, "")
        self._clients_id = self._resolve_special_note("tt_clients_note_id", self.TITLE_CLIENTS,
                                                      self.get_str("clients_default"))

    def _resolve_special_note(self, setting_key: str, title: str, default_content: str):
        stored = self.vault.get_setting(setting_key, "")
        if stored.isdigit() and self.vault.get_note(int(stored)):
            return int(stored)
        nid = self.vault.find_active_note_id(title)
        if nid is None:
            nid = self.vault.create_note(title, default_content)
        if nid is not None:
            self.vault.set_setting(setting_key, str(nid))
        return nid

    def _note_text(self, nid) -> str:
        """Current text of a note: the editor if it is open (may be unsaved), else the database."""
        if nid is None:
            return ""
        if nid == self.current_note_id:
            return self._editor_text()
        self.vault.flush()
        res = self.vault.get_note(nid)
        return (res[1] or "") if res else ""

    def _archive_rows(self):
        """[(date, content, entries_json)] with the 'dd/mm/yyyy' keys parsed."""
        rows = []
        for key, content, entries_json in self.vault.get_summary_rows():
            try:
                rows.append((datetime.strptime(key, '%d/%m/%Y').date(), content, entries_json))
            except (TypeError, ValueError):
                log.warning("Skipping timetracking archive row with unreadable date %r", key)
        return rows

    def _sync_tt_archive(self, tt_content: str):
        """Store every day's entries whose content changed, past days included, from the text being saved."""
        digest = hashlib.md5(tt_content.encode('utf-8')).hexdigest()
        if digest == self._last_tt_hash:
            return
        self._last_tt_hash = digest
        try:
            engine = self._tt_engine
            if self._archive_known is None:
                self.vault.flush()
                self._archive_known = {d: js for d, _, js in self._archive_rows()}
            entries, _ = engine.parse_entries(tt_content)
            updates = snapshot_updates(entries, self._archive_known)
            moved = [d for d in moved_away_days(self._tt_prev_entries, entries)
                     if self._archive_known.get(d) not in (None, '[]')]
            self._tt_prev_entries = entries
            rows = []
            if updates:
                client_map = engine.parse_clients(self._note_text(self._clients_id))
                use_sections = engine.uses_sections(tt_content)
                for d, entries_json, day_entries in updates:
                    # The rendered text keeps the archive readable for older builds
                    text = engine.render_report(self._period_label('daily', d, d), day_entries, client_map,
                                                self._s, use_sections)
                    rows.append((d.strftime('%d/%m/%Y'), text, entries_json))
                    self._archive_known[d] = entries_json
            for d in moved:
                rows.append((d.strftime('%d/%m/%Y'), self._s['no_history'], '[]'))
                self._archive_known[d] = '[]'
            if rows:
                self.vault.save_summary_snapshots(rows)
        except Exception as e:
            log.error("_sync_tt_archive error: %s", e)
        if self._history_window_open():
            self._update_history_display()

    def _period_label(self, mode: str, start: date, end: date) -> str:
        s = self._s
        if mode == 'daily':
            return f"{s['weekdays'][start.weekday()]} {start:%d.%m.%Y}"
        if mode == 'weekly':
            return s['week_label'].format(week=start.isocalendar()[1], start=f"{start:%d.%m.}", end=f"{end:%d.%m.%Y}")
        return f"{s['months'][start.month - 1]} {start.year}"

    def _tt_period_report(self, mode: str, start: date, end: date):
        """(text, csv rows) for a period: note data plus archived days the note no longer holds."""
        s = self._s
        engine = self._tt_engine
        tt_content = self._note_text(self._tt_id)
        client_map = engine.parse_clients(self._note_text(self._clients_id))
        live, warnings = engine.parse_entries(tt_content)
        self.vault.flush()
        archive = {d: (text, entries_from_json(d, js)) for d, text, js in self._archive_rows()}
        entries, archived, legacy = select_period_entries(live, archive, start, end)

        if not entries:
            if mode == 'daily' and legacy:
                return archive[legacy[0]][0] or s['no_history'], []
            if not legacy:
                return s['no_history'], []

        def day_list(days):
            return ', '.join(f"{d:%d.%m.%Y}" for d in days)

        footer = []
        if archived:
            footer.append(s['sum_archived'].format(day_list(archived)))
        if legacy:
            footer.append(s['sum_legacy'].format(day_list(legacy)))
        use_sections = engine.uses_sections(tt_content) or any(e['section'] for e in entries)
        text = engine.render_report(self._period_label(mode, start, end), entries, client_map, s, use_sections,
                                    per_day=(mode != 'daily'), warnings=warnings, footer=footer)
        return text, engine.csv_rows(entries, client_map)

    # ==========================================
    # SUMMARY HISTORY WINDOW
    # ==========================================
    def _history_window_open(self) -> bool:
        return bool(self._history_window and self._history_window.winfo_exists())

    def open_summary_history(self):
        """Open the summary history window."""
        if self._history_window_open():
            self._history_window.lift()
            self._history_window.focus_force()
            return

        win = self._history_window = tk.Toplevel(self)
        win.geometry("900x700")
        win.minsize(760, 500)
        win.configure(bg="#1a1a1a")
        try:
            icon_path = resource_path('app_icon.ico')
            if icon_path.exists():
                win.iconbitmap(str(icon_path))
        except Exception as e:
            log.debug("History window icon error: %s", e)

        # History window state
        self._hist_mode = 'daily'
        self._hist_anchor = date.today()
        self._hist_range = (self._hist_anchor, self._hist_anchor)
        self._hist_text = ""
        self._hist_rows = []

        # Top navigation bar
        nav_frame = ctk.CTkFrame(win, fg_color="#1e1e2e", height=50)
        nav_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(nav_frame, text="◀◀", width=35, fg_color="gray30",
                      command=lambda: self._navigate_history(-1)).pack(side="left", padx=(20, 2))
        ctk.CTkButton(nav_frame, text="▶▶", width=35, fg_color="gray30",
                      command=lambda: self._navigate_history(1)).pack(side="left", padx=2)
        self._hist_mode_btn = ctk.CTkSegmentedButton(nav_frame, command=self._on_hist_mode_pick)
        self._hist_mode_btn.pack(side="left", padx=(15, 5))
        self._hist_date_label = ctk.CTkLabel(nav_frame, font=("Segoe UI", 10))
        self._hist_date_label.pack(side="left", padx=(15, 5))
        self._hist_date_entry = ctk.CTkEntry(nav_frame, width=100, font=("Segoe UI", 10))
        self._hist_date_entry.pack(side="left", padx=5)
        self._hist_date_entry.bind("<Return>", self._hist_jump_to_date)
        self._hist_go_btn = ctk.CTkButton(nav_frame, width=40, fg_color="gray30", command=self._hist_jump_to_date)
        self._hist_go_btn.pack(side="left", padx=2)
        self._hist_period_label = ctk.CTkLabel(nav_frame, text="", font=("Segoe UI", 10), text_color="gray")
        self._hist_period_label.pack(side="right", padx=10)

        # Content area
        self._hist_content = ctk.CTkTextbox(win, font=("Consolas", 14), fg_color="#121212", wrap="none")
        self._hist_content.pack(fill="both", expand=True, padx=10, pady=10)
        self._hist_content.configure(state="disabled")

        # Bottom bar
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self._hist_copy_btn = ctk.CTkButton(bottom, width=110, fg_color="gray30", command=self._hist_copy)
        self._hist_copy_btn.pack(side="left")
        self._hist_csv_btn = ctk.CTkButton(bottom, width=130, fg_color="gray30", command=self._hist_export_csv)
        self._hist_csv_btn.pack(side="left", padx=(10, 0))
        self._hist_status = ctk.CTkLabel(bottom, text="", text_color="gray")
        self._hist_status.pack(side="left", padx=15)
        self._hist_close_btn = ctk.CTkButton(bottom, width=110, fg_color="gray30", command=self._on_history_close)
        self._hist_close_btn.pack(side="right")

        win.protocol("WM_DELETE_WINDOW", self._on_history_close)
        self._hist_apply_texts()
        self._update_history_display()

    def _hist_apply_texts(self):
        s = self._s
        self._history_window.title(f"{s['hist_title']} - {s['title']}")
        mode_labels = [s[m] for m in HIST_MODES]
        self._hist_mode_btn.configure(values=mode_labels)
        self._hist_mode_btn.set(mode_labels[HIST_MODES.index(self._hist_mode)])
        self._hist_date_label.configure(text=s['hist_date'])
        self._hist_go_btn.configure(text=s['hist_go'])
        self._hist_copy_btn.configure(text=s['hist_copy'])
        self._hist_csv_btn.configure(text=s['hist_csv'])
        self._hist_close_btn.configure(text=s['hist_close'])

    def _on_history_close(self):
        """Clean up when history window is closed."""
        if self._history_window:
            self._history_window.destroy()
            self._history_window = None

    def _on_hist_mode_pick(self, label):
        mode_labels = [self._s[m] for m in HIST_MODES]
        if label in mode_labels:
            self._set_history_mode(HIST_MODES[mode_labels.index(label)])

    def _set_history_mode(self, mode):
        """Set the history view mode (daily/weekly/monthly); the shown date stays in view."""
        self._hist_mode = mode
        self._hist_mode_btn.set(self._s[mode])
        self._update_history_display()

    def _navigate_history(self, direction):
        """One period back or forward from the one shown."""
        self._hist_anchor = shift_anchor(self._hist_mode, self._hist_anchor, direction)
        self._hist_date_entry.delete(0, "end")
        self._update_history_display()

    def _hist_jump_to_date(self, event=None):
        """Jump to the date in the date field, keeping the view mode."""
        m = re.fullmatch(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})', self._hist_date_entry.get().strip())
        try:
            if not m:
                raise ValueError
            self._hist_anchor = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            self._hist_status.configure(text=self.get_str("hist_bad_date"))
            return
        self._update_history_display()

    def _update_history_display(self):
        """Render the period that contains the anchor date in the current mode."""
        start, end = period_range(self._hist_mode, self._hist_anchor)
        self._hist_range = (start, end)
        self._hist_period_label.configure(text=self._period_label(self._hist_mode, start, end))
        self._hist_status.configure(text="")
        text, rows = self._tt_period_report(self._hist_mode, start, end)
        self._hist_rows = rows
        if text == self._hist_text:
            return
        self._hist_text = text
        tb = self._hist_content._textbox
        scroll = tb.yview()[0]
        self._hist_content.configure(state="normal")
        self._hist_content.delete("1.0", "end")
        self._hist_content.insert("1.0", text)
        self._hist_content.configure(state="disabled")
        tb.yview_moveto(scroll)

    def _hist_copy(self):
        self._history_window.clipboard_clear()
        self._history_window.clipboard_append(self._hist_text)
        self._hist_status.configure(text=self.get_str("hist_copied"))

    def _hist_export_csv(self):
        if not self._hist_rows:
            self._hist_status.configure(text=self.get_str("hist_csv_empty"))
            return
        start, end = self._hist_range
        path = filedialog.asksaveasfilename(
            parent=self._history_window, defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"timetracking_{start:%Y-%m-%d}_{end:%Y-%m-%d}.csv")
        if not path:
            return
        german = self.lang == "DE"  # Excel DE expects ; and a decimal comma
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(self._s['csv_header'])
            for d, section, client, prefix, ticket, hours, desc in self._hist_rows:
                hours_str = fmt_hours(hours)
                writer.writerow([f"{d:%d.%m.%Y}" if german else d.isoformat(), section, client, prefix, ticket,
                                 hours_str.replace('.', ',') if german else hours_str, desc])
        self._hist_status.configure(text=self.get_str("hist_csv_done").format(len(self._hist_rows)))


if __name__ == "__main__":
    app = HistoryNotesApp()
    app.mainloop()
