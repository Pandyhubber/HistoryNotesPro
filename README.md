📝 History Notes Pro
Minimal. Fast. Focused note-taking for history lovers.
<p align="center"> <img src="https://img.shields.io/badge/Platform-Windows-blue?style=for-the-badge"> <img src="https://img.shields.io/badge/Python-3.x-yellow?style=for-the-badge"> <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge"> <img src="https://img.shields.io/badge/Status-Stable-success?style=for-the-badge"> </p>
✨ Overview

History Notes Pro is a lightweight desktop tool designed for fast, distraction-free note-taking.
Built for simplicity and efficiency, it helps you focus on what matters: your ideas.

🚀 Get the Desktop App (.exe)

Turn the project into a standalone Windows app in minutes:

🧩 1. Install Python

Download from 👉 https://www.python.org/

⚠️ Important: أثناء التثبيت، فعّل
"Add Python to PATH"

📦 2. Download the Source Code
Click Code → Download ZIP
Extract it anywhere (Desktop recommended)
💻 3. Open Command Prompt
Open the project folder
Click the address bar
Type cmd → press Enter
⚙️ 4. Install Build Tool
pip install pyinstaller
🏗 5. Build the Executable
pyinstaller --onefile --windowed notes.py
📂 6. Run Your App
Go to the dist folder
Launch notes.exe 🎉
🧠 Features
<p align="center">
Feature	Description
⚡ Auto Save	Saves automatically after 1s of inactivity
💾 Manual Save	Ctrl + S for instant save
🔍 Search	Ctrl + F to find notes instantly
🕒 Timestamp	Ctrl + T inserts date & time
📦 Portable	All data stored locally
🎯 Minimal UI	Clean interface for maximum focus
</p>
📁 Data Storage

Your notes are محفوظة في:

notes_vault.db

📌 Located in the same folder as the app.

⚠️ Warning

[!CAUTION]
Deleting notes_vault.db will permanently delete all your notes.
No backup. No recovery.

💡 Pro Tip

To transfer your notes to another computer:

✔ Copy both files:

notes.exe
notes_vault.db

📁 Keep them in the same folder — done.
