# 📝 History Notes Pro

A lightweight, efficient tool for capturing and organizing your history notes.

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

### 4. Install the Converter
Run the following command:

```bash
pip install pyinstaller
```
## 5. Locate Your App
Open the newly created **dist** folder. Your **notes.exe** is ready to use or move to your Desktop.

---

## 🛠 Features & Shortcuts

| Feature | Details |
| :--- | :--- |
| **Auto-Save** | Triggers 1s after typing stops (if >5 chars changed). |
| **Manual Save** | **Ctrl + S** — Force-save with a discrete popup. |
| **History Slider** | A simple slider to browse every change you've made. |
| **Search** | **Ctrl + F** — Instantly find specific entries. |
| **Timestamp** | **Ctrl + T** — Inserts current date and time. |
| **Portable** | Data is stored in **notes_vault.db** within the app folder. |
| **Clean UI** | Minimalist design for high-focus note-taking. |

---

> [!CAUTION]
> **Warning:** If you delete the **notes_vault.db** file, all your notes will be permanently lost.

---

### 💡 Pro-Tip
To share your notes with another computer, you must copy both **notes.exe** and **notes_vault.db** together to the new device.
