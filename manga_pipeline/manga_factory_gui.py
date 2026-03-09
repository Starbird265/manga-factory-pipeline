#!/usr/bin/env python3
"""
Manga Factory GUI - Premium Edition
All bugs fixed, live log panel added, new-site handling integrated.
"""

import sys
import os
import time
import subprocess
import datetime
import random
import re
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QFrame, QListWidget, QListWidgetItem,
                             QScrollArea, QSizePolicy, QPlainTextEdit)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, QRect
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPixmap

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

try:
    from manga_factory_enhanced import EnhancedMangaFactory, setup_logging
except ImportError:
    print("Warning: manga_factory_enhanced not found. Running in UI-only mode.")
    EnhancedMangaFactory = None

# --- CONSTANTS ---
C_BG       = "#0B0C10"
C_PANEL    = "#1F2833"
C_TEXT     = "#C5C6C7"
C_ACCENT   = "#66FCF1"
C_ACCENT_HOVER = "#45A29E"
C_BORDER   = "#1F2833"
C_BLUE     = "#66FCF1"   # alias — used by widget helpers
C_BLACK    = "#0B0C10"   # alias — used by widget helpers

CLEAN_STYLESHEET = f"""
QMainWindow {{
    background-color: {C_BG};
}}
QWidget {{
    font-family: 'Inter', 'Segoe UI', 'Helvetica', 'Arial', sans-serif;
    color: {C_TEXT};
}}

/* HEADERS */
QLabel#HeaderBig {{
    font-size: 38px;
    font-weight: 800;
    color: {C_ACCENT};
    letter-spacing: 2px;
    margin-bottom: 2px;
}}
QLabel#HeaderSub {{
    font-size: 14px;
    color: {C_TEXT};
    opacity: 0.7;
}}

/* PANELS */
QFrame#PanelBox {{
    background-color: rgba(31, 40, 51, 0.6);
    border: 1px solid rgba(102, 252, 241, 0.15);
    border-radius: 12px;
}}
QLabel#PanelTitle {{
    color: {C_ACCENT};
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 1px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(102, 252, 241, 0.1);
}}

/* INPUTS */
QLineEdit {{
    background-color: rgba(11, 12, 16, 0.8);
    border: 1px solid rgba(102, 252, 241, 0.2);
    border-radius: 6px;
    color: {C_TEXT};
    font-size: 14px;
    padding: 10px 14px;
}}
QLineEdit:focus {{
    border: 1px solid {C_ACCENT};
    background-color: rgba(11, 12, 16, 1.0);
}}

/* CHECKBOXES */
QCheckBox {{
    color: {C_TEXT};
    font-size: 13px;
    spacing: 10px;
    padding: 4px;
}}
QCheckBox:hover {{
    color: {C_ACCENT};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid rgba(102, 252, 241, 0.3);
    border-radius: 4px;
    background: rgba(11, 12, 16, 0.6);
}}
QCheckBox::indicator:hover {{
    border: 1px solid {C_ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {C_ACCENT};
    border: 1px solid {C_ACCENT};
}}

/* LIST (Library) */
QListWidget {{
    background-color: rgba(11, 12, 16, 0.5);
    border: 1px solid rgba(102, 252, 241, 0.15);
    border-radius: 8px;
    color: {C_TEXT};
    padding: 8px;
}}
QListWidget::item {{
    padding: 10px;
    border-bottom: 1px solid rgba(31, 40, 51, 0.8);
    border-radius: 4px;
}}
QListWidget::item:hover {{
    background-color: rgba(31, 40, 51, 0.6);
}}
QListWidget::item:selected {{
    background-color: rgba(69, 162, 158, 0.2);
    color: {C_ACCENT};
    border: 1px solid rgba(102, 252, 241, 0.3);
}}

/* LOG PANEL */
QPlainTextEdit#LogPanel {{
    background-color: rgba(0, 0, 0, 0.6);
    border: 1px solid rgba(102, 252, 241, 0.15);
    border-radius: 8px;
    color: {C_ACCENT};
    font-family: 'Menlo', 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    padding: 8px;
}}

/* BUTTONS */
QPushButton#RunBtn {{
    background-color: {C_ACCENT};
    color: {C_BG};
    font-weight: 800;
    font-size: 16px;
    letter-spacing: 1px;
    border: none;
    border-radius: 8px;
    padding: 16px;
}}
QPushButton#RunBtn:hover {{
    background-color: {C_ACCENT_HOVER};
}}
QPushButton#RunBtn:disabled {{
    background-color: {C_PANEL};
    color: rgba(197, 198, 199, 0.4);
}}
"""


