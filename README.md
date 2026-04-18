📝 History Notes Pro

A lightweight, distraction-free tool for capturing and organizing your history notes.

🚀 Turn It Into a Desktop App (.exe)

Follow this simple guide to convert the project into a standalone Windows application:

🧩 Step 1 — Install Python

Download Python from python.org

⚠️ Important: أثناء التثبيت، تأكد من تفعيل خيار
“Add Python to PATH”

📦 Step 2 — Download the Project
Click the green Code button on this page
Select Download ZIP
Extract the ZIP file somewhere easy (like your Desktop)
💻 Step 3 — Open Command Prompt in the Folder
Open the folder containing notes.py
Click the address bar at the top
Type cmd and press Enter
⚙️ Step 4 — Install PyInstaller

Run this command:

pip install pyinstaller
🏗 Step 5 — Build the App

Convert the script into an .exe:

pyinstaller --onefile --windowed notes.py
📂 Step 6 — Find Your App
Open the newly created dist folder
You’ll find notes.exe inside
Move it anywhere and run it 🎉
✨ Features & Shortcuts
🚀 Feature	💡 What It Does
Auto-Save	Saves automatically after 1 second of inactivity (if changes > 5 characters)
Manual Save	Ctrl + S — Save instantly with a subtle confirmation
Search	Ctrl + F — Quickly find any note
Timestamp	Ctrl + T — Insert current date & time
Portable	Stores data in notes_vault.db (same folder as the app)
Clean UI	Minimal, distraction-free interface
⚠️ Important Warning

[!CAUTION]
Deleting notes_vault.db will permanently erase all your notes.
There is no recovery.

💡 Pro Tip

Want to move your notes to another computer?

👉 Just copy:

notes.exe
notes_vault.db

Keep them in the same folder, and everything will work instantly.
