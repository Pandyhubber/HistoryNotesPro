import tkinter as tk
import customtkinter as ctk
import sqlite3
import zipfile
import re
import webbrowser
import sys
import ctypes
import logging
import threading
import queue
import hashlib
from pathlib import Path
from datetime import datetime, date, timedelta
from tkinter import messagebox, filedialog
import calendar

# ==========================================
# LOGGING SETUP
# ==========================================
def _setup_logging():
    if getattr(sys, 'frozen', False):
        log_dir = Path(sys.executable).parent
    else:
        log_dir = Path(__file__).resolve().parent
    log_path = log_dir / 'historynotespro.log'
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
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
        "restore": "Restore", "pin": "📌", "unpin": "✕", "live": "Live",
        "lang_btn": "Language: EN", "menu_file": "File", "export": "Export (.zip)", 
        "import": "Import (.txt/.zip)", "stats": "Words: {} | Chars: {}", 
        "confirm_del": "Delete note permanently?", "history_label": "History Version",
        "menu_file_label": "File", "saved": "Saved", "new_note_default": "New Note",
        "welcome_title": "Welcome!", "welcome_text": "This is your first note.\n\nYou can simply edit this text or click '+ New Note' above.",
        "history_btn": "📊 History", "daily": "Daily", "weekly": "Weekly", "monthly": "Monthly",
        "no_history": "No historical data available for this period."
    },
    "DE": {
        "title": "HistoryNotes PRO", "new": "+ Neue Notiz", "del": "Archivieren", "final_del": "Endgültig Löschen",
        "restore": "Wiederherstellen", "pin": "📌", "unpin": "✕", "live": "Live",
        "lang_btn": "Sprache: DE", "menu_file": "Datei", "export": "Export (.zip)", 
        "import": "Import (.txt/.zip)", "stats": "Wörter: {} | Zeichen: {}", 
        "confirm_del": "Notiz wirklich endgültig löschen?", "history_label": "Versionsverlauf",
        "menu_file_label": "Datei", "saved": "Gespeichert", "new_note_default": "Neue Notiz",
        "welcome_title": "Willkommen!", "welcome_text": "Dies ist deine erste Notiz.\n\nDu kannst diesen Text einfach löschen oder oben auf '+ Neue Notiz' klicken.",
        "history_btn": "📊 Verlauf", "daily": "Täglich", "weekly": "Wöchentlich", "monthly": "Monatlich",
        "no_history": "Keine historischen Daten für diesen Zeitraum verfügbar."
    }
}