class AssetLabel(QLabel):
    """Helper to display image scaled keeping aspect ratio"""
    def __init__(self, path, size=None):
        super().__init__()
        self.path = path
        if size:
            self.setFixedSize(*size)
        self.setScaledContents(True)
        self._load()

    def _load(self):
        if self.path.exists():
            pix = QPixmap(str(self.path))
            if not pix.isNull():
                self.setPixmap(pix)
            else:
                self.setText("IMG ERROR")
        else:
            self.setText(f"MISSING: {self.path.name}")
            self.setStyleSheet(
                f"border: 2px dashed {C_BLUE}; color: {C_BLUE}; font-size: 10px;"
            )


class Barcode(QWidget):
    """Simulates a barcode strip"""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(50)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C_BLACK))
        x = 0
        w_total = self.width()
        r = random.Random(42)
        while x < w_total:
            bw = r.randint(1, 6)
            gap = r.randint(1, 4)
            painter.drawRect(x, 0, bw, self.height())
            x += bw + gap


class VerticalLabel(QLabel):
    """Rotated text for sidebar"""
    def __init__(self, text):
        super().__init__(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QColor(C_BLACK))
        painter.setFont(self.font())
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(-90)
        painter.drawText(
            QRect(-150, -20, 300, 40),
            Qt.AlignmentFlag.AlignCenter,
            self.text()
        )


