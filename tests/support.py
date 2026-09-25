"""Shared test helpers. Every test works in its own temp folder; a real notes_vault.db is never touched.

Run from the repo root:  python -m unittest discover tests
"""
import sys
import tempfile
import subprocess
import importlib.util
import itertools
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

import notes  # noqa: E402

_TMP = tempfile.TemporaryDirectory(prefix='hnp_tests_', ignore_cleanup_errors=True)
TMP = Path(_TMP.name)

# V21, the last version before the V22 rework, read from the git history for the
# equivalence and migration tests. Without the history (ZIP download) they are skipped.
V21_REV = 'd8857de'


def _v21_source():
    try:
        return subprocess.run(['git', '-C', str(REPO), 'show', f'{V21_REV}:notes.py'],
                              capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


V21_SOURCE = _v21_source()
HAVE_V21 = V21_SOURCE is not None
_counter = itertools.count()


def new_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix='case_', dir=TMP))


def load_old_module(folder: Path):
    """V21 notes.py, written into folder, so its database lives there."""
    dst = folder / 'old_notes.py'
    dst.write_bytes(V21_SOURCE)
    spec = importlib.util.spec_from_file_location(f"old_notes_{next(_counter)}", dst)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Ev:
    def __init__(self, keysym=''):
        self.keysym = keysym


def make_app(folder: Path):
    notes.app_dir = lambda: folder
    app = notes.HistoryNotesApp()
    app.withdraw()
    app.update()
    return app


def close_app(app):
    app._on_app_close()


def pump(app, ms: int):
    """Run the Tk event loop for ms milliseconds (lets after() callbacks fire)."""
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.update()
        time.sleep(0.01)


def type_text(app, text, at=None):
    """Insert like typing at the cursor (or at index `at`) and fire the key-release handler."""
    tb = app.editor._textbox
    if at is not None:
        tb.mark_set('insert', at)
    tb.insert('insert', text)
    app.on_key_release(Ev('a'))


def set_editor(app, text):
    """Replace the editor text as one edit and fire the key-release handler."""
    app.editor.delete('1.0', 'end')
    app.editor.insert('1.0', text)
    app.on_key_release(Ev('a'))


def db_note(app, nid):
    app.vault.flush()
    return app.vault.get_note(nid)


def note_id_by_title(app, title):
    app.vault.flush()
    row = app.vault._rconn.execute("SELECT id FROM note_list WHERE title = ? ORDER BY id LIMIT 1", (title,)).fetchone()
    return row[0] if row else None