# ==========================================
# 2. DATA ACCESS LAYER
# ==========================================
class NoteVault:
    """
    Thread-safe SQLite access.
    - WAL mode is set once on the main-thread read connection before the
      writer thread starts, so there is no lock contention on startup.
    - All writes are serialised through a queue served by a single writer
      thread; reads run on the caller (main) thread.
    """
    def __init__(self, db_path: Path):
        self._db_path = db_path
        # Open + configure the read connection first, while no writer exists yet
        self._rconn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
        self._rconn.execute("PRAGMA journal_mode=WAL")
        self._rconn.commit()
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
            sql, params, evt, box = item
            try:
                with wconn:
                    wconn.execute(sql, params)
                if box is not None:
                    box.append(None)
            except Exception as e:
                log.error("DB write error: %s | sql=%s params=%s", e, sql, params)
                if box is not None:
                    box.append(e)
            finally:
                if evt:
                    evt.set()

    def _write(self, sql: str, params: tuple = ()):
        """Fire-and-forget write."""
        self._write_queue.put((sql, params, None, None))

    def _write_sync(self, sql: str, params: tuple = ()):
        """Blocking write -- waits for completion, re-raises on error."""
        evt = threading.Event()
        box: list = []
        self._write_queue.put((sql, params, evt, box))
        evt.wait()
        if box and isinstance(box[0], Exception):
            raise box[0]

    def close(self):
        self._write_queue.put(None)
        self._writer_thread.join(timeout=3)
        self._rconn.close()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------
    def _setup_db(self):
        for sql in [
            'CREATE TABLE IF NOT EXISTS note_list (id INTEGER PRIMARY KEY, title TEXT, pinned INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0, last_content TEXT, last_updated TEXT)',
            'CREATE TABLE IF NOT EXISTS history (note_id INTEGER, content TEXT, timestamp TEXT)',
            'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)',
            'CREATE TABLE IF NOT EXISTS summary_history (date TEXT PRIMARY KEY, content TEXT, created_at TEXT)',
            'CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)',
        ]:
            self._write_sync(sql)
        if not self._rconn.execute("SELECT version FROM schema_version").fetchone():
            self._write_sync("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")
        if self._rconn.execute("SELECT COUNT(*) FROM note_list").fetchone()[0] == 0:
            lang = self.get_setting("lang", "EN")
            self.create_note(STR_TABLE[lang]["welcome_title"], STR_TABLE[lang]["welcome_text"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str) -> str:
        res = self._rconn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res[0] if res else default

    def set_setting(self, key: str, value: str):
        self._write("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    def fetch_sidebar_notes(self, search_term: str, show_archived: bool):
        f = 1 if show_archived else 0
        q = f"SELECT id, title, pinned, is_deleted FROM note_list WHERE is_deleted = {f}"
        p = []
        if search_term:
            q += " AND (LOWER(title) LIKE ? OR LOWER(last_content) LIKE ?)"
            p = [f'%{search_term}%', f'%{search_term}%']
        q += " ORDER BY pinned DESC, last_updated DESC"
        return self._rconn.execute(q, p).fetchall()

    def get_note(self, nid: int):
        return self._rconn.execute("SELECT title, last_content, is_deleted FROM note_list WHERE id = ?", (nid,)).fetchone()

    def get_history(self, nid: int):
        rows = self._rconn.execute("SELECT timestamp, content FROM history WHERE note_id = ? ORDER BY timestamp ASC", (nid,)).fetchall()
        return [(r[0][11:16] if 'T' in r[0] else r[0][:16], r[1]) for r in rows]

    def get_history_count(self, nid: int) -> int:
        """Lightweight count -- avoids fetching all content rows on every save."""
        row = self._rconn.execute("SELECT COUNT(*) FROM history WHERE note_id = ?", (nid,)).fetchone()
        return row[0] if row else 0

    def save_snapshot(self, nid: int, title: str, content: str, force_history: bool = False):
        now_str = datetime.now().isoformat()
        self._write("UPDATE note_list SET title = ?, last_content = ?, last_updated = ? WHERE id = ?",
                    (title, content, now_str, nid))
        if force_history:
            last = self._rconn.execute(
                "SELECT content FROM history WHERE note_id = ? ORDER BY timestamp DESC LIMIT 1", (nid,)
            ).fetchone()
            if not last or last[0] != content:
                self._write("INSERT INTO history (note_id, content, timestamp) VALUES (?, ?, ?)",
                            (nid, content, now_str))

    def create_note(self, title: str, content: str = "") -> int:
        """Synchronous insert so we can return the new id."""
        now_str = datetime.now().isoformat()
        evt = threading.Event()
        box: list = []
        def _do():
            try:
                conn = sqlite3.connect(str(self._db_path), timeout=30)
                with conn:
                    c = conn.cursor()
                    c.execute("INSERT INTO note_list (title, last_content, last_updated) VALUES (?, ?, ?)",
                              (title, content, now_str))
                    box.append(c.lastrowid)
                conn.close()
            except Exception as e:
                log.error("create_note error: %s", e)
                box.append(None)
            finally:
                evt.set()
        threading.Thread(target=_do, daemon=True).start()
        evt.wait()
        return box[0]

    def delete_note_soft(self, nid: int):
        self._write("UPDATE note_list SET is_deleted = 1, pinned = 0 WHERE id = ?", (nid,))

    def delete_note_hard(self, nid: int):
        self._write("DELETE FROM note_list WHERE id = ?", (nid,))
        self._write("DELETE FROM history WHERE note_id = ?", (nid,))

    def restore_note(self, nid: int):
        self._write("UPDATE note_list SET is_deleted = 0 WHERE id = ?", (nid,))

    def toggle_pin(self, nid: int):
        self._write("UPDATE note_list SET pinned = 1 - pinned WHERE id = ?", (nid,))

    def get_latest_active_id(self):
        row = self._rconn.execute(
            "SELECT id FROM note_list WHERE is_deleted = 0 ORDER BY pinned DESC, last_updated DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def get_export_data(self):
        return self._rconn.execute("SELECT title, last_content FROM note_list WHERE is_deleted = 0").fetchall()

    def get_note_by_title(self, title: str):
        row = self._rconn.execute(
            "SELECT id, last_content FROM note_list WHERE title = ? AND is_deleted = 0 LIMIT 1", (title,)
        ).fetchone()
        return row

    def update_note_content(self, nid: int, content: str):
        now_str = datetime.now().isoformat()
        self._write("UPDATE note_list SET last_content = ?, last_updated = ? WHERE id = ?",
                    (content, now_str, nid))

    # === Summary History ===
    def save_summary_snapshot(self, date_key: str, content: str):
        now_str = datetime.now().isoformat()
        self._write(
            "INSERT OR REPLACE INTO summary_history (date, content, created_at) VALUES (?, ?, ?)",
            (date_key, content, now_str)
        )

    def get_summary_snapshots(self, start_date: str = None, end_date: str = None):
        if start_date and end_date:
            return self._rconn.execute(
                "SELECT date, content FROM summary_history WHERE date >= ? AND date <= ? ORDER BY date ASC",
                (start_date, end_date)
            ).fetchall()
        return self._rconn.execute(
            "SELECT date, content FROM summary_history ORDER BY date ASC"
        ).fetchall()

    def get_latest_summary_snapshot(self):
        return self._rconn.execute(
            "SELECT date, content FROM summary_history ORDER BY date DESC LIMIT 1"
        ).fetchone()

    def has_summary_for_date(self, date_key: str) -> bool:
        row = self._rconn.execute("SELECT 1 FROM summary_history WHERE date = ?", (date_key,)).fetchone()
        return row is not None


# ==========================================
# 3. UI COMPONENTS
# ==========================================
class NoteButton(ctk.CTkFrame):
    def __init__(self, master, note_id, title, pinned, is_deleted, select_cmd, pin_cmd, get_str_cmd):
        super().__init__(master, fg_color="transparent")
        self.note_id = note_id
        self.get_str = get_str_cmd
        
        self.btn = ctk.CTkButton(self, anchor="w", text="", fg_color="transparent", hover_color="gray30", command=lambda: select_cmd(note_id))
        self.btn.pack(side="left", fill="x", expand=True)
        
        self.pin_mini = ctk.CTkButton(self, width=25, height=25, text="", fg_color="gray25", hover_color="gray40", command=lambda: pin_cmd(note_id))
        self.update_data(title, pinned)
        
        self.btn.bind("<Enter>", lambda e: self.pin_mini.pack(side="right", padx=5) if not is_deleted else None)
        self.btn.bind("<Leave>", lambda e: self.pin_mini.pack_forget())
        self.pin_mini.bind("<Leave>", lambda e: self.pin_mini.pack_forget())

    def update_data(self, title, pinned):
        display = (title if title and title.strip() else "...").replace("\n", " ")
        self.btn.configure(text=f"{'📌 ' if pinned else ''}{display}")
        self.pin_mini.configure(text=self.get_str("pin") if not pinned else self.get_str("unpin"))


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

    Client mapping format (one per line in Timetracking Clients note):
        PREFIX = Client Name
    """

    # Matches a time value at the start: 1h, 1.5h, 1,5h, 0.5h etc.
    _TIME_RE = re.compile(r'^(\d+(?:[.,]\d+)?)h\s+', re.IGNORECASE)
    # Looks like a time entry but may be malformed
    _LOOKS_LIKE_ENTRY_RE = re.compile(r'^\d', re.IGNORECASE)
    # Date marker: --- DD.MM.YYYY ---
    _DATE_RE = re.compile(r'^---\s*(\d{2})\.(\d{2})\.(\d{4})\s*---$')
    # Client mapping line: PREFIX = Name
    _CLIENT_RE = re.compile(r'^\s*([A-Z0-9]+)\s*=\s*(.+)$', re.IGNORECASE)

    def parse_clients(self, clients_content: str) -> dict:
        """Returns {PREFIX_UPPER: display_name}"""
        mapping = {}
        for line in clients_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = self._CLIENT_RE.match(line)
            if m:
                mapping[m.group(1).upper()] = m.group(2).strip()
        return mapping

    def parse_entries(self, tt_content: str, client_map: dict):
        """
        Returns:
            entries  : list of dicts {date, prefix, ticket, hours, description}
            warnings : list of strings (human-readable)
        """
        entries = []
        warnings = []
        current_date = None

        for lineno, raw in enumerate(tt_content.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue

            # Check for date marker
            dm = self._DATE_RE.match(line)
            if dm:
                day, month, year = dm.group(1), dm.group(2), dm.group(3)
                try:
                    current_date = date(int(year), int(month), int(day))
                except ValueError:
                    warnings.append(f"Line {lineno}: invalid date marker  \"{raw.rstrip()}\"")
                continue

            # Does it look like a time entry?
            if not self._LOOKS_LIKE_ENTRY_RE.match(line):
                continue  # plain text / description line, ignore silently

            # Try to parse as a proper time entry
            tm = self._TIME_RE.match(line)
            if not tm:
                warnings.append(f"Line {lineno}: unparseable  \"{raw.rstrip()}\"")
                continue

            hours = float(tm.group(1).replace(',', '.'))
            rest = line[tm.end():].strip()
            if not rest:
                warnings.append(f"Line {lineno}: unparseable (no ticket)  \"{raw.rstrip()}\"")
                continue

            # Parse prefix + ticket from rest
            parts = rest.split()
            first = parts[0]
            if '-' in first:
                # Format: PREFIX-123 description
                split = first.split('-', 1)
                prefix = split[0].upper()
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
                warnings.append(f"Line {lineno}: undated entry  \"{raw.rstrip()}\"")
                # Still record it under a sentinel date so it shows in warnings only
                continue

            entries.append({
                'date': current_date,
                'prefix': prefix,
                'ticket': ticket,
                'hours': hours,
                'description': description,
            })

        return entries, warnings

    def aggregate(self, entries: list, client_map: dict, filter_fn=None):
        """
        filter_fn: callable(entry) -> bool, or None for all entries.
        Returns dict keyed by prefix:
            { prefix: { 'name': str, 'tickets': { ticket: {'hours': float, 'descriptions': [str]} } } }
        """
        result = {}
        for e in entries:
            if filter_fn and not filter_fn(e):
                continue
            prefix = e['prefix']
            if prefix not in result:
                result[prefix] = {
                    'name': client_map.get(prefix, f"Unknown ({prefix})"),
                    'tickets': {}
                }
            tickets = result[prefix]['tickets']
            t = e['ticket']
            if t not in tickets:
                tickets[t] = {'hours': 0.0, 'descriptions': []}
            tickets[t]['hours'] += e['hours']
            if e['description']:
                tickets[t]['descriptions'].append(e['description'])
        return result

    def build_summary_text(self, tt_content: str, clients_content: str,
                           view_mode: str, nav_offset: int) -> str:
        """
        view_mode: 'daily', 'weekly' or 'monthly'
        nav_offset: 0 = current period, -1 = one period back, etc.
        """
        client_map = self.parse_clients(clients_content)
        entries, warnings = self.parse_entries(tt_content, client_map)

        today = date.today()

        if view_mode == 'daily':
            target_date = today + timedelta(days=nav_offset)
            label = target_date.strftime('%d.%m.%Y')
            filter_fn = lambda e: e['date'] == target_date
        elif view_mode == 'weekly':
            # Mon of the current week + offset
            monday = today - timedelta(days=today.weekday()) + timedelta(weeks=nav_offset)
            friday = monday + timedelta(days=4)
            label = f"Week {monday.strftime('%d.%m')} – {friday.strftime('%d.%m.%Y')}"
            filter_fn = lambda e: monday <= e['date'] <= friday
        else:
            # Monthly
            target_month = today.replace(day=1)
            # apply offset in months
            m = today.month + nav_offset
            y = today.year
            while m <= 0:
                m += 12; y -= 1
            while m > 12:
                m -= 12; y += 1
            target_month = date(y, m, 1)
            last_day = calendar.monthrange(y, m)[1]
            period_end = date(y, m, last_day)
            label = target_month.strftime('%B %Y')
            filter_fn = lambda e, s=target_month, en=period_end: s <= e['date'] <= en

        aggregated = self.aggregate(entries, client_map, filter_fn)

        lines = []
        lines.append(f"TIMETRACKING SUMMARY  —  {label}")
        lines.append("")

        total_hours = 0.0

        for prefix, data in sorted(aggregated.items()):
            client_total = sum(t['hours'] for t in data['tickets'].values())
            total_hours += client_total
            lines.append(f"── {data['name']} ({prefix}) " + "─" * max(2, 44 - len(data['name']) - len(prefix)))
            for ticket, tdata in sorted(data['tickets'].items()):
                desc_str = ' / '.join(dict.fromkeys(tdata['descriptions']))  # deduplicate, preserve order
                desc_str = (desc_str[:50] + '…') if len(desc_str) > 50 else desc_str
                lines.append(f"  {ticket:<18} {tdata['hours']:>5.1f}h   {desc_str}")
            lines.append(f"  {'Client total:':<18} {client_total:>5.1f}h")
            lines.append("")

        lines.append("═" * 48)
        lines.append(f"  {'TOTAL LOGGED:':<18} {total_hours:>5.1f}h")
        lines.append("")

        if warnings:
            lines.append("⚠ Warnings:")
            for w in warnings:
                lines.append(f"  {w}")

        return '\n'.join(lines)


# ==========================================
# 5. MAIN APPLICATION
# ==========================================
class HistoryNotesApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path(__file__).resolve().parent
        
        db_path = base_path / 'notes_vault.db'
        self.vault = NoteVault(db_path)
        
        # Set Window/Taskbar Icon
        icon_path = base_path / 'app_icon.ico'
        if icon_path.exists():
            self.iconbitmap(str(icon_path))
        
        self.lang = self.vault.get_setting("lang", "EN")
        self.current_note_id = None
        self.show_archived = False
        self.current_title_cache = ""
        self.history_snapshots = [] 
        self.last_saved_content_len = 0
        self.is_loading = False 
        
        self._after_id_format = None
        self._after_id_save = None
        self._sidebar_cache: dict = {}   # note_id -> NoteButton widget
        self._sidebar_order: list = []   # ordered list of currently visible note_ids
        self._sidebar_pinned_count: int = 0  # how many pinned notes are at the top of _sidebar_order

        # Timetracking
        self._tt_engine = TimetrackingEngine()
        self._history_window = None      # Reference to the history popup window
        self._last_tt_content_hash: str = ""  # skip redundant TT snapshots

        self.geometry("1100x850")
        ctk.set_appearance_mode("dark")
        
        self._init_ui()
        self.update_ui_texts()
        self._ensure_special_notes()
        self.refresh_sidebar()
        self.load_latest_or_empty()

        # Restore window geometry from last session
        saved_geo = self.vault.get_setting("window_geometry", "")
        if saved_geo:
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
        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=self.help_menu)
        self._build_help_menu()
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
        
        self.archive_toggle_btn = ctk.CTkButton(self.search_frame, text="📦", width=35, fg_color="gray25", command=self.toggle_archive_view)
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
        
        self.del_btn = ctk.CTkButton(self.top_bar, fg_color="#882222", width=140, command=self.handle_delete_action)
        self.del_btn.pack(side="right")
        self.restore_btn = ctk.CTkButton(self.top_bar, fg_color="#228844", width=140, command=self.restore_note)

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
            text="📊 History",
            width=100,
            height=28,
            fg_color="#2b5b84",
            hover_color="#3a7ab5",
            command=self.open_summary_history
        )

        self._setup_markdown_tags()

    # Colour palette: muted, dark-background-friendly
    FORMAT_COLORS = [
        ("Slate Blue",   "#7B9EC9"),
        ("Sage Green",   "#7EAA7E"),
        ("Warm Amber",   "#C9A84C"),
        ("Dusty Rose",   "#B87A7A"),
        ("Muted Teal",   "#5FA8A0"),
        ("Steel Gray",   "#8A9BB0"),
    ]
    # Regex: matches [colorname]...[/colorname]
    _COLOR_TAG_RE = re.compile(r'\[([a-z_]+)\](.*?)\[/\1\]', re.DOTALL)

    def _setup_markdown_tags(self):
        self.editor.tag_config("h1", foreground="#569CD6", underline=True)
        self.editor.tag_config("bold", foreground="#CE9178")
        self.editor.tag_config("list", foreground="#B5CEA8")
        self.editor.tag_config("timestamp", foreground="#A0A0A0")
        self.editor.tag_config("url", foreground="#4DA6FF", underline=True)
        self.editor.tag_config("search_match", background="#FFFF00", foreground="#000000")
        self.editor.tag_config("underline", underline=True)
        self.editor.tag_config("strikethrough", overstrike=True)
        self.editor._textbox.tag_config("bold_weight", font=("Consolas", 16, "bold"))
        # elide tags -- used to hide syntax markers for __, ~~, +++, and [color]
        self.editor._textbox.tag_config("color_hidden", elide=True)
        self.editor._textbox.tag_config("fmt_hidden", elide=True)
        for label, hex_color in self.FORMAT_COLORS:
            tag_name = "color_" + label.lower().replace(" ", "_")
            self.editor.tag_config(tag_name, foreground=hex_color)
        self.editor._textbox.tag_bind("url", "<Button-1>", self.open_url)
        self.editor._textbox.tag_bind("url", "<Enter>", lambda e: self.editor._textbox.configure(cursor="hand2"))
        self.editor._textbox.tag_bind("url", "<Leave>", lambda e: self.editor._textbox.configure(cursor="xterm"))
        self.editor.bind("<KeyRelease>", self.on_key_release)
        self.editor.bind("<Control-t>", self.insert_timestamp)
        self.editor.bind("<Control-b>", lambda e: self._apply_format("+++", "+++") or "break")
        self.editor._textbox.bind("<MouseWheel>", lambda e: self.apply_markdown())
        self.editor._textbox.bind("<Button-3>", self._show_context_menu)

    # ==========================================
    # LOGIC & EVENTS
    # ==========================================
    def get_str(self, key): 
        return STR_TABLE[self.lang].get(key, "")

    def update_ui_texts(self):
        s = STR_TABLE[self.lang]
        self.title(s["title"])
        self.new_btn.configure(text=s["new"])
        self.lang_btn.configure(text=s["lang_btn"])
        self.hist_label.configure(text=s["history_label"])
        self.version_info.configure(text=s["live"])
        self.tt_history_btn.configure(text=s["history_btn"])
        self.menubar.entryconfig(1, label=s["menu_file_label"])
        self.file_menu.delete(0, "end")
        self.file_menu.add_command(label=s["export"], command=self.export_notes)
        self.file_menu.add_command(label=s["import"], command=self.import_notes)
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
        try:
            index = self.editor._textbox.index(f"@{event.x},{event.y}")
            ranges = self.editor._textbox.tag_ranges("url")
            for i in range(0, len(ranges), 2):
                if self.editor._textbox.compare(ranges[i], "<=", index) and self.editor._textbox.compare(index, "<=", ranges[i+1]):
                    url = self.editor.get(ranges[i], ranges[i+1])
                    if not url.startswith(('http://', 'https://')): url = 'https://' + url
                    webbrowser.open(url)
                    break
        except Exception as e:
            log.warning("open_url error: %s", e)

    def _on_slider_move(self, val):
        if not self.current_note_id:
            return
        self._ensure_history_snapshots_loaded()
        if not self.history_snapshots:
            return
        self.is_loading = True
        idx = int(val)
        if idx >= len(self.history_snapshots):
            self.version_info.configure(text=self.get_str("live"), text_color="white")
            res = self.vault.get_note(self.current_note_id)
            if res: self._update_editor_silently(res[1])
        else:
            ts, content = self.history_snapshots[idx]
            self.version_info.configure(text=ts, text_color="#ffcc00")
            self._update_editor_silently(content)
        self.is_loading = False

    def _update_editor_silently(self, content):
        self.editor.delete("0.0", "end")
        self.editor.insert("0.0", content)
        self.apply_markdown(full_scan=True)
        self.last_saved_content_len = len(content)

    def on_key_release(self, e):
        if self.is_loading or e.keysym in ("Control_L", "Control_R"): return
        if self._after_id_format: self.after_cancel(self._after_id_format)
        self._after_id_format = self.after(50, self.apply_markdown)
        if self._after_id_save: self.after_cancel(self._after_id_save)
        self._after_id_save = self.after(1000, self.auto_save)
        self.update_stats()

    def auto_save(self):
        if not self.current_note_id or self.is_loading: return
        content = self.editor.get("0.0", "end-1c")
        new_title = (self.title_entry.get().strip() or self.get_str("new_note_default"))[:40]

        if (new_title == self.current_title_cache) and abs(len(content) - self.last_saved_content_len) < 5: return

        # Before saving Timetracking note, snapshot the current summary
        if new_title == self.TITLE_TT:
            self._snapshot_current_summary()

        self.vault.save_snapshot(self.current_note_id, new_title, content, force_history=True)
        
        # CHECK IF TITLE CHANGED - refresh sidebar immediately
        title_changed = (new_title != self.current_title_cache)
        self.current_title_cache = new_title
        self.last_saved_content_len = len(content)
        self._update_history_data()

        # Refresh sidebar if title changed or note moved in order
        if title_changed:
            self.refresh_sidebar()
        else:
            unpinned = self._sidebar_order[self._sidebar_pinned_count:]
            if not unpinned or unpinned[0] != self.current_note_id:
                self.refresh_sidebar()


    def force_save(self):
        if not self.current_note_id or self.is_loading: return
        content = self.editor.get("0.0", "end-1c")
        title = (self.title_entry.get().strip() or self.get_str("new_note_default"))[:40]
        
        # Before saving Timetracking note, snapshot the current summary
        if title == self.TITLE_TT:
            self._snapshot_current_summary()
            
        self.vault.save_snapshot(self.current_note_id, title, content, force_history=False)

    def load_note(self, nid):
        if self.current_note_id is not None: self.force_save()
        self.is_loading = True
        self.current_note_id = nid
        res = self.vault.get_note(nid)
        if res:
            title, content, is_deleted = res
            self.current_title_cache = title
            self.title_entry.delete(0, "end")
            if title and title != self.get_str("new_note_default"): self.title_entry.insert(0, title)

            # Check if this is the Timetracking note
            is_timetracking = (title == self.TITLE_TT)

            if is_timetracking:
                # Show history button in panel
                self.history_panel.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
                self.tt_history_btn.pack(side="right", padx=(10, 0))
                self.editor.configure(state="normal")
                self.editor.delete("0.0", "end")
                self.editor.insert("0.0", content)
            else:
                # Normal note: hide timetracking elements
                self.tt_history_btn.pack_forget()
                self.history_panel.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
                self.editor.configure(state="normal")
                self.editor.delete("0.0", "end")
                self.editor.insert("0.0", content)
                
            self.editor._textbox.see("1.0")
            self.apply_markdown(full_scan=True)
            self.update_stats()

            self.update_delete_button_state(is_deleted)
            self.last_saved_content_len = len(content)
        self._update_history_data()
        self.is_loading = False

    def _update_history_data(self):
        if not self.current_note_id:
            return
        # Count-only query -- avoids loading all content on every auto-save
        count = self.vault.get_history_count(self.current_note_id)
        self.history_snapshots = []   # lazy: loaded on first slider touch
        if count > 0:
            self.history_slider.configure(from_=0, to=count, number_of_steps=count)
            if not self.is_loading:
                self.history_slider.set(count)

    def _ensure_history_snapshots_loaded(self):
        """Load full snapshot content only when the slider is actually moved."""
        if not self.history_snapshots and self.current_note_id:
            self.history_snapshots = self.vault.get_history(self.current_note_id)

    def handle_delete_action(self):
        if not self.current_note_id: return
        res = self.vault.get_note(self.current_note_id)
        if res and res[2] == 1:
            if messagebox.askyesno(self.get_str("final_del"), self.get_str("confirm_del")):
                self.vault.delete_note_hard(self.current_note_id)
                self.current_note_id = None
                self.title_entry.delete(0, "end")
                self.editor.delete("0.0", "end")
        else:
            self.vault.delete_note_soft(self.current_note_id)
        self.refresh_sidebar()
        self.update_delete_button_state()

    def restore_note(self):
        if not self.current_note_id: return
        self.vault.restore_note(self.current_note_id)
        self.show_archived = False
        self.refresh_sidebar()
        self.update_delete_button_state()

    def insert_timestamp(self, e=None):
        res = self.vault.get_note(self.current_note_id) if self.current_note_id else None
        current_title = res[0] if res else ""
        if current_title == self.TITLE_TT:
            stamp = datetime.now().strftime("--- %d.%m.%Y ---")
        else:
            stamp = datetime.now().strftime("--- %d.%m.%Y, %H:%M ---")
        self.editor.insert(tk.INSERT, f"\n{stamp}\n")
        self.apply_markdown(full_scan=True)
        self.auto_save()
        return "break"

    def refresh_sidebar(self):
        rows = self.vault.fetch_sidebar_notes(self.search_bar.get().lower(), self.show_archived)
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
        self._sidebar_pinned_count = sum(1 for nid in new_order if new_data.get(nid, (None, 0))[1])

    def update_delete_button_state(self, is_deleted=None):
        if not self.current_note_id: 
            self.del_btn.configure(text=self.get_str("del"), fg_color="#882222")
            self.restore_btn.pack_forget()
            return
        if is_deleted is None:
            res = self.vault.get_note(self.current_note_id)
            is_deleted = res[2] if res else 0
        if is_deleted == 1:
            self.del_btn.configure(text=self.get_str("final_del"), fg_color="#FF0000")
            self.restore_btn.pack(side="right", padx=(0, 10))
            self.restore_btn.configure(text=self.get_str("restore"))
        else:
            self.del_btn.configure(text=self.get_str("del"), fg_color="#882222")
            self.restore_btn.pack_forget()

    def apply_markdown(self, full_scan=False):
        try:
            if full_scan:
                start_idx, end_idx = "1.0", "end"
            else:
                start_idx = self.editor._textbox.index(f"{self.editor._textbox.index('@0,0')} linestart -5 lines")
                if self.editor._textbox.compare(start_idx, "<", "1.0"): start_idx = "1.0"
                end_idx = self.editor._textbox.index(f"{self.editor._textbox.index(f'@0,{self.editor.winfo_height()}')} lineend +5 lines")

            all_tags = ["h1", "bold", "list", "timestamp", "url", "search_match",
                        "underline", "strikethrough"] + [
                        "color_" + l.lower().replace(" ", "_") for l, _ in self.FORMAT_COLORS]
            for tag in all_tags:
                self.editor.tag_remove(tag, start_idx, end_idx)
            self.editor._textbox.tag_remove("bold_weight", start_idx, end_idx)
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
                for m in re.finditer(pattern, content, flag):
                    self.editor.tag_add(tag, f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")

            # Inner-text rules: apply style to group(1), elide the markers
            # Each tuple: (tag, open_marker_len, close_marker_len, compiled_regex)
            inner_rules = [
                ("underline",     2, 2, re.compile(r'__(.*?)__',         re.DOTALL)),
                ("strikethrough", 2, 2, re.compile(r'~~(.*?)~~',         re.DOTALL)),
                ("bold_weight",   3, 3, re.compile(r'\+\+\+(.*?)\+\+\+', re.DOTALL)),
            ]
            for tag, open_len, close_len, rx in inner_rules:
                tb_ref = self.editor._textbox if tag == "bold_weight" else self.editor
                for m in rx.finditer(content):
                    inner_s = m.start(1)
                    inner_e = m.end(1)
                    tb_ref.tag_add(tag,          f"{start_idx} + {inner_s} chars", f"{start_idx} + {inner_e} chars")
                    self.editor.tag_add("fmt_hidden", f"{start_idx} + {m.start()} chars", f"{start_idx} + {inner_s} chars")
                    self.editor.tag_add("fmt_hidden", f"{start_idx} + {inner_e} chars",   f"{start_idx} + {m.end()} chars")

            # Colour tags: color inner text only, hide the [tag]...[/tag] markers
            for m in self._COLOR_TAG_RE.finditer(content):
                key = m.group(1)
                tag_name = "color_" + key
                if tag_name not in all_tags:
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
        self.load_note(nid)
        self.title_entry.focus_set() 

    def toggle_pin(self, nid):
        self.vault.toggle_pin(nid)
        self.refresh_sidebar()

    def toggle_archive_view(self):
        self.show_archived = not self.show_archived
        self.archive_toggle_btn.configure(fg_color="#445566" if self.show_archived else "gray25")
        self.refresh_sidebar()

    def export_notes(self):
        path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP Archive", "*.zip")])
        if not path: return
        with zipfile.ZipFile(path, 'w') as z:
            for t, ct in self.vault.get_export_data(): z.writestr(f"{t or 'note'}.txt", ct or "")

    def import_notes(self):
        path = filedialog.askopenfilename(filetypes=[("Text/ZIP", "*.txt *.zip")])
        if not path: return
        if path.endswith(".zip"):
            with zipfile.ZipFile(path, 'r') as z:
                for name in z.namelist():
                    if name.endswith(".txt"):
                        content = z.read(name).decode('utf-8', errors='ignore')
                        self.vault.create_note(name.replace(".txt", ""), content)
        else:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                self.vault.create_note(Path(path).stem, f.read())
        self.refresh_sidebar()

    def toggle_language(self):
        self.lang = "DE" if self.lang == "EN" else "EN"
        self.vault.set_setting('lang', self.lang)
        self.update_ui_texts()
        self.refresh_sidebar()

    def update_stats(self):
        text = self.editor.get("0.0", "end-1c")
        self.status_bar.configure(text=self.get_str("stats").format(len(text.split()), len(text)))

    def _build_help_menu(self):
        m = self.help_menu
        shortcuts = [
            ("Save",             "Ctrl+S"),
            ("Search",           "Ctrl+F"),
            ("Insert timestamp", "Ctrl+T"),
            ("Bold / fat text",  "Ctrl+B"),
        ]
        syntax = [
            ("Heading",          "# text"),
            ("Orange highlight", "**text**"),
            ("Fat / bold",       "+++text+++"),
            ("Underline",        "__text__"),
            ("Strikethrough",    "~~text~~"),
            ("Color",            "right-click menu"),
            ("List item",        "- text  or  * text"),
        ]
        m.add_command(label="── Keyboard shortcuts ──", state="disabled")
        for label, key in shortcuts:
            m.add_command(label=f"{label:<22}{key}", state="disabled")
        m.add_separator()
        m.add_command(label="── Formatting syntax ──", state="disabled")
        for label, syntax_str in syntax:
            m.add_command(label=f"{label:<22}{syntax_str}", state="disabled")

    def _on_app_close(self):
        """Flush pending edits before exit -- no keystrokes lost."""
        try:
            if self._after_id_save:
                self.after_cancel(self._after_id_save)
            if self._after_id_format:
                self.after_cancel(self._after_id_format)
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
        menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="#d4d4d4",
                       activebackground="#3a3a3a", activeforeground="#ffffff",
                       bd=0, relief="flat")

        # Standard edit actions
        menu.add_command(label="Cut",   command=lambda: self.editor._textbox.event_generate("<<Cut>>"))
        menu.add_command(label="Copy",  command=lambda: self.editor._textbox.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: self.editor._textbox.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Bold",          command=lambda: self._apply_format("**", "**"))
        menu.add_command(label="Underline",     command=lambda: self._apply_format("__", "__"))
        menu.add_command(label="Strikethrough", command=lambda: self._apply_format("~~", "~~"))
        menu.add_separator()
        # Colour submenu
        color_menu = tk.Menu(menu, tearoff=0, bg="#2b2b2b", fg="#d4d4d4",
                             activebackground="#3a3a3a", activeforeground="#ffffff",
                             bd=0, relief="flat")
        for label, _ in self.FORMAT_COLORS:
            tag_key = label.lower().replace(" ", "_")
            color_menu.add_command(label=label, command=lambda k=tag_key: self._apply_color(k))
        color_menu.add_separator()
        color_menu.add_command(label="Remove color", command=self._remove_color)
        menu.add_cascade(label="Color  ▶", menu=color_menu)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _apply_format(self, open_tag: str, close_tag: str):
        """Wrap or unwrap selected text with open_tag/close_tag markers."""
        tb = self.editor._textbox
        try:
            sel_start = tb.index("sel.first")
            sel_end   = tb.index("sel.last")
        except tk.TclError:
            return  # nothing selected
        selected = tb.get(sel_start, sel_end)
        if not selected:
            return
        # Toggle: strip if already wrapped
        if selected.startswith(open_tag) and selected.endswith(close_tag) and len(selected) > len(open_tag) + len(close_tag):
            new_text = selected[len(open_tag):-len(close_tag)]
        else:
            new_text = f"{open_tag}{selected}{close_tag}"
        tb.delete(sel_start, sel_end)
        tb.insert(sel_start, new_text)
        self.apply_markdown(full_scan=True)
        self.on_key_release(type('_', (), {'keysym': ''})())  # trigger debounced save

    def _apply_color(self, tag_key: str):
        """Wrap selected text in [tag_key]...[/tag_key]. Replaces existing color if present."""
        tb = self.editor._textbox
        try:
            sel_start = tb.index("sel.first")
            sel_end   = tb.index("sel.last")
        except tk.TclError:
            return
        selected = tb.get(sel_start, sel_end)
        if not selected:
            return
        # Strip any existing color wrapper first
        m = self._COLOR_TAG_RE.fullmatch(selected)
        inner = m.group(2) if m else selected
        new_text = f"[{tag_key}]{inner}[/{tag_key}]"
        tb.delete(sel_start, sel_end)
        tb.insert(sel_start, new_text)
        self.apply_markdown(full_scan=True)
        self.on_key_release(type('_', (), {'keysym': ''})())

    def _remove_color(self):
        """Strip all [color]...[/color] wrappers from selection."""
        tb = self.editor._textbox
        try:
            sel_start = tb.index("sel.first")
            sel_end   = tb.index("sel.last")
        except tk.TclError:
            return
        selected = tb.get(sel_start, sel_end)
        if not selected:
            return
        new_text = self._COLOR_TAG_RE.sub(r'\2', selected)
        if new_text != selected:
            tb.delete(sel_start, sel_end)
            tb.insert(sel_start, new_text)
            self.apply_markdown(full_scan=True)
            self.on_key_release(type('_', (), {'keysym': ''})())

    # ==========================================
    # TIMETRACKING
    # ==========================================
    TITLE_TT       = "Timetracking"
    TITLE_CLIENTS  = "Timetracking Clients"
    CLIENTS_DEFAULT = "# One line per client: PREFIX = Client Name\n# Example:\n# MMS = MöbelMartin\n# LGIT = LGIT GmbH\n"

    def _ensure_special_notes(self):
        """Create Timetracking special notes if they don't exist yet."""
        for title, default_content in [
            (self.TITLE_TT, ""),
            (self.TITLE_CLIENTS, self.CLIENTS_DEFAULT),
        ]:
            if not self.vault.get_note_by_title(title):
                self.vault.create_note(title, default_content)

    def _snapshot_current_summary(self):
        """Save TT summary snapshots. Skips if content unchanged since last call."""
        try:
            tt_row = self.vault.get_note_by_title(self.TITLE_TT)
            cl_row = self.vault.get_note_by_title(self.TITLE_CLIENTS)
            if not tt_row:
                return
            tt_content = tt_row[1] or ""
            cl_content = cl_row[1] if cl_row else ""
            # Skip expensive parse when nothing changed
            content_hash = hashlib.md5((tt_content + cl_content).encode()).hexdigest()
            if content_hash == self._last_tt_content_hash:
                return
            self._last_tt_content_hash = content_hash
            engine = self._tt_engine
            client_map = engine.parse_clients(cl_content)
            entries, _ = engine.parse_entries(tt_content, client_map)
            unique_dates = set(e['date'] for e in entries)
            today = date.today()
            for entry_date in unique_dates:
                date_str = entry_date.strftime('%d/%m/%Y')
                if not self.vault.has_summary_for_date(date_str) or entry_date == today:
                    text = engine.build_summary_text(
                        tt_content, cl_content, 'daily', (entry_date - today).days
                    )
                    self.vault.save_summary_snapshot(date_str, text)
        except Exception as e:
            log.error("_snapshot_current_summary error: %s", e)

    # ==========================================
    # SUMMARY HISTORY WINDOW
    # ==========================================
    def open_summary_history(self):
        """Open the summary history window."""
        if self._history_window and self._history_window.winfo_exists():
            self._history_window.lift()
            self._history_window.focus_force()
            return
        
        self._history_window = tk.Toplevel(self)
        self._history_window.title(f"Timetracking History - {self.get_str('title')}")
        self._history_window.geometry("800x700")
        self._history_window.minsize(600, 500)
        self._history_window.configure(bg="#1a1a1a")
        
        # Make it a proper window with icon
        try:
            if getattr(sys, 'frozen', False):
                icon_path = Path(sys.executable).parent / 'app_icon.ico'
            else:
                icon_path = Path(__file__).resolve().parent / 'app_icon.ico'
            if icon_path.exists():
                self._history_window.iconbitmap(str(icon_path))
        except Exception as e:
            log.debug("History window icon error: %s", e)
        
        # History window state
        self._hist_view_mode = 'daily'
        self._hist_nav_offset = 0
        self._hist_custom_date = None
        
        # Top navigation bar
        nav_frame = ctk.CTkFrame(self._history_window, fg_color="#1e1e2e", height=50)
        nav_frame.pack(fill="x", padx=5, pady=5)
        
        # Navigation arrows
        ctk.CTkButton(
            nav_frame, text="◀◀", width=35, fg_color="gray30",
            command=lambda: self._navigate_history(-1)
        ).pack(side="left", padx=(20, 2))
        
        ctk.CTkButton(
            nav_frame, text="▶▶", width=35, fg_color="gray30",
            command=lambda: self._navigate_history(1)
        ).pack(side="left", padx=2)
        
        # Date input field
        ctk.CTkLabel(nav_frame, text="Date (dd/mm/yyyy):", font=("Segoe UI", 10)).pack(side="left", padx=(20, 5))
        self._hist_date_entry = ctk.CTkEntry(nav_frame, width=100, font=("Segoe UI", 10))
        self._hist_date_entry.pack(side="left", padx=5)
        self._hist_date_entry.bind("<Return>", self._hist_jump_to_date)
        
        ctk.CTkButton(
            nav_frame, text="Go", width=40, fg_color="gray30",
            command=self._hist_jump_to_date
        ).pack(side="left", padx=2)
        
        # Period label
        self._hist_period_label = ctk.CTkLabel(nav_frame, text="", font=("Segoe UI", 10), text_color="gray")
        self._hist_period_label.pack(side="right", padx=10)
        
        # Content area
        self._hist_content = ctk.CTkTextbox(
            self._history_window, 
            font=("Consolas", 14), 
            fg_color="#121212",
            wrap="none"
        )
        self._hist_content.pack(fill="both", expand=True, padx=10, pady=10)
        self._hist_content.configure(state="disabled")
        
        # Close button at bottom
        ctk.CTkButton(
            self._history_window, 
            text="Close", 
            fg_color="gray30",
            command=self._history_window.destroy
        ).pack(pady=10)
        
        # Load initial data
        self._update_history_display()
        
        # Handle window close
        self._history_window.protocol("WM_DELETE_WINDOW", self._on_history_close)

    def _on_history_close(self):
        """Clean up when history window is closed."""
        if self._history_window:
            self._history_window.destroy()
            self._history_window = None

    def _set_history_mode(self, mode):
        """Set the history view mode (daily/weekly/monthly)."""
        self._hist_view_mode = mode
        self._hist_nav_offset = 0
        self._hist_custom_date = None
        self._hist_date_entry.delete(0, "end")
        self._update_history_display()

    def _navigate_history(self, direction):
        """Navigate forward/backward in history."""
        self._hist_nav_offset += direction
        self._hist_custom_date = None
        self._hist_date_entry.delete(0, "end")
        self._update_history_display()

    def _hist_jump_to_date(self, event=None):
        """Jump to a specific date entered in the date field."""
        date_str = self._hist_date_entry.get().strip()
        if not date_str:
            return
        
        try:
            parts = date_str.split('/')
            if len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                target_date = date(year, month, day)
                self._hist_custom_date = target_date
                self._hist_view_mode = 'daily'
                self._update_history_display()
        except (ValueError, IndexError):
            pass  # Invalid date format, just ignore

    def _update_history_display(self):
        """Load and display history data based on current settings."""
        today = date.today()
        
        # Calculate date range based on view mode and offset
        if self._hist_custom_date:
            if self._hist_view_mode == 'daily':
                start_date = end_date = self._hist_custom_date
                label = f"Daily: {start_date.strftime('%d.%m.%Y')}"
            elif self._hist_view_mode == 'weekly':
                monday = self._hist_custom_date - timedelta(days=self._hist_custom_date.weekday())
                friday = monday + timedelta(days=4)
                start_date, end_date = monday, friday
                label = f"Week: {monday.strftime('%d.%m')} – {friday.strftime('%d.%m.%Y')}"
            else:  # monthly
                start_date = date(self._hist_custom_date.year, self._hist_custom_date.month, 1)
                last_day = calendar.monthrange(self._hist_custom_date.year, self._hist_custom_date.month)[1]
                end_date = date(self._hist_custom_date.year, self._hist_custom_date.month, last_day)
                label = f"Month: {start_date.strftime('%B %Y')}"
        else:
            if self._hist_view_mode == 'daily':
                target_date = today + timedelta(days=self._hist_nav_offset)
                start_date = end_date = target_date
                label = f"Daily: {target_date.strftime('%d.%m.%Y')}"
            elif self._hist_view_mode == 'weekly':
                monday = today - timedelta(days=today.weekday()) + timedelta(weeks=self._hist_nav_offset)
                friday = monday + timedelta(days=4)
                start_date, end_date = monday, friday
                label = f"Week: {monday.strftime('%d.%m')} – {friday.strftime('%d.%m.%Y')}"
            else:  # monthly
                m = today.month + self._hist_nav_offset
                y = today.year
                while m <= 0:
                    m += 12; y -= 1
                while m > 12:
                    m -= 12; y += 1
                start_date = date(y, m, 1)
                last_day = calendar.monthrange(y, m)[1]
                end_date = date(y, m, last_day)
                label = f"Month: {start_date.strftime('%B %Y')}"
        
        self._hist_period_label.configure(text=label)
        
        # Fetch snapshots for the date range
        start_str = start_date.strftime('%d/%m/%Y')
        end_str = end_date.strftime('%d/%m/%Y')
        snapshots = self.vault.get_summary_snapshots(start_str, end_str)
        
        # Display the snapshots
        self._hist_content.configure(state="normal")
        self._hist_content.delete("1.0", "end")
        
        if not snapshots:
            self._hist_content.insert("1.0", self.get_str("no_history"))
        else:
            for i, (date_key, content) in enumerate(snapshots):
                if i > 0:
                    self._hist_content.insert("end", "\n\n" + "=" * 50 + "\n\n")
                self._hist_content.insert("end", content)
        
        self._hist_content.configure(state="disabled")


if __name__ == "__main__":
    app = HistoryNotesApp()
    app.mainloop()