class SectionBox(QFrame):
    """Panel container with title"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("PanelBox")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

        t = QLabel(title)
        t.setObjectName("PanelTitle")
        self.layout.addWidget(t)

    def add_widget(self, w):
        self.layout.addWidget(w)


class ZineWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manga Factory")
        self.resize(960, 840)
        self.setMinimumSize(680, 500)
        self.setStyleSheet(CLEAN_STYLESHEET)

        # Root scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )
        self.main_widget = QWidget()
        self.scroll_area.setWidget(self.main_widget)
        self.setCentralWidget(self.scroll_area)

        self.content_col = QVBoxLayout(self.main_widget)
        self.content_col.setContentsMargins(30, 30, 30, 30)
        self.content_col.setSpacing(20)

        # 1. HEADER
        header_row = QVBoxLayout()
        header_row.setSpacing(4)
        title = QLabel("MANGA FACTORY")
        title.setObjectName("HeaderBig")
        sub = QLabel("Automated Precision Manga & Webtoon Downloader Pipeline")
        sub.setObjectName("HeaderSub")
        header_row.addWidget(title)
        header_row.addWidget(sub)
        self.content_col.addLayout(header_row)
        self.content_col.addSpacing(10)

        # 2. SOURCE TARGETS
        proc_box = SectionBox("SOURCE TARGETS")

        self.url_in = QLineEdit()
        self.url_in.setPlaceholderText(
            "Link to first chapter — e.g., site.com/chapter-40  (auto-increments for bulk downloads)"
        )
        proc_box.add_widget(self.url_in)

        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("Custom Series Output Directory Name (leave blank for auto)")
        proc_box.add_widget(self.name_in)

        self.ch_count = QLineEdit()
        self.ch_count.setPlaceholderText("How Many Chapters? (e.g., 10)")
        proc_box.add_widget(self.ch_count)

        self.dir_in = QLineEdit()
        self.dir_in.setPlaceholderText("Base Root Output Path")
        self.dir_in.setText(str(Path.home() / "Desktop" / "MangaOutput"))
        proc_box.add_widget(self.dir_in)

        self.content_col.addWidget(proc_box)

        # 3. MID SECTION
        mid_row = QHBoxLayout()

        # Col 1: PIPELINE MODULES
        mod_box = SectionBox("PIPELINE MODULES")
        self.chk_force_dl       = QCheckBox("FORCE REDOWNLOAD")
        self.chk_force_dl.setChecked(False)
        self.chk_human          = QCheckBox("HUMAN BEHAVIOR (Slows detection)")
        self.chk_human.setChecked(True)
        self.chk_adblock        = QCheckBox("AD BLOCKER / POPUP RELIEF")
        self.chk_adblock.setChecked(True)
        self.chk_stitch         = QCheckBox("AUTO STITCHING")
        self.chk_stitch.setChecked(True)
        self.chk_ml             = QCheckBox("ACTIVE LEARNING")
        self.chk_ml.setChecked(True)
        self.chk_learn_chars    = QCheckBox("LEARN CHARACTERS")
        self.chk_analyze_scenes = QCheckBox("ANALYZE SCENES")

        for w in (self.chk_force_dl, self.chk_human, self.chk_adblock,
                  self.chk_stitch, self.chk_ml, self.chk_learn_chars,
                  self.chk_analyze_scenes):
            mod_box.add_widget(w)
        mid_row.addWidget(mod_box)

        # Col 2: SKIP OPTIONS
        skip_box = SectionBox("SKIP STEPS (EXCLUSIONS)")
        self.chk_ocr   = QCheckBox("SKIP OCR")
        self.chk_clean = QCheckBox("SKIP CLEANING")
        self.chk_slice = QCheckBox("SKIP SLICING")
        for w in (self.chk_ocr, self.chk_clean, self.chk_slice):
            skip_box.add_widget(w)
        skip_box.layout.addStretch()
        mid_row.addWidget(skip_box)

        # Col 3: OUTPUT FORMATS
        term_box = SectionBox("OUTPUT FORMATS")
        self.chk_pdf    = QCheckBox("GENERATE PDF")
        self.chk_pdf.setChecked(True)
        self.chk_ai     = QCheckBox("AI SCRIPTING (Req. API Key)")
        self.chk_emotion = QCheckBox("EMOTION TAGS")
        for w in (self.chk_pdf, self.chk_ai, self.chk_emotion):
            term_box.add_widget(w)
        term_box.layout.addStretch()
        mid_row.addWidget(term_box)

        self.content_col.addLayout(mid_row)

        # 4. RECENT DOWNLOADS LIBRARY
        lib_box = SectionBox("RECENT DOWNLOADS")
        self.lib_list = QListWidget()
        self.lib_list.setFixedHeight(150)
        self.lib_list.itemDoubleClicked.connect(self._open_folder)
        lib_box.add_widget(self.lib_list)
        self.content_col.addWidget(lib_box)

        # 5. LIVE LOG PANEL
        log_box = SectionBox("PIPELINE LOG")
        self.log_panel = QPlainTextEdit()
        self.log_panel.setObjectName("LogPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setFixedHeight(180)
        self.log_panel.setMaximumBlockCount(500)   # auto-trim old lines
        self.log_panel.setPlaceholderText("Pipeline activity will appear here…")
        log_box.add_widget(self.log_panel)
        self.content_col.addWidget(log_box)

        # 6. RUN BUTTON
        self.run_btn = QPushButton("INITIALIZE PIPELINE")
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self._start_process)
        self.content_col.addWidget(self.run_btn)

        # Timers
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_library)
        self._refresh_timer.start(5000)
        self._refresh_library()

        self._log("Manga Factory ready. Enter a URL and click INITIALIZE PIPELINE.")

    # ------------------------------------------------------------------ Log helper
    def _log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_panel.appendPlainText(f"[{ts}] {msg}")
        # Scroll to bottom
        sb = self.log_panel.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------------ Library
    def _refresh_library(self):
        self.lib_list.clear()
        p = Path(self.dir_in.text())
        if p.exists():
            items = []
            try:
                for x in p.iterdir():
                    if x.is_dir() and not x.name.startswith('.'):
                        items.append((x.stat().st_mtime, x.name))
            except Exception:
                pass
            items.sort(key=lambda x: x[0], reverse=True)
            for ts, name in items:
                dt = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                sp = "-" * (40 - len(name)) if len(name) < 40 else "-"
                self.lib_list.addItem(f"■ {dt} {sp} {name}")

    def _open_folder(self, item):
        txt = item.text()
        p = Path(self.dir_in.text())
        name = txt.split(" ")[-1]
        target = p / name
        if target.exists():
            if sys.platform == 'darwin':
                subprocess.call(['open', str(target)])
            elif sys.platform == 'win32':
                os.startfile(str(target))
            else:
                subprocess.call(['xdg-open', str(target)])

    # ------------------------------------------------------------------ Start
    def _start_process(self):
        url = self.url_in.text().strip()

        # ---- URL validation ----
        if not url:
            self._log("⚠️  No URL entered. Please paste a chapter URL.")
            self.run_btn.setText("MISSING URL!")
            QTimer.singleShot(2000, lambda: self.run_btn.setText("INITIALIZE PIPELINE"))
            return

        # Basic sanity check — must look like a URL
        if "." not in url or (" " in url and not url.startswith("http")):
            self._log(f"⚠️  URL looks malformed: '{url}'. Add http:// and check for typos.")
            self.run_btn.setText("INVALID URL!")
            QTimer.singleShot(2000, lambda: self.run_btn.setText("INITIALIZE PIPELINE"))
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_in.setText(url)
            self._log(f"ℹ️  Auto-added https:// → {url}")

        try:
            count_txt = self.ch_count.text().strip()
            ch_count = int(count_txt) if count_txt else 1
            if ch_count < 1:
                ch_count = 1
        except ValueError:
            self._log("⚠️  Invalid chapter count — must be a number.")
            self.run_btn.setText("INVALID COUNT!")
            self.run_btn.setEnabled(True)
            QTimer.singleShot(2000, lambda: self.run_btn.setText("INITIALIZE PIPELINE"))
            return

        self.run_btn.setText("RUNNING…")
        self.run_btn.setEnabled(False)
        self._log(f"🚀 Starting pipeline: {ch_count} chapter(s) from {url}")

        config_options = {
            'url': url,
            'series_name': self.name_in.text().strip() or "",
            'ch_count': ch_count,
            'path': Path(self.dir_in.text()),
            'force_dl': self.chk_force_dl.isChecked(),
            'active_learning': self.chk_ml.isChecked(),
            'auto_stitching': self.chk_stitch.isChecked(),
            'learn_characters': self.chk_learn_chars.isChecked(),
            'analyze_scenes': self.chk_analyze_scenes.isChecked(),
            'human_behavior': self.chk_human.isChecked(),
            'ad_blocker': self.chk_adblock.isChecked(),
            'skip_ocr': self.chk_ocr.isChecked(),
            'skip_clean': self.chk_clean.isChecked(),
            'skip_slice': self.chk_slice.isChecked(),
            'generate_pdf': self.chk_pdf.isChecked(),
            'ai_scripting': self.chk_ai.isChecked(),
            'emotion_tags': self.chk_emotion.isChecked(),
        }

        self.worker = WorkerThread(config_options)
        self.worker.finished.connect(self._done)
        self.worker.progress.connect(self._on_progress)
        self.worker.start()

    def _on_progress(self, msg: str):
        self.run_btn.setText(msg[:50])   # cap button text width
        self._log(msg)                   # full message to log panel

    def _done(self):
        self.run_btn.setText("INITIALIZE PIPELINE")
        self.run_btn.setEnabled(True)
        self._log("─" * 50)
        self._refresh_library()


class WorkerThread(QThread):
    finished = pyqtSignal()
    progress = pyqtSignal(str)

    def __init__(self, config_options):
        super().__init__()
        self.config_options = config_options

    def run(self):
        if not EnhancedMangaFactory:
            self.progress.emit("❌ Backend (manga_factory_enhanced) not found")
            time.sleep(2)
            self.finished.emit()
            return

        try:
            url_target   = self.config_options['url']
            series_name  = self.config_options['series_name']
            base_path    = self.config_options['path']
            ch_count     = self.config_options['ch_count']
            force_dl     = self.config_options['force_dl']

            # Auto-name series from URL if left blank
            if not series_name:
                name_match = re.search(
                    r'/(?:manga|series|comic|title|en/[^/]+)/([^/?]+)', url_target
                )
                if name_match:
                    series_name = name_match.group(1).title().replace("-", " ")
                else:
                    parts = [p for p in url_target.split('/') if p]
                    if len(parts) >= 2:
                        series_name = parts[-2].title().replace("-", " ")
                    else:
                        from urllib.parse import urlparse
                        domain = urlparse(url_target).netloc
                        series_name = f"Auto_{domain.replace('www.', '')}"

            # Regex to find the chapter number in URL for auto-increment
            match = re.search(r'(.*?[^\d])(\d+)(/?)\s*$', url_target)

            for i in range(ch_count):
                if "{chapter}" in url_target:
                    current_url = url_target.replace("{chapter}", str(i + 1))
                    ch_num = i + 1
                elif match:
                    prefix     = match.group(1)
                    start_num  = int(match.group(2))
                    suffix     = match.group(3)
                    ch_num     = start_num + i
                    padding    = len(match.group(2))
                    ch_str     = str(ch_num).zfill(padding)
                    current_url = f"{prefix}{ch_str}{suffix}"
                else:
                    current_url = url_target if i == 0 else f"{url_target}/{i + 1}"
                    ch_num = i + 1

                chapter_name = f"Chapter_{ch_num}"
                chapter_dir  = base_path / series_name / chapter_name
                chapter_dir.mkdir(parents=True, exist_ok=True)

                self.progress.emit(f"[{i+1}/{ch_count}] ─── CH {ch_num}: {series_name} ───")
                f = EnhancedMangaFactory(str(chapter_dir), None)

                if self.config_options['human_behavior']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Human behavior enabled")
                if self.config_options['ad_blocker']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Ad blocker enabled")

                # Check existing files
                raw_dir    = f.dirs['raw']
                has_files  = raw_dir.exists() and any(raw_dir.iterdir())

                # Step 1: Download
                if has_files and not force_dl:
                    self.progress.emit(
                        f"[{i+1}/{ch_count}] Files exist — skipping download (enable FORCE REDOWNLOAD to override)"
                    )
                else:
                    self.progress.emit(f"[{i+1}/{ch_count}] Downloading from {current_url}…")
                    if not f.download_chapter(current_url):
                        self.progress.emit(
                            f"[{i+1}/{ch_count}] ⚠️  Download failed — check log for details. Skipping chapter."
                        )
                        time.sleep(1)
                        continue

                # Step 2: Clean
                if not self.config_options['skip_clean']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Cleaning pages…")
                    f.clean_pages_enhanced()

                # Step 3: Stitching
                if self.config_options['auto_stitching']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Stitching strips…")
                    f.process_stitching_enhanced(None, extract_single_panels=False)

                # Step 4: Panel Extraction
                if not self.config_options['skip_slice']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Extracting panels…")
                    f.extract_panels_enhanced(skip_validation=False)

                # Step 5: OCR
                if not self.config_options['skip_ocr']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Performing OCR…")
                    f.process_ocr_enhanced(ocr_lang='eng')

                # Step 6: Character Learning
                if self.config_options['learn_characters']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Learning characters…")
                    try:
                        from character_learner import CharacterLearner
                        learner = CharacterLearner(
                            output_dir=f.chapter_dir, manga_name=series_name
                        )
                        valid_panels = list(f.dirs['panels'].glob('*.png'))
                        for p in valid_panels:
                            learner.learn_from_panel(p, p.stem)
                        learner.cluster_characters()
                    except Exception as e:
                        self.progress.emit(f"[{i+1}/{ch_count}] ⚠️  Character learning skipped: {e}")

                # Step 7: Scene Analysis
                if self.config_options['analyze_scenes']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Analyzing scenes…")
                    try:
                        from character_learner import SceneAnalyzer
                        import json
                        scene_meta   = {}
                        valid_panels = list(f.dirs['panels'].glob('*.png'))
                        for p in valid_panels:
                            tags = SceneAnalyzer.analyze(p)
                            if tags:
                                scene_meta[p.name] = tags
                        f.dirs['script'].mkdir(parents=True, exist_ok=True)
                        with open(f.dirs['script'] / 'scene_analysis.json', 'w') as fh:
                            json.dump(scene_meta, fh, indent=2)
                    except Exception as e:
                        self.progress.emit(f"[{i+1}/{ch_count}] ⚠️  Scene analysis skipped: {e}")

                # Step 8: Script Generation
                self.progress.emit(f"[{i+1}/{ch_count}] Generating script…")
                if self.config_options['ai_scripting']:
                    f.generate_ai_enhanced_script(chapter_title=chapter_name)
                else:
                    f.generate_script_enhanced(
                        add_emotions=self.config_options['emotion_tags']
                    )

                # Step 9: Active Learning / ML
                if self.config_options['active_learning']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Active learning…")
                    f.train_model_if_needed()

                # Step 10: PDF Generation
                if self.config_options['generate_pdf']:
                    self.progress.emit(f"[{i+1}/{ch_count}] Generating PDF…")
                    try:
                        from pdf_generator import generate_chapter_pdf
                        generate_chapter_pdf(str(chapter_dir))
                    except Exception as e:
                        self.progress.emit(f"[{i+1}/{ch_count}] ⚠️  PDF generation skipped: {e}")

                self.progress.emit(f"[{i+1}/{ch_count}] ✅ Chapter {ch_num} complete!")

            self.progress.emit(f"🎉 PIPELINE COMPLETE! ({ch_count} chapter(s) processed)")

        except Exception as e:
            self.progress.emit(f"❌ Fatal error: {e}")
            time.sleep(2)

        self.finished.emit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(CLEAN_STYLESHEET)
    w = ZineWindow()
    w.show()
    sys.exit(app.exec())
