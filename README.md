# 📝 History Notes Pro

A lightweight, efficient tool for capturing and organizing your notes, with a version history for every note and built-in time tracking.

---

## 🚀 Desktop App Conversion (.exe)

Follow these steps to transform the source code into a standalone Windows application.

### 1. Install Python
Visit [python.org](https://www.python.org/) and download the latest Windows version.  
**Crucial:** Check the box **"Add Python to PATH"** during installation.

### 2. Download the Code
Click the green **Code** button on this page and select **Download ZIP**.  
Extract the ZIP file to a folder on your Desktop.

### 3. Open the Terminal
Open the folder containing `notes.py`.  
Click the **Address Bar** at the top, type `cmd`, and press **Enter**.

### 4. Install the Dependencies and Build
Run the following commands:

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconsole --onefile --icon=app_icon.ico --add-data "app_icon.ico;." notes.py
```

### 5. Locate Your App
Open the newly created **dist** folder. Your **notes.exe** is ready to use.  
Move it into a folder of its own, for example on your Desktop: the app keeps its data next to the .exe, and Windows does not allow that inside `Program Files`.

> [!NOTE]
> Windows SmartScreen may warn about an unknown publisher, because the .exe you built yourself is not signed. Choose **More info** and then **Run anyway**.

---

## 🛠 Features

| Feature | Details |
| :--- | :--- |
| **Auto-Save** | Saves 1 s after you stop typing. |
| **History Slider** | Browse earlier versions of a note. A version is kept once at least 5 characters changed. Typing into an older version restores it; the text it replaces stays in the history. |
| **Search** | Titles and content, case-insensitive, umlauts included. |
| **Pin & Archive** | Right-click a note in the sidebar to pin it. Archived notes (📦) can be restored or deleted permanently. |
| **Formatting** | `# heading`, `**highlight**`, `+++bold+++`, `__underline__`, `~~strikethrough~~`, colours via right-click. Listed in the **Help** menu. |
| **Timetracking** | Hours per day, week and month from a plain-text note, see below. |
| **Export / Import** | **File** menu: all active notes as `.txt` files in a ZIP; import `.txt` or `.zip`. |
| **Languages** | English and German, switch at the bottom of the sidebar. |
| **Portable** | Data is stored in **notes_vault.db** next to the app. |

### ⌨️ Shortcuts

| Key | Action |
| :--- | :--- |
| `Ctrl+S` | Save |
| `Ctrl+F` | Search |
| `Ctrl+T` | Insert timestamp (date only in the Timetracking note) |
| `Ctrl+B` | Bold (`+++`) |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |

### ⏱ Timetracking

The notes **Timetracking** and **Timetracking Clients** are created on first start. They keep their role when you rename them.
Write one entry per line below a date line (`Ctrl+T`); sections are optional:

```
******PROJECT A******
--- 25.09.2026 --- [2.25h]
1.5h ABC-123 fix login
0.75h ABC 124 review
```

- The total in brackets is added to every date line automatically, per section.
- **Timetracking Clients** maps ticket prefixes to names, one per line: `ABC = Acme Corp`.
- **📊 History** (shown in the Timetracking note): daily, weekly (Monday to Sunday) and monthly totals per client and ticket, **Copy** to the clipboard and **Export CSV** (Excel-ready; the German UI writes `;` and decimal commas).
- Days you delete from the note later stay in the history.

---

> [!CAUTION]
> **Warning:** If you delete the **notes_vault.db** file, all your notes will be permanently lost.
> Back it up while the app is closed: with the app open, the newest changes may still sit in `notes_vault.db-wal`.

### 💡 Pro-Tip
To move your notes to another computer, close the app and copy **notes.exe** and **notes_vault.db** together to the new device.

---

## 🧪 Tests

From the folder containing `notes.py`:

```bash
python -m unittest discover tests
```

The tests use temporary folders and never touch your `notes_vault.db`. The comparison tests against V21 need the git history (a `git clone`); in a ZIP download they are skipped.
