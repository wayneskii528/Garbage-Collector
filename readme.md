Garbage Collector - Windows Cleanup Tool
=========================================

A Python-based Windows cleanup tool built with PyQt6. It allows users to clear temporary files, browser caches, Windows logs, Recycle Bin, and more.

Features
--------

- Empty Recycle Bin
- Clear Temp Files
- Clear Downloads folder
- Clear Windows Prefetch and Temp folders
- Clear Windows Update cache
- Clear Office and browser caches (Chrome, Edge, Brave, Firefox, Opera)
- Clear Windows Error Reports
- View estimated space to free
- Threaded cleanup for responsiveness

Requirements
------------

- Windows 10/11
- Python 3.10+

Install dependencies:

pip install -r requirements.txt

Usage
-----

python main.py

- Run as administrator for full cleanup.
- Check the desired cleanup options.
- Click **Start Cleanup** to remove selected files.
- View logs and progress in real time.

Notes
-----

- Make sure to close applications like Office, Teams, or Skype to safely remove cache files.

License
-------

MIT License
