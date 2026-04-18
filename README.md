# 📝 History Notes Pro

A lightweight, efficient tool for capturing and organizing your history notes.

---

## 🚀 How to Use This as a Desktop App (.exe)

Follow these simple steps to turn the source code into a clickable application for your Windows computer.

### Step 1: Install Python

1. Go to [python.org](https://www.python.org/downloads/) and download the latest version for Windows.
2. **Crucial:** When installing, check the box that says **"Add Python to PATH"** before clicking Install.

### Step 2: Download the Code

1. Click the green **Code** button at the top of this GitHub page and select **Download ZIP**.
2. Extract the ZIP file to a folder on your Desktop.

### Step 3: Open the Terminal

1. Open your folder containing `notes.py`.
2. Click on the **Address Bar** at the top of the folder window, type `cmd`, and press **Enter**. A black window will open.

### Step 4: Install the Converter

In the Command Prompt window, type this command and press **Enter**:

```bash
pip install pyinstaller
```

### Step 5: Create the .exe

Type this final command and press **Enter**:

```bash
pyinstaller --onefile --windowed notes.py
```

### Step 6: Locate Your App

Once the process finishes, you will see a new folder named `dist`. Open it, and you will find `notes.exe`. You can now move this file anywhere (like your Desktop) and run it!

---

## 🛠 Features & Shortcuts

| Feature | Details |
|---|---|
| **Auto-Save** | Triggers 1sec. after typing stops if >5 chars changed. |
| **Manual Save** | Ctrl + S —  Force-save with a discrete "Saved" popup. |
| **Portable** | Notes are stored in `notes_vault.db` in the same folder as the app. |
| **Search** | `Ctrl + F` — Instantly find specific entries within your history notes. |
| **Timestamp** | `Ctrl + T` — Inserts a current date and time stamp into your note. |
| **Clean UI** | Designed for high-focus note-taking without distractions. |

> ⚠️ **Warning:** If you delete the `.db` file, all your notes will be lost!

---

## 💡 Pro-Tip

To share your notes with another computer, copy **both** `notes.exe` and `notes_vault.db` together.
