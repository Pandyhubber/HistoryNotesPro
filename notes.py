import tkinter as tk
import customtkinter as ctk
import sqlite3
import os
import sys
import zipfile
import re
from datetime import datetime
from tkinter import messagebox, filedialog

class HistoryNotes(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'notes_vault.db')
        self._setup_db()
        
        self.lang = self._get_setting("lang", "DE")
        self.current_note_id = None
        self.show_archived = False
        self.current_title_cache = ""
        self.history_snapshots = [] 
        self.last_saved_content_len = 0
        self.is_loading = False 
        
        self._after_id_format = None
        self._after_id_save = None

        self.str_table = {
            "DE": {
                "title": "HistoryNotes PRO", "new": "+ Neue Notiz", "del": "Archivieren", "final_del": "Endgültig Löschen",
                "restore": "Wiederherstellen", "pin": "📌", "unpin": "✕", "live": "Live",
                "lang_btn": "Sprache: DE", "menu_file": "Datei", "export": "Export (.zip)", 
                "import": "Import (.txt/.zip)", "stats": "Wörter: {} | Zeichen: {}", 
                "confirm_del": "Notiz wirklich endgültig löschen?", "history_label": "Versionsverlauf",
                "menu_file_label": "Datei"
            },
            "EN": {
                "title": "HistoryNotes PRO", "new": "+ New Note", "del": "Archive", "final_del": "Delete Permanently",
                "restore": "Restore", "pin": "📌", "unpin": "✕", "live": "Live",
                "lang_btn": "Language: EN", "menu_file": "File", "export": "Export (.zip)", 
                "import": "Import (.txt/.zip)", "stats": "Words: {} | Chars: {}", 
                "confirm_del": "Delete note permanently?", "history_label": "History Version",
                "menu_file_label": "File"
            }
        }

        self.geometry("1100x850")
        ctk.set_appearance_mode("dark")
        self._init_ui()
        self.update_ui_texts()
        self.refresh_sidebar()
        self.load_latest_or_empty()
        
        self.search_bar.focus_set()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)

    def _setup_db(self):
        with self._get_conn() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS note_list (id INTEGER PRIMARY KEY, title TEXT, pinned INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0, last_content TEXT, last_updated TEXT)')
            conn.execute('CREATE TABLE IF NOT EXISTS history (note_id INTEGER, content TEXT, timestamp TEXT)')
            conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
            conn.commit()

    def _init_ui(self):
        self.menubar = tk.Menu(self)
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=self.get_str("menu_file_label"), menu=self.file_menu)
        self.config(menu=self.menubar)

        self.paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#1a1a1a", sashwidth=2, borderwidth=0, opaqueresize=False)
        self.paned_window.pack(fill="both", expand=True)

        self.sidebar = ctk.CTkFrame(self.paned_window, width=280, corner_radius=0)
        self.paned_window.add(self.sidebar, width=280, minsize=180)
        
        self.new_btn = ctk.CTkButton(self.sidebar, text=self.get_str("new"), command=self.create_new_note)
        self.new_btn.pack(pady=10, padx=10)
        
        self.search_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.search_frame.pack(fill="x", padx=10)
        self.search_bar = ctk.CTkEntry(self.search_frame)
        self.search_bar.pack(side="left", fill="x", expand=True, pady=5)
        self.search_bar.bind("<KeyRelease>", lambda e: self.refresh_sidebar())
        
        self.archive_toggle_btn = ctk.CTkButton(self.search_frame, text="📦", width=35, fg_color="gray25", command=self.toggle_archive_view)
        self.archive_toggle_btn.pack(side="right", padx=(5, 0))
        
        self.note_list_frame = ctk.CTkScrollableFrame(self.sidebar, label_text="Notes")
        self.note_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.lang_btn = ctk.CTkButton(self.sidebar, text=self.get_str("lang_btn"), fg_color="gray20", command=self.toggle_language)
        self.lang_btn.pack(side="bottom", pady=10)

        self.main_content = ctk.CTkFrame(self.paned_window, fg_color="transparent")
        self.paned_window.add(self.main_content, minsize=400)
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(0, weight=1)

        self.editor_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.editor_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=10)
        self.editor_container.grid_columnconfigure(0, weight=1)
        self.editor_container.grid_rowconfigure(1, weight=1)
        
        self.top_bar = ctk.CTkFrame(self.editor_container, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", pady=(0,5))
        
        self.del_btn = ctk.CTkButton(self.top_bar, text=self.get_str("del"), fg_color="#882222", width=140, command=self.handle_delete_action)
        self.del_btn.pack(side="right")
        self.restore_btn = ctk.CTkButton(self.top_bar, text=self.get_str("restore"), fg_color="#228844", width=140, command=self.restore_note)

        self.editor = ctk.CTkTextbox(self.editor_container, font=("Consolas", 16), undo=True, fg_color="#121212")
        self.editor.grid(row=1, column=0, sticky="nsew")
        
        self.status_bar = ctk.CTkLabel(self.editor_container, text="", font=("Segoe UI", 11), text_color="gray")
        self.status_bar.grid(row=2, column=0, sticky="w", pady=2)

        self.history_panel = ctk.CTkFrame(self.main_content, height=80)
        self.history_panel.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        
        self.hist_label = ctk.CTkLabel(self.history_panel, text=self.get_str("history_label"), font=("Segoe UI", 12, "bold"))
        self.hist_label.pack(side="top", pady=2)

        self.slider_frame = ctk.CTkFrame(self.history_panel, fg_color="transparent")
        self.slider_frame.pack(fill="x", padx=20, pady=5)

        self.history_slider = ctk.CTkSlider(self.slider_frame, from_=0, to=1, number_of_steps=1, command=self._on_slider_move)
        self.history_slider.pack(side="left", fill="x", expand=True)
        
        self.version_info = ctk.CTkLabel(self.slider_frame, text=self.get_str("live"), width=120)
        self.version_info.pack(side="right", padx=10)

        self.editor.tag_config("title_line", foreground="#569CD6", spacing1=5, spacing3=10)
        self.editor.tag_config("h1", foreground="#569CD6", underline=True)
        self.editor.tag_config("bold", foreground="#CE9178")
        self.editor.tag_config("list", foreground="#B5CEA8")
        self.editor.tag_config("timestamp", foreground="#718096")

        self.editor.bind("<KeyRelease>", self.on_key_release)
        self.editor.bind("<Control-t>", self.insert_timestamp)
        self.editor._textbox.bind("<MouseWheel>", lambda e: self.apply_markdown())

    def _on_slider_move(self, val):
        if not self.history_snapshots: return
        self.is_loading = True 
        idx = int(val)
        if idx >= len(self.history_snapshots):
            self.version_info.configure(text=self.get_str("live"), text_color="white")
            with self._get_conn() as conn:
                res = conn.execute("SELECT last_content FROM note_list WHERE id = ?", (self.current_note_id,)).fetchone()
                if res: self._update_editor_silently(res[0])
        else:
            ts, content = self.history_snapshots[idx]
            self.version_info.configure(text=ts, text_color="#ffcc00")
            self._update_editor_silently(content)
        self.is_loading = False

    def _update_editor_silently(self, content):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.apply_markdown(full_scan=True)
        self.last_saved_content_len = len(content)

    def auto_save(self):
        if not self.current_note_id or self.is_loading: return
        content = self.editor.get("1.0", "end-1c")
        current_len = len(content)
        first_line = content.split('\n')[0].strip()
        new_title = (re.sub(r'^#+\s*', '', first_line) or "...")[:40]
        
        title_changed = (new_title != self.current_title_cache)
        if not title_changed and abs(current_len - self.last_saved_content_len) < 5: return 

        now_str = datetime.now().isoformat()
        with self._get_conn() as conn:
            last = conn.execute("SELECT content FROM history WHERE note_id = ? ORDER BY timestamp DESC LIMIT 1", (self.current_note_id,)).fetchone()
            if not last or last[0] != content:
                conn.execute("INSERT INTO history (note_id, content, timestamp) VALUES (?, ?, ?)", (self.current_note_id, content, now_str))
            conn.execute("UPDATE note_list SET title = ?, last_content = ?, last_updated = ? WHERE id = ?", (new_title, content, now_str, self.current_note_id))
            conn.commit()
            
        self.current_title_cache = new_title
        self.last_saved_content_len = current_len
        if title_changed: self.refresh_sidebar()
        self._update_history_data()

    def _update_history_data(self):
        if not self.current_note_id: return
        with self._get_conn() as conn:
            rows = conn.execute("SELECT timestamp, content FROM history WHERE note_id = ? ORDER BY timestamp ASC", (self.current_note_id,)).fetchall()
            self.history_snapshots = [(r[0][11:16] if 'T' in r[0] else r[0][:16], r[1]) for r in rows]
        count = len(self.history_snapshots)
        if count > 0:
            self.history_slider.configure(from_=0, to=count, number_of_steps=count)
            if not self.is_loading: self.history_slider.set(count)

    def force_save(self):
        if not self.current_note_id or self.is_loading: return
        content = self.editor.get("1.0", "end-1c")
        new_title = (re.sub(r'^#+\s*', '', (content.split('\n')[0].strip())) or "...")[:40]
        now_str = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("UPDATE note_list SET title = ?, last_content = ?, last_updated = ? WHERE id = ?", (new_title, content, now_str, self.current_note_id))
            conn.commit()

    def load_note(self, nid):
        if self.current_note_id is not None: 
            self.force_save()
        self.is_loading = True
        self.current_note_id = nid
        with self._get_conn() as conn:
            res = conn.execute("SELECT title, last_content FROM note_list WHERE id = ?", (nid,)).fetchone()
            if res:
                self.current_title_cache = res[0]
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", res[1])
                # Ensure cursor is at top and visible
                self.editor._textbox.see("1.0")
                self.editor._textbox.mark_set("insert", "1.0")
                self.editor.focus_set()
                self.apply_markdown(full_scan=True)
                self.update_stats()
                self.update_delete_button_state()
                self.last_saved_content_len = len(res[1])
        self._update_history_data()
        self.is_loading = False

    def handle_delete_action(self):
        if not self.current_note_id: return
        with self._get_conn() as conn:
            res = conn.execute("SELECT is_deleted FROM note_list WHERE id = ?", (self.current_note_id,)).fetchone()
            if res and res[0] == 1:
                if messagebox.askyesno(self.get_str("final_del"), self.get_str("confirm_del")):
                    conn.execute("DELETE FROM note_list WHERE id = ?", (self.current_note_id,))
                    conn.execute("DELETE FROM history WHERE note_id = ?", (self.current_note_id,))
                    conn.commit()
                    self.current_note_id = None
                    self.editor.delete("1.0", "end")
            else:
                conn.execute("UPDATE note_list SET is_deleted = 1, pinned = 0 WHERE id = ?", (self.current_note_id,))
                conn.commit()
        self.refresh_sidebar()
        self.update_delete_button_state()

    def restore_note(self):
        if not self.current_note_id: return
        with self._get_conn() as conn:
            conn.execute("UPDATE note_list SET is_deleted = 0 WHERE id = ?", (self.current_note_id,))
            conn.commit()
        self.show_archived = False
        self.refresh_sidebar()
        self.update_delete_button_state()

    def on_key_release(self, e):
        if self.is_loading or e.keysym in ("Control_L", "Control_R"): return
        if self._after_id_format: self.after_cancel(self._after_id_format)
        self._after_id_format = self.after(50, self.apply_markdown)
        if self._after_id_save: self.after_cancel(self._after_id_save)
        self._after_id_save = self.after(1000, self.auto_save)
        self.update_stats()

    def insert_timestamp(self, e=None):
        now = datetime.now().strftime("%d.%m.%Y, %H:%M")
        self.editor.insert(tk.INSERT, f"\n--- {now} ---\n")
        self.apply_markdown(full_scan=True)
        self.auto_save()
        return "break"

    def refresh_sidebar(self):
        search = self.search_bar.get().lower()
        f = 1 if self.show_archived else 0
        with self._get_conn() as conn:
            q = f"SELECT id, title, pinned, is_deleted FROM note_list WHERE is_deleted = {f}"
            p = []
            if search: 
                q += " AND (LOWER(title) LIKE ? OR LOWER(last_content) LIKE ?)"
                p = [f'%{search}%', f'%{search}%']
            q += " ORDER BY pinned DESC, last_updated DESC"
            rows = conn.execute(q, p).fetchall()
        for child in self.note_list_frame.winfo_children(): child.destroy()
        for nid, title, pinned, is_del in rows:
            NoteButton(self.note_list_frame, nid, title, pinned, is_del, self.load_note, self.toggle_pin, self.get_str).pack(fill="x", pady=2)

    def update_delete_button_state(self):
        if not self.current_note_id: 
            self.del_btn.configure(text=self.get_str("del"), fg_color="#882222")
            self.restore_btn.pack_forget()
            return
        with self._get_conn() as conn:
            res = conn.execute("SELECT is_deleted FROM note_list WHERE id = ?", (self.current_note_id,)).fetchone()
            if res and res[0] == 1:
                self.del_btn.configure(text=self.get_str("final_del"), fg_color="#FF0000")
                self.restore_btn.pack(side="right", padx=(0, 10))
            else:
                self.del_btn.configure(text=self.get_str("del"), fg_color="#882222")
                self.restore_btn.pack_forget()

    def apply_markdown(self, full_scan=False):
        try:
            if full_scan:
                start_idx, end_idx = "1.0", "end"
            else:
                start_idx = self.editor._textbox.index("@0,0")
                end_idx = self.editor._textbox.index(f"@0,{self.editor.winfo_height()}")
                start_idx = self.editor._textbox.index(f"{start_idx} linestart -5 lines")
                if self.editor._textbox.compare(start_idx, "<", "1.0"): start_idx = "1.0"
                end_idx = self.editor._textbox.index(f"{end_idx} lineend +5 lines")
            for tag in ["h1", "bold", "list", "timestamp", "title_line"]: 
                self.editor.tag_remove(tag, start_idx, end_idx)
            self.editor.tag_add("title_line", "1.0", "1.end")
            content = self.editor.get(start_idx, end_idx)
            for m in re.finditer(r"^# .*", content, re.M): 
                self.editor.tag_add("h1", f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")
            for m in re.finditer(r"\*\*.*?\*\*", content): 
                self.editor.tag_add("bold", f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")
            for m in re.finditer(r"^[ \t]*[-*+] .*", content, re.M): 
                self.editor.tag_add("list", f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")
            for m in re.finditer(r"--- \d{2}\.\d{2}\.\d{4}, \d{2}:\d{2} ---", content): 
                self.editor.tag_add("timestamp", f"{start_idx} + {m.start()} chars", f"{start_idx} + {m.end()} chars")
        except: pass

    def update_ui_texts(self):
        s = self.str_table[self.lang]
        self.title(s["title"])
        self.new_btn.configure(text=s["new"])
        self.lang_btn.configure(text=s["lang_btn"])
        self.hist_label.configure(text=s["history_label"])
        self.version_info.configure(text=s["live"])
        self.file_menu.delete(0, "end")
        # Only add export/import entries; do NOT add a duplicate "File" label
        self.file_menu.add_command(label=s["export"], command=self.export_notes)
        self.file_menu.add_command(label=s["import"], command=self.import_notes)
        self.update_delete_button_state()

    def create_new_note(self):
        now_str = datetime.now().isoformat()
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO note_list (title, last_content, last_updated) VALUES ('...', '', ?)", (now_str,))
            nid = c.lastrowid
            conn.commit()
        self.refresh_sidebar(); self.load_note(nid)

    def toggle_pin(self, nid):
        with self._get_conn() as conn:
            conn.execute("UPDATE note_list SET pinned = 1 - pinned WHERE id = ?", (nid,))
            conn.commit()
        self.refresh_sidebar()

    def toggle_archive_view(self):
        self.show_archived = not self.show_archived
        self.archive_toggle_btn.configure(fg_color="#445566" if self.show_archived else "gray25")
        self.refresh_sidebar()

    def export_notes(self):
        path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP Archive", "*.zip")])
        if not path: return
        with zipfile.ZipFile(path, 'w') as z:
            with self._get_conn() as conn:
                for t, ct in conn.execute("SELECT title, last_content FROM note_list WHERE is_deleted = 0").fetchall():
                    z.writestr(f"{t or 'note'}.txt", ct or "")

    def import_notes(self):
        path = filedialog.askopenfilename(filetypes=[("Text/ZIP", "*.txt *.zip")])
        if not path: return
        if path.endswith(".zip"):
            with zipfile.ZipFile(path, 'r') as z:
                for name in z.namelist():
                    if name.endswith(".txt"):
                        content = z.read(name).decode('utf-8', errors='ignore')
                        self._add_to_db(name.replace(".txt", ""), content)
        else:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                self._add_to_db(os.path.basename(path).replace(".txt", ""), f.read())
        self.refresh_sidebar()

    def _add_to_db(self, t, ct):
        now_str = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute("INSERT INTO note_list (title, last_content, last_updated) VALUES (?, ?, ?)", (t, ct, now_str))
            conn.commit()

    def toggle_language(self):
        self.lang = "EN" if self.lang == "DE" else "DE"
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (self.lang,))
            conn.commit()
        self.update_ui_texts(); self.refresh_sidebar()

    def get_str(self, key): return self.str_table[self.lang].get(key, "")

    def _get_setting(self, k, d):
        try:
            with self._get_conn() as conn:
                r = conn.execute("SELECT value FROM settings WHERE key = ?", (k,)).fetchone()
                return r[0] if r else d
        except: return d

    def update_stats(self):
        text = self.editor.get("1.0", "end-1c")
        self.status_bar.configure(text=self.get_str("stats").format(len(text.split()), len(text)))

    def load_latest_or_empty(self):
        with self._get_conn() as conn:
            row = conn.execute("SELECT id FROM note_list WHERE is_deleted = 0 ORDER BY pinned DESC, last_updated DESC LIMIT 1").fetchone()
            if row: self.load_note(row[0])

class NoteButton(ctk.CTkFrame):
    def __init__(self, master, note_id, title, pinned, is_deleted, select_cmd, pin_cmd, get_str_cmd):
        super().__init__(master, fg_color="transparent")
        self.note_id = note_id; self.get_str = get_str_cmd
        self.btn = ctk.CTkButton(self, anchor="w", text="", fg_color="transparent", hover_color="gray30", command=lambda: select_cmd(note_id))
        self.btn.pack(side="left", fill="x", expand=True)
        self.pin_mini = ctk.CTkButton(self, width=25, height=25, text="", fg_color="gray25", hover_color="gray40", command=lambda: pin_cmd(note_id))
        self.update_data(title, pinned)
        self.btn.bind("<Enter>", lambda e: self.pin_mini.pack(side="right", padx=5) if not is_deleted else None)
        self.bind("<Leave>", lambda e: self.pin_mini.pack_forget())

    def update_data(self, title, pinned):
        display = (title if title and title.strip() else "...").replace("\n", " ")
        self.btn.configure(text=f"{'📌 ' if pinned else ''}{display}")
        self.pin_mini.configure(text=self.get_str("pin") if not pinned else self.get_str("unpin"))

if __name__ == "__main__":
    app = HistoryNotes()
    app.mainloop()