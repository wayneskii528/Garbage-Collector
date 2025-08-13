import sys
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Callable, Tuple
from time import sleep
from getpass import getuser

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QCheckBox, QPushButton, QTextEdit, QProgressBar, QLabel,
    QScrollArea, QFrame
)
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from elevate import elevate
elevate()

import winshell

# ===================== Utilities =====================
def bytes_to_readable(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"

def safe_iterdir(path: Path):
    try:
        return list(path.iterdir())
    except Exception:
        return []

def rmtree_quiet(path: Path):
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

def unlink_quiet(path: Path):
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass

# ===================== Folder Size Worker =====================
class FolderSizeWorker(QThread):
    size_calculated = pyqtSignal(int)

    def __init__(self, paths: List[Path]):
        super().__init__()
        self.paths = paths
        self._running = True

    def run(self):
        total = 0
        for path in self.paths:
            total += self.get_size(path)
        self.size_calculated.emit(total)

    def get_size(self, path: Path) -> int:
        total = 0
        try:
            if path.is_file():
                return path.stat().st_size
            elif path.is_dir():
                for entry in os.scandir(path):
                    if not self._running:
                        break
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            total += self.get_size(Path(entry.path))
                    except Exception:
                        pass
        except Exception:
            pass
        return total

    def stop(self):
        self._running = False

# ===================== Cleanup Functions =====================
def clear_path_symlink(path: Path, log: Callable[[str], None]):
    if not path.exists():
        return
    try:
        if path.is_symlink():
            target = path.resolve()
            log(f"Folder is symlink: {path} -> {target}")
            clear_paths([target], log)
    except Exception as e:
        log(f"Failed to resolve symlink {path}: {e}")
    clear_paths([path], log)

def empty_recycle_bin(log):
    try:
        winshell.recycle_bin().empty(confirm=False, show_progress=False, sound=False)
        log("Recycle Bin emptied.")
    except Exception as e:
        log(f"Could not empty Recycle Bin: {e}")

def clear_paths(paths: List[Path], log: Callable[[str], None]):
    for p in paths:
        if not p.exists():
            continue
        try:
            if p.is_file():
                unlink_quiet(p)
                log(f"Deleted file: {p}")
            else:
                for sub in safe_iterdir(p):
                    if sub.is_file():
                        unlink_quiet(sub)
                        log(f"Deleted file: {sub}")
                    elif sub.is_dir():
                        rmtree_quiet(sub)
                        log(f"Deleted folder: {sub}")
        except Exception as e:
            log(f"Could not delete {p}: {e}")

# ===================== Cleanup Worker =====================
class CleanupWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    done_signal = pyqtSignal()

    def __init__(self, tasks: List[Tuple[str, Callable]]):
        super().__init__()
        self.tasks = tasks

    def run(self):
        total = len(self.tasks)
        for i, (label, func) in enumerate(self.tasks, start=1):
            self.log_signal.emit(f"Running: {label} ...")
            try:
                func(self.log_signal.emit)
            except Exception as e:
                self.log_signal.emit(f"Error in {label}: {e}")
            self.progress_signal.emit(int(i / total * 100))
            sleep(0.2)
        self.done_signal.emit()

# ===================== Cleanup Option =====================
class CleanupOption:
    def __init__(self, name: str, func: Callable, paths: List[Path] = None):
        self.name = name
        self.func = func
        self.paths = paths or []
        self.checkbox: QCheckBox = None

# ===================== Main UI =====================
class GarbageCollectorUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Garbage Collector")
        self.setWindowIcon(QIcon("trash-logo.ico"))
        self.resize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # Left panel
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color:#1e1e1e;border-radius:10px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.checkbox_layout = QVBoxLayout(scroll_content)
        self.checkbox_layout.setSpacing(5)
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(28)
        left_layout.addWidget(self.progress)

        self.start_btn = QPushButton("Start Cleanup")
        self.start_btn.setMinimumHeight(40)
        left_layout.addWidget(self.start_btn)

        self.space_label = QLabel("Estimated space to free: 0.00 MB")
        self.space_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        left_layout.addWidget(self.space_label)

        main_layout.addWidget(left_panel, 1)

        # Right panel
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 10))
        main_layout.addWidget(self.log_output, 1)

        # Options
        self.options: List[CleanupOption] = []

        def add_option(text, func, paths: List[Path] = None):
            cb = QCheckBox(text)
            cb.setFont(QFont("Arial", 10))
            cb.setMinimumHeight(24)
            cb.stateChanged.connect(self.update_estimate)
            self.checkbox_layout.addWidget(cb)
            option = CleanupOption(text, func, paths)
            option.checkbox = cb
            self.options.append(option)
            return cb

        home = Path.home()

        # ===================== Paths =====================
        temp_dir = [Path(tempfile.gettempdir())]
        downloads = [home / "Downloads"]
        prefetch = [Path(r"C:\Windows\Prefetch")]
        win_temp = [Path(r"C:\Windows\Temp")]
        windows_old = [Path(r"C:\Windows.old")]
        win_update = [Path(r"C:\Windows\SoftwareDistribution\Download")]
        office_cache = [Path(home / f"AppData/Local/Microsoft/Office/{v}/OfficeFileCache") for v in ["15.0","16.0"]]
        explorer_cache = [p for p in (home / r"AppData\Local\Microsoft\Windows\Explorer").glob("*.db") if p.exists()]
        directx_cache = [Path(home / p) for p in ["AppData/Local/D3DSCache","AppData/Local/D3DCache"]] + [Path(r"C:\Windows\Temp\DirectX")]
        browser_cache = [home / p for p in ["AppData/Local/Microsoft/Edge/User Data/Default/Cache",
                                           "AppData/Local/Google/Chrome/User Data/Default/Cache",
                                           "AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/Cache",
                                           "AppData/Local/Opera Software/Opera Stable/Cache"]]
        firefox_base = home / r"AppData\Local\Mozilla\Firefox\Profiles"
        if firefox_base.exists():
            for prof in safe_iterdir(firefox_base):
                c2 = prof / "cache2"
                if c2.exists():
                    browser_cache.append(c2)
        sys_logs = [p for p in Path(r"C:\Windows\System32\winevt\Logs").glob("*.evtx") if p.exists()]
        font_cache = [home / "AppData/Local/FontCache"]
        ms_store_cache = [home / "AppData/Local/Packages/Microsoft.WindowsStore_8wekyb3d8bbwe/LocalCache"]
        thumbnail_cache = [home / "AppData/Local/Microsoft/Windows/Explorer"]
        wer_reports = [Path(r"C:\ProgramData\Microsoft\Windows\WER\ReportQueue"),
                       Path(r"C:\ProgramData\Microsoft\Windows\WER\ReportArchive")]
        teams_cache = [home / "AppData/Roaming/Microsoft/Teams/Cache"]
        skype_cache = [home / "AppData/Roaming/Skype"]

        # ===================== Options =====================
        add_option("Empty Recycle Bin", empty_recycle_bin, [])
        add_option("Clear Temp Files", lambda log: [clear_path_symlink(p, log) for p in temp_dir], temp_dir)
        add_option("Clear Downloads", lambda log: [clear_path_symlink(p, log) for p in downloads], downloads)
        add_option("Clear Prefetch Files", lambda log: [clear_path_symlink(p, log) for p in prefetch], prefetch)
        add_option("Clear Windows Temp", lambda log: [clear_path_symlink(p, log) for p in win_temp], win_temp)
        add_option("Clear Windows.old", lambda log: [clear_path_symlink(p, log) for p in windows_old], windows_old)
        add_option("Clear Windows Update Cache", lambda log: [clear_path_symlink(p, log) for p in win_update], win_update)
        add_option("Clear Office Cache", lambda log: [clear_path_symlink(p, log) for p in office_cache], office_cache)
        add_option("Clear Explorer Thumbnails", lambda log: [clear_path_symlink(p, log) for p in explorer_cache], explorer_cache)
        add_option("Clear DirectX Cache", lambda log: [clear_path_symlink(p, log) for p in directx_cache], directx_cache)
        add_option("Clear Browser Cache", lambda log: [clear_path_symlink(p, log) for p in browser_cache], browser_cache)
        add_option("Clear System Logs", lambda log: [clear_path_symlink(p, log) for p in sys_logs], sys_logs)
        add_option("Clear Font Cache", lambda log: [clear_path_symlink(p, log) for p in font_cache], font_cache)
        add_option("Clear Microsoft Store Cache", lambda log: [clear_path_symlink(p, log) for p in ms_store_cache], ms_store_cache)
        add_option("Clear Thumbnail Cache", lambda log: [clear_path_symlink(p, log) for p in thumbnail_cache], thumbnail_cache)
        add_option("Clear Windows Error Reports", lambda log: [clear_path_symlink(p, log) for p in wer_reports], wer_reports)
        add_option("Clear Teams Cache", lambda log: [clear_path_symlink(p, log) for p in teams_cache], teams_cache)
        add_option("Clear Skype Cache", lambda log: [clear_path_symlink(p, log) for p in skype_cache], skype_cache)

        self.start_btn.clicked.connect(self.start_cleanup)
        self.update_estimate()

        # App styling
        self.setStyleSheet("""
            QMainWindow { background-color:#1e1e1e; }
            QFrame { background-color:#2e2e2e; border-radius:10px; }
            QScrollArea { background-color:#2e2e2e; border:none; }

            QCheckBox { color:#e0e0e0; spacing:10px; font-weight: normal; }
            QCheckBox::indicator { width:20px; height:20px; border-radius:4px; border: 2px solid #555555; background-color:#2e2e2e; }
            QCheckBox::indicator:checked { background-color: #88c0d0; border: 2px solid #81a1c1; }
            QCheckBox::indicator:hover { border-color: #81a1c1; }

            QPushButton {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #4c566a, stop:1 #3b4252);
                color: #eceff4;
                border-radius:8px;
                border: 1px solid #555555;
                padding:8px 15px;
                font-weight:bold;
            }
            QPushButton:hover {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #5e81ac, stop:1 #4c566a);
                border: 1px solid #81a1c1;
            }
            QPushButton:pressed {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #3b4252, stop:1 #2e3440);
                border: 1px solid #81a1c1;
            }

            QProgressBar {
                border:1px solid #555555;
                border-radius:6px;
                text-align:center;
                color:#ffffff;
                background-color:#3b3b3b;
            }
            QProgressBar::chunk {
                background-color:#88c0d0;
                border-radius:6px;
            }

            QTextEdit { background-color:#2e2e2e; color:#ffffff; border-radius:6px; }
            QLabel { color:#ffffff; }

            QScrollBar:vertical {
                background: #2e2e2e;
                width: 14px;
                margin: 0px 0px 0px 0px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                min-height: 20px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover {
                background: #777777;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    # ===================== Logging =====================
    def log(self, msg):
        self.log_output.append(msg)

    # ===================== Estimate =====================
    def update_estimate(self):
        paths_to_check = []
        for option in self.options:
            if option.checkbox.isChecked():
                paths_to_check.extend(option.paths)
        if paths_to_check:
            self.space_label.setText("Estimating...")
            self.size_worker = FolderSizeWorker(paths_to_check)
            self.size_worker.size_calculated.connect(lambda total: self.space_label.setText(
                f"Estimated space to free: {bytes_to_readable(total)}"
            ))
            self.size_worker.start()
        else:
            self.space_label.setText("Estimated space to free: 0.00 MB")

    # ===================== Start cleanup =====================
    def start_cleanup(self):
        tasks = [(option.name, option.func) for option in self.options if option.checkbox.isChecked()]
        if not tasks:
            self.log("No tasks selected.")
            return
        self.start_btn.setEnabled(False)
        self.progress.setValue(0)

        self.worker = CleanupWorker(tasks)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.done_signal.connect(self.cleanup_done)
        self.worker.start()

    def cleanup_done(self):
        self.log("Cleanup complete.")
        self.start_btn.setEnabled(True)
        self.update_estimate()

# ===================== Run app =====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = GarbageCollectorUI()
    win.show()
    sys.exit(app.exec())
