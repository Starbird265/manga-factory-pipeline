#!/usr/bin/env python3
"""
Manga Factory GUI.

A focused desktop control deck for the pipeline: clear inputs, real backend
terminal output, honest run stats, and controls that map to worker behavior.
"""

import datetime
import concurrent.futures
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

from PyQt6.QtCore import QRect, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

try:
    import requests
except ImportError:
    requests = None

sys.path.append(str(Path(__file__).parent))

try:
    from manga_factory_enhanced import EnhancedMangaFactory
except ImportError:
    print("Warning: manga_factory_enhanced not found. Running in UI-only mode.")
    EnhancedMangaFactory = None

try:
    from ml_proxy_manager import MLProxyManager
except ImportError:
    MLProxyManager = None

try:
    from smart_pipeline_manager import SmartPipelineManager
except ImportError:
    SmartPipelineManager = None


C_BG = "#DCE6E8"
C_SURFACE = "#FBFCFA"
C_SURFACE_2 = "#D7EEE7"
C_INK = "#172327"
C_MUTED = "#5D6C70"
C_RED = "#D95849"
C_TEAL = "#087D74"
C_GOLD = "#E9AE42"
C_TERMINAL = "#11191C"
C_TERM_TEXT = "#D8FFF0"
C_TERM_DIM = "#83AAA4"


APP_STYLESHEET = f"""
QMainWindow {{
    background-color: {C_BG};
}}
QWidget {{
    font-family: "Avenir Next", "Inter", "Segoe UI", "Helvetica", "Arial", sans-serif;
    color: {C_INK};
    font-size: 13px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QFrame#Hero {{
    background-color: {C_SURFACE_2};
    border: 1px solid rgba(255, 244, 223, 0.34);
    border-radius: 10px;
}}
QFrame#PetStage {{
    background-color: #102326;
    border: 2px solid {C_TEAL};
    border-radius: 8px;
}}
QLabel#PetActivity {{
    color: {C_TEAL};
    font-size: 10px;
    font-weight: 850;
    letter-spacing: 1px;
}}
QFrame#PanelBox {{
    background-color: {C_SURFACE};
    border: 1px solid rgba(33, 26, 22, 0.12);
    border-radius: 9px;
}}
QFrame#StatBox {{
    background-color: rgba(255, 255, 255, 0.48);
    border: 1px solid rgba(33, 26, 22, 0.10);
    border-radius: 8px;
}}
QLabel#AppTitle {{
    color: {C_INK};
    font-size: 34px;
    font-weight: 900;
    letter-spacing: 1px;
}}
QLabel#AppKicker {{
    color: {C_RED};
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#AppSubtitle {{
    color: {C_MUTED};
    font-size: 14px;
}}
QLabel#PanelTitle {{
    color: {C_INK};
    font-size: 15px;
    font-weight: 850;
}}
QLabel#PanelHint {{
    color: {C_MUTED};
    font-size: 12px;
}}
QLabel#GroupLabel {{
    color: {C_RED};
    font-size: 11px;
    font-weight: 850;
    letter-spacing: 1px;
    padding: 4px 0 2px 0;
}}
QLabel#StatLabel {{
    color: {C_MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#StatValue {{
    color: {C_INK};
    font-size: 22px;
    font-weight: 900;
}}
QLabel#StatusPill {{
    background-color: {C_INK};
    color: {C_SURFACE};
    border-radius: 14px;
    padding: 7px 12px;
    font-weight: 800;
    letter-spacing: 1px;
}}
QLabel#PathLabel {{
    color: {C_MUTED};
    font-size: 12px;
}}
QLineEdit, QSpinBox, QPlainTextEdit#UrlInput {{
    background-color: rgba(255, 255, 255, 0.72);
    border: 1px solid rgba(33, 26, 22, 0.18);
    border-radius: 7px;
    color: {C_INK};
    padding: 9px 11px;
    selection-background-color: {C_GOLD};
}}
QSpinBox {{
    min-height: 22px;
}}
QLineEdit:focus, QSpinBox:focus {{
    border: 1px solid {C_TEAL};
    background-color: #FFFFFF;
}}
QPlainTextEdit#UrlInput {{
    font-family: "Menlo", "SF Mono", "Consolas", monospace;
    font-size: 12px;
    line-height: 1.35;
}}
QPlainTextEdit#UrlInput:focus {{
    border: 1px solid {C_TEAL};
    background-color: #FFFFFF;
}}
QCheckBox {{
    color: {C_INK};
    spacing: 9px;
    padding: 3px 0;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid rgba(33, 26, 22, 0.30);
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.70);
}}
QCheckBox::indicator:checked {{
    background-color: {C_TEAL};
    border: 1px solid {C_TEAL};
}}
QCheckBox:disabled {{
    color: #A99C8C;
}}
QCheckBox::indicator:disabled {{
    background-color: rgba(33, 26, 22, 0.08);
    border-color: rgba(33, 26, 22, 0.12);
}}
QPushButton {{
    border: none;
    border-radius: 8px;
    padding: 10px 13px;
    font-weight: 800;
}}
QPushButton#RunBtn {{
    background-color: {C_RED};
    color: white;
    font-size: 15px;
    min-height: 34px;
}}
QPushButton#RunBtn:hover {{
    background-color: #C84A39;
}}
QPushButton#RunBtn:disabled {{
    background-color: #8A8178;
}}
QPushButton#StopBtn {{
    background-color: {C_INK};
    color: {C_SURFACE};
}}
QPushButton#StopBtn:disabled {{
    background-color: #A99C8C;
    color: rgba(255, 244, 223, 0.60);
}}
QPushButton#GhostBtn {{
    background-color: rgba(33, 26, 22, 0.08);
    color: {C_INK};
}}
QPushButton#GhostBtn:hover {{
    background-color: rgba(33, 26, 22, 0.14);
}}
QPlainTextEdit#LogPanel {{
    background-color: {C_TERMINAL};
    color: {C_TERM_TEXT};
    border: 1px solid rgba(201, 242, 214, 0.18);
    border-radius: 9px;
    font-family: "Menlo", "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 10px;
}}
QProgressBar {{
    background-color: rgba(33, 26, 22, 0.12);
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {C_TEAL};
    border-radius: 6px;
}}
QListWidget {{
    background-color: rgba(255, 255, 255, 0.48);
    border: 1px solid rgba(33, 26, 22, 0.12);
    border-radius: 8px;
    padding: 6px;
}}
QListWidget::item {{
    padding: 9px;
    border-radius: 6px;
}}
QListWidget::item:hover {{
    background-color: rgba(20, 124, 114, 0.11);
}}
QListWidget::item:selected {{
    background-color: rgba(180, 60, 46, 0.16);
    color: {C_INK};
}}
QListWidget#QueueList {{
    background-color: #F4F8F8;
    border: 1px solid rgba(8, 125, 116, 0.22);
}}
QListWidget#QueueList::item {{
    border-left: 3px solid {C_TEAL};
    margin: 2px 0;
    padding: 8px 10px;
}}
"""


class SectionBox(QFrame):
    def __init__(self, title: str, hint: str = ""):
        super().__init__()
        self.setObjectName("PanelBox")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 18)
        self.layout.setSpacing(11)

        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")
        self.layout.addWidget(title_label)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("PanelHint")
            hint_label.setWordWrap(True)
            self.layout.addWidget(hint_label)

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)


class StatBox(QFrame):
    def __init__(self, label: str, value: str = "0"):
        super().__init__()
        self.setObjectName("StatBox")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        self.label = QLabel(label.upper())
        self.label.setObjectName("StatLabel")
        self.value = QLabel(value)
        self.value.setObjectName("StatValue")
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value):
        self.value.setText(str(value))


class QtLogHandler(logging.Handler):
    def __init__(self, emit_line):
        super().__init__()
        self.emit_line = emit_line
        self.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))

    def emit(self, record):
        try:
            self.emit_line(self.format(record))
        except Exception:
            pass


class PixelPetStage(QFrame):
    """A small pixel stage driven by the real pipeline state."""

    CELL_SIZE = (192, 208)
    STATES = {
        "idle": (0, (280, 110, 110, 140, 140, 320)),
        "running-right": (1, (120, 120, 120, 120, 120, 120, 120, 220)),
        "running-left": (2, (120, 120, 120, 120, 120, 120, 120, 220)),
        "waving": (3, (140, 140, 140, 280)),
        "jumping": (4, (140, 140, 140, 140, 280)),
        "failed": (5, (140, 140, 140, 140, 140, 140, 140, 240)),
        "waiting": (6, (150, 150, 150, 150, 150, 260)),
        "running": (7, (120, 120, 120, 120, 120, 220)),
        "review": (8, (150, 150, 150, 150, 150, 280)),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PetStage")
        self.setFixedSize(174, 124)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._assets_dir = Path(__file__).parent / "assets" / "inkbit"
        self._atlas_path = self._assets_dir / "spritesheet.webp"
        self._fallback_path = self._assets_dir / "idle.png"
        self._atlas = QPixmap()
        self._fallback = QPixmap()
        self._state = "idle"
        self._frame = 0
        self._elapsed_ms = 0
        self._travel = 0.50
        self._direction = 1
        self._load_assets()

        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _load_assets(self):
        if self._atlas_path.exists():
            self._atlas = QPixmap(str(self._atlas_path))
        if self._fallback_path.exists():
            self._fallback = QPixmap(str(self._fallback_path))

    def set_state(self, state: str):
        state = state if state in self.STATES else "idle"
        if state == self._state:
            return
        self._state = state
        self._frame = 0
        self._elapsed_ms = 0
        self.update()

    def _advance(self):
        durations = self.STATES[self._state][1]
        self._elapsed_ms += self._timer.interval()
        if self._elapsed_ms >= durations[self._frame]:
            self._elapsed_ms = 0
            self._frame = (self._frame + 1) % len(durations)

        if self._state in {"running-right", "running-left"}:
            step = 0.028 * (1 if self._state == "running-right" else -1)
            self._travel += step
            if self._travel >= 0.88:
                self._travel = 0.88
                self._state = "running-left"
                self._frame = 0
            elif self._travel <= 0.12:
                self._travel = 0.12
                self._state = "running-right"
                self._frame = 0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        target_width, target_height = 92, 100
        x = int((self.width() - target_width) * self._travel)
        bob = 2 if self._state == "jumping" and self._frame in {1, 2} else 0
        y = self.height() - target_height - 7 - bob
        target = QRect(x, y, target_width, target_height)

        if not self._atlas.isNull():
            row, durations = self.STATES[self._state]
            source = QRect(
                self._frame * self.CELL_SIZE[0],
                row * self.CELL_SIZE[1],
                self.CELL_SIZE[0],
                self.CELL_SIZE[1],
            )
            painter.drawPixmap(target, self._atlas, source)
        elif not self._fallback.isNull():
            painter.drawPixmap(target, self._fallback)
        else:
            painter.setPen(QColor("#D8FFF0"))
            painter.setFont(QFont("Menlo", 8, QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "INKBIT")
        painter.end()


class ZineWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manga Factory")
        self.resize(1180, 820)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(APP_STYLESHEET)
        self.worker = None
        self.last_output_path = None
        self.last_log_path = None
        self.queue_items = {}
        self.queue_states = {}

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.main_widget = QWidget()
        self.scroll_area.setWidget(self.main_widget)
        self.setCentralWidget(self.scroll_area)

        root = QVBoxLayout(self.main_widget)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        root.addWidget(self._build_hero())

        root.addWidget(self._build_controls())
        root.addWidget(self._build_terminal(), 1)
        root.addWidget(self._build_library())

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_library)
        self._refresh_timer.start(5000)
        self._refresh_library()

        self._set_running(False)
        self._log("Manga Factory is ready. Paste a chapter URL and run the deck.")

    def _build_hero(self):
        hero = QFrame()
        hero.setObjectName("Hero")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(22, 18, 22, 18)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        kicker = QLabel("LOCAL PIPELINE CONSOLE")
        kicker.setObjectName("AppKicker")
        title = QLabel("MANGA FACTORY")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Reader capture, cleanup, stitching, OCR, scripts, and PDF output in one honest desktop surface.")
        subtitle.setObjectName("AppSubtitle")
        subtitle.setWordWrap(True)
        title_col.addWidget(kicker)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        self.status_pill = QLabel("IDLE")
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.pet_stage = PixelPetStage()
        self.pet_activity = QLabel("INKBIT // READY")
        self.pet_activity.setObjectName("PetActivity")
        self.pet_activity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pet_column = QVBoxLayout()
        pet_column.setSpacing(4)
        pet_column.addWidget(self.pet_stage)
        pet_column.addWidget(self.pet_activity)
        layout.addLayout(title_col, 1)
        layout.addLayout(pet_column, 0)
        layout.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        return hero

    def _build_controls(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        source = SectionBox(
            "Chapter Queue",
            "Paste one reader URL per line. With one link, Chapters resolves real reader navigation; with many links, each pasted URL runs exactly as written.",
        )
        self.url_in = QPlainTextEdit()
        self.url_in.setObjectName("UrlInput")
        self.url_in.setPlaceholderText(
            "https://roliascan.com/read/.../ch1-32984/\n"
            "https://roliascan.com/read/.../ch2-33001/"
        )
        self.url_in.setFixedHeight(100)
        self.url_in.setTabChangesFocus(True)
        source.add_widget(self.url_in)

        queue_tools = QHBoxLayout()
        self.preview_queue_btn = QPushButton("Preview Queue")
        self.preview_queue_btn.setObjectName("GhostBtn")
        self.preview_queue_btn.clicked.connect(self._preview_queue)
        self.resolve_chapters_btn = QPushButton("Resolve Chapters")
        self.resolve_chapters_btn.setObjectName("GhostBtn")
        self.resolve_chapters_btn.clicked.connect(self._resolve_chapters)
        self.import_urls_btn = QPushButton("Import URL List")
        self.import_urls_btn.setObjectName("GhostBtn")
        self.import_urls_btn.clicked.connect(self._import_url_list)
        self.clear_urls_btn = QPushButton("Clear Queue")
        self.clear_urls_btn.setObjectName("GhostBtn")
        self.clear_urls_btn.clicked.connect(self._clear_url_queue)
        queue_tools.addWidget(self.preview_queue_btn)
        queue_tools.addWidget(self.resolve_chapters_btn)
        queue_tools.addWidget(self.import_urls_btn)
        queue_tools.addWidget(self.clear_urls_btn)
        queue_tools.addStretch(1)
        source.add_layout(queue_tools)

        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("Series output name (optional)")
        source.add_widget(self.name_in)

        count_row = QHBoxLayout()
        self.ch_count = QSpinBox()
        self.ch_count.setRange(1, 999)
        self.ch_count.setValue(1)
        self.ch_count.setToolTip("For one URL, choose how many real chapter links to resolve. URL templates and pasted chapter lists also work.")
        count_row.addWidget(QLabel("Chapters"))
        count_row.addWidget(self.ch_count)
        self.parallel_count = QSpinBox()
        self.parallel_count.setRange(1, 3)
        self.parallel_count.setValue(3)
        self.parallel_count.setToolTip("Maximum simultaneous chapter browsers")
        count_row.addWidget(QLabel("Parallel"))
        count_row.addWidget(self.parallel_count)
        self.retry_count = QSpinBox()
        self.retry_count.setRange(0, 3)
        self.retry_count.setValue(1)
        self.retry_count.setToolTip("Extra download attempts before a chapter is marked failed")
        count_row.addWidget(QLabel("Retries"))
        count_row.addWidget(self.retry_count)
        source.add_layout(count_row)

        account_row = QHBoxLayout()
        self.profile_in = QLineEdit()
        self.profile_in.setText("account")
        self.profile_in.setPlaceholderText("Browser account group")
        self.profile_in.setToolTip(
            "Creates isolated profiles such as account_1, account_2, and account_3"
        )
        account_row.addWidget(QLabel("Accounts"))
        account_row.addWidget(self.profile_in, 1)
        source.add_layout(account_row)

        path_row = QHBoxLayout()
        self.dir_in = QLineEdit()
        self.dir_in.setText(str(Path.home() / "Desktop" / "MangaOutput"))
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("GhostBtn")
        self.browse_btn.clicked.connect(self._browse_output)
        path_row.addWidget(self.dir_in, 1)
        path_row.addWidget(self.browse_btn)
        source.add_layout(path_row)

        action_row = QHBoxLayout()
        self.run_btn = QPushButton("Run Queue")
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.clicked.connect(self._start_process)
        self.stop_btn = QPushButton("Finish Current Step")
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.clicked.connect(self._request_stop)
        action_row.addWidget(self.run_btn, 2)
        action_row.addWidget(self.stop_btn, 1)
        source.add_layout(action_row)
        layout.addWidget(source)

        modules = SectionBox(
            "Studio Powers",
            "Every enabled control maps directly to the worker. Full-strip scenes stay the source for panel, dialogue, script, and video output.",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(42)
        grid.setVerticalSpacing(8)

        capture_label = QLabel("CAPTURE & BROWSER")
        capture_label.setObjectName("GroupLabel")
        output_label = QLabel("PANELS & OUTPUT")
        output_label.setObjectName("GroupLabel")
        grid.addWidget(capture_label, 0, 0)
        grid.addWidget(output_label, 0, 1)

        self.chk_force_dl = QCheckBox("Force redownload")
        self.chk_human = QCheckBox("Human browser behavior")
        self.chk_adblock = QCheckBox("Popup cleanup")
        self.chk_stitch = QCheckBox("Stitch strips")
        self.chk_stitch_individual = QCheckBox("Cut panels from full strip")
        self.chk_headful = QCheckBox("Headful account browsers")
        self.chk_browser_only = QCheckBox("Browser-only capture")
        self.chk_ml = QCheckBox("Active learning hook")
        self.chk_learn_chars = QCheckBox("Build character context")
        self.chk_analyze_scenes = QCheckBox("Scene + speaker map")
        self.chk_ocr = QCheckBox("Skip OCR")
        self.chk_clean = QCheckBox("Skip cleaning")
        self.chk_slice = QCheckBox("Skip slicing")
        self.chk_pdf = QCheckBox("Generate PDF")
        self.chk_ai = QCheckBox("AI script")
        self.chk_emotion = QCheckBox("Emotion tags")

        for checkbox in (
            self.chk_human,
            self.chk_adblock,
            self.chk_stitch,
            self.chk_stitch_individual,
            self.chk_headful,
            self.chk_browser_only,
            self.chk_pdf,
            self.chk_emotion,
            self.chk_ml,
            self.chk_learn_chars,
            self.chk_analyze_scenes,
            self.chk_ai,
        ):
            checkbox.setChecked(True)

        capture_toggles = [
            self.chk_force_dl,
            self.chk_human,
            self.chk_adblock,
            self.chk_headful,
            self.chk_browser_only,
            self.chk_clean,
        ]
        output_toggles = [
            self.chk_stitch,
            self.chk_stitch_individual,
            self.chk_slice,
            self.chk_ocr,
            self.chk_pdf,
            self.chk_emotion,
            self.chk_ml,
            self.chk_ai,
            self.chk_learn_chars,
            self.chk_analyze_scenes,
        ]
        for row, checkbox in enumerate(capture_toggles, start=1):
            grid.addWidget(checkbox, row, 0)
        for row, checkbox in enumerate(output_toggles, start=1):
            grid.addWidget(checkbox, row, 1)
        self.pipeline_toggles = capture_toggles + output_toggles

        self.ch_count.valueChanged.connect(self._sync_control_state)
        self.retry_count.valueChanged.connect(self._sync_control_state)
        self.url_in.textChanged.connect(self._sync_control_state)
        self.chk_stitch.toggled.connect(self._sync_control_state)
        self.chk_slice.toggled.connect(self._sync_control_state)
        self.chk_ocr.toggled.connect(self._sync_control_state)
        modules.add_layout(grid)
        layout.addWidget(modules)
        return panel

    def _build_terminal(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        queue_box = SectionBox(
            "Run Queue",
            "Queued chapters keep their own status while up to three isolated browser profiles work in parallel.",
        )
        self.job_list = QListWidget()
        self.job_list.setObjectName("QueueList")
        self.job_list.setMinimumHeight(108)
        self.job_list.setMaximumHeight(220)
        queue_box.add_widget(self.job_list)
        layout.addWidget(queue_box)

        stats_box = SectionBox("Live Output", "Counts come from the active chapter output folders as each phase completes.")
        stats_grid = QGridLayout()
        stats_grid.setSpacing(10)
        self.stats = {
            "raw": StatBox("raw"),
            "clean": StatBox("clean"),
            "parts": StatBox("strip parts"),
            "scenes": StatBox("video scenes"),
            "panels": StatBox("panels"),
            "scripts": StatBox("scripts"),
            "pdf": StatBox("pdf"),
            "chapter": StatBox("chapter", "-"),
        }
        for idx, stat in enumerate(self.stats.values()):
            stats_grid.addWidget(stat, idx // 3, idx % 3)
        stats_box.add_layout(stats_grid)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        stats_box.add_widget(self.progress)
        self.current_path = QLabel("No output yet")
        self.current_path.setObjectName("PathLabel")
        self.current_path.setWordWrap(True)
        stats_box.add_widget(self.current_path)
        artifact_row = QHBoxLayout()
        self.open_panels_btn = QPushButton("Open Panels")
        self.open_panels_btn.setObjectName("GhostBtn")
        self.open_panels_btn.clicked.connect(lambda: self._open_run_artifact("panels"))
        self.open_scenes_btn = QPushButton("Open Scenes")
        self.open_scenes_btn.setObjectName("GhostBtn")
        self.open_scenes_btn.clicked.connect(lambda: self._open_run_artifact("scenes"))
        self.open_strip_btn = QPushButton("Open Full Strip")
        self.open_strip_btn.setObjectName("GhostBtn")
        self.open_strip_btn.clicked.connect(lambda: self._open_run_artifact("strip"))
        self.open_pdf_btn = QPushButton("Open PDF")
        self.open_pdf_btn.setObjectName("GhostBtn")
        self.open_pdf_btn.clicked.connect(lambda: self._open_run_artifact("pdf"))
        self.open_script_btn = QPushButton("Open Script")
        self.open_script_btn.setObjectName("GhostBtn")
        self.open_script_btn.clicked.connect(lambda: self._open_run_artifact("script"))
        self.open_characters_btn = QPushButton("Open Characters")
        self.open_characters_btn.setObjectName("GhostBtn")
        self.open_characters_btn.clicked.connect(lambda: self._open_run_artifact("characters"))
        artifact_row.addStretch(1)
        artifact_row.addWidget(self.open_scenes_btn)
        artifact_row.addWidget(self.open_panels_btn)
        artifact_row.addWidget(self.open_strip_btn)
        artifact_row.addWidget(self.open_pdf_btn)
        artifact_row.addWidget(self.open_script_btn)
        artifact_row.addWidget(self.open_characters_btn)
        stats_box.add_layout(artifact_row)
        layout.addWidget(stats_box)

        terminal = SectionBox("Real Terminal", "Backend logger output streams here while the worker runs.")
        toolbar = QHBoxLayout()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("GhostBtn")
        self.clear_btn.clicked.connect(self._clear_terminal)
        self.open_log_btn = QPushButton("Open Log")
        self.open_log_btn.setObjectName("GhostBtn")
        self.open_log_btn.clicked.connect(self._open_last_log)
        toolbar.addStretch(1)
        toolbar.addWidget(self.clear_btn)
        toolbar.addWidget(self.open_log_btn)
        terminal.add_layout(toolbar)

        self.log_panel = QPlainTextEdit()
        self.log_panel.setObjectName("LogPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumBlockCount(1200)
        self.log_panel.setMinimumHeight(320)
        terminal.add_widget(self.log_panel)
        layout.addWidget(terminal, 1)
        return panel

    def _build_library(self):
        library = SectionBox("Library", "Recent series folders from the configured output path.")
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("GhostBtn")
        self.refresh_btn.clicked.connect(self._refresh_library)
        self.open_selected_btn = QPushButton("Open Selected")
        self.open_selected_btn.setObjectName("GhostBtn")
        self.open_selected_btn.clicked.connect(self._open_selected_folder)
        self.open_output_btn = QPushButton("Open Output Root")
        self.open_output_btn.setObjectName("GhostBtn")
        self.open_output_btn.clicked.connect(lambda: self._open_path(Path(self.dir_in.text())))
        row.addStretch(1)
        row.addWidget(self.refresh_btn)
        row.addWidget(self.open_selected_btn)
        row.addWidget(self.open_output_btn)
        library.add_layout(row)

        self.lib_list = QListWidget()
        self.lib_list.setMinimumHeight(120)
        self.lib_list.itemDoubleClicked.connect(lambda _item: self._open_selected_folder())
        library.add_widget(self.lib_list)
        return library

    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.browse_btn.setEnabled(not running)
        for control in (
            self.url_in,
            self.name_in,
            self.dir_in,
            self.ch_count,
            self.parallel_count,
            self.retry_count,
            self.profile_in,
            self.preview_queue_btn,
            self.resolve_chapters_btn,
            self.import_urls_btn,
            self.clear_urls_btn,
            *self.pipeline_toggles,
        ):
            control.setEnabled(not running)
        self.status_pill.setText("RUNNING" if running else "IDLE")
        self._set_pet_activity(
            "running-right" if running else "idle",
            "INKBIT // ON THE MOVE" if running else "INKBIT // READY",
        )
        if not running:
            self._sync_control_state()
        self._sync_artifact_buttons()

    def _sync_control_state(self, *_args):
        if self.worker:
            return
        urls = self._collect_urls()
        jobs = WorkerThread.build_jobs(urls, self.ch_count.value())
        count = len(jobs)
        if len(urls) == 1 and self.ch_count.value() > 1:
            self.run_btn.setText(f"Resolve & Run {self.ch_count.value()} Chapters")
        else:
            self.run_btn.setText(
                "Run Queue" if count == 0 else ("Run Chapter" if count == 1 else f"Run {count} Chapters")
            )
        stitch_enabled = self.chk_stitch.isChecked()
        slicing_enabled = not self.chk_slice.isChecked()
        ocr_enabled = not self.chk_ocr.isChecked()
        self.chk_stitch_individual.setEnabled(stitch_enabled and slicing_enabled)
        self.chk_pdf.setEnabled(stitch_enabled)
        self.chk_emotion.setEnabled(ocr_enabled)
        self.chk_ai.setEnabled(ocr_enabled)

    def _collect_urls(self):
        raw_text = self.url_in.toPlainText()
        values = []
        for part in re.split(r"[\n,]+", raw_text):
            value = part.strip()
            if not value or value.startswith("#"):
                continue
            values.append(value)
        return values

    def _normalise_urls(self):
        cleaned = []
        invalid = []
        for value in self._collect_urls():
            if not value.startswith(("http://", "https://")):
                value = "https://" + value
            if "." not in value or " " in value:
                invalid.append(value)
                continue
            cleaned.append(value)
        return cleaned, invalid

    def _populate_job_queue(self, jobs):
        self.job_list.clear()
        self.queue_items = {}
        self.queue_states = {}
        for job in jobs:
            index = int(job["index"])
            item = QListWidgetItem(
                f"{index:02d}  {job['folder']}   QUEUED   {job['url']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.job_list.addItem(item)
            self.queue_items[index] = item
            self.queue_states[index] = "queued"

    def _preview_queue(self):
        urls, invalid = self._normalise_urls()
        urls = self._resolve_chapter_batch(urls)
        jobs = WorkerThread.build_jobs(urls, self.ch_count.value())
        self._populate_job_queue(jobs)
        if invalid:
            self._log("Ignored malformed queue rows: " + ", ".join(invalid))
        if not jobs:
            self._log("Add at least one chapter URL to preview the queue.")
            return
        self._log(f"Queue preview ready: {len(jobs)} chapter job(s), up to {min(3, self.parallel_count.value())} at once.")

    def _resolve_chapters(self):
        urls, invalid = self._normalise_urls()
        if invalid:
            self._log("Ignored malformed queue rows: " + ", ".join(invalid))
        if not urls:
            self._log("Add one valid reader URL before resolving chapters.")
            self._set_pet_activity("waiting", "INKBIT // WAITING FOR A LINK")
            return
        resolved_urls = self._resolve_chapter_batch(urls)
        jobs = WorkerThread.build_jobs(resolved_urls, self.ch_count.value())
        self._populate_job_queue(jobs)

    def _resolve_chapter_batch(self, urls):
        """Resolve a one-link batch only when the count requests more chapters."""
        if len(urls) != 1 or self.ch_count.value() <= 1:
            return urls

        resolved_urls, note = WorkerThread.resolve_chapter_urls(
            urls,
            self.ch_count.value(),
        )
        if note:
            self._log(note)
        if len(resolved_urls) > 1 and resolved_urls != urls:
            self.url_in.setPlainText("\n".join(resolved_urls))
        return resolved_urls

    def _import_url_list(self):
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            "Import chapter URL list",
            str(Path.home()),
            "Text files (*.txt *.csv);;All files (*)",
        )
        if not filename:
            return
        try:
            content = Path(filename).read_text(encoding="utf-8")
            existing = self.url_in.toPlainText().strip()
            self.url_in.setPlainText(f"{existing}\n{content}".strip())
            self._log(f"Imported chapter queue: {filename}")
            self._preview_queue()
        except Exception as exc:
            self._log(f"Could not import URL list: {exc}")

    def _clear_url_queue(self):
        self.url_in.clear()
        self._populate_job_queue([])
        self._log("Chapter queue cleared.")

    def _sync_artifact_buttons(self):
        chapter_path = self.last_output_path
        self.open_panels_btn.setEnabled(bool(chapter_path and (chapter_path / "panels").exists()))
        self.open_scenes_btn.setEnabled(bool(
            chapter_path and (chapter_path / "02_stitched" / "video_scenes").exists()
        ))
        self.open_strip_btn.setEnabled(bool(
            chapter_path and (chapter_path / "02_stitched" / "complete_manga_strip.png").exists()
        ))
        self.open_pdf_btn.setEnabled(bool(chapter_path and list(chapter_path.glob("*.pdf"))))
        self.open_script_btn.setEnabled(bool(
            chapter_path and (chapter_path / "script" / "chapter.txt").exists()
        ))
        self.open_characters_btn.setEnabled(bool(
            chapter_path and (chapter_path / "script" / "characters.json").exists()
        ))

    def _open_run_artifact(self, artifact):
        if not self.last_output_path:
            self._log("Run a chapter or select output first.")
            return
        if artifact == "scenes":
            target = self.last_output_path / "02_stitched" / "video_scenes"
        elif artifact == "panels":
            target = self.last_output_path / "panels"
        elif artifact == "strip":
            target = self.last_output_path / "02_stitched" / "complete_manga_strip.png"
        elif artifact == "pdf":
            pdf_files = sorted(self.last_output_path.glob("*.pdf"))
            target = pdf_files[0] if pdf_files else self.last_output_path / "Chapter.pdf"
        elif artifact == "script":
            target = self.last_output_path / "script" / "chapter.txt"
        else:
            target = self.last_output_path / "script" / "characters.json"
        self._open_path(target)

    def _log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_panel.appendPlainText(f"{ts}  {msg}")
        self.log_panel.moveCursor(QTextCursor.MoveOperation.End)

    def _clear_terminal(self):
        self.log_panel.clear()
        self._log("Terminal cleared.")

    def _browse_output(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose Manga Factory output folder", self.dir_in.text())
        if chosen:
            self.dir_in.setText(chosen)
            self._refresh_library()

    def _refresh_library(self):
        self.lib_list.clear()
        base = Path(self.dir_in.text()).expanduser()
        if not base.exists():
            item = QListWidgetItem("Output folder does not exist yet")
            item.setData(Qt.ItemDataRole.UserRole, str(base))
            self.lib_list.addItem(item)
            return

        items = []
        try:
            for entry in base.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    items.append((entry.stat().st_mtime, entry))
        except Exception as exc:
            item = QListWidgetItem(f"Could not read output folder: {exc}")
            item.setData(Qt.ItemDataRole.UserRole, str(base))
            self.lib_list.addItem(item)
            return

        items.sort(key=lambda item: item[0], reverse=True)
        if not items:
            item = QListWidgetItem("No series folders yet")
            item.setData(Qt.ItemDataRole.UserRole, str(base))
            self.lib_list.addItem(item)
            return

        for modified, path in items[:40]:
            stamp = datetime.datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{stamp}    {path.name}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.lib_list.addItem(item)

    def _open_selected_folder(self):
        item = self.lib_list.currentItem()
        if not item:
            self._log("Select a library row first.")
            return
        self._open_path(Path(item.data(Qt.ItemDataRole.UserRole)))

    def _open_last_log(self):
        if self.last_log_path and self.last_log_path.exists():
            self._open_path(self.last_log_path)
        else:
            self._log("No run log is available yet.")

    def _open_path(self, path: Path):
        path = path.expanduser()
        if not path.exists():
            self._log(f"Path does not exist: {path}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform == "win32":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self._log(f"Could not open path: {exc}")

    def _start_process(self):
        urls, invalid = self._normalise_urls()
        if not urls:
            self._log("Add at least one valid chapter URL to the queue.")
            self.status_pill.setText("NEEDS URL")
            self._set_pet_activity("waiting", "INKBIT // WAITING FOR A LINK")
            QTimer.singleShot(1600, lambda: self.status_pill.setText("IDLE"))
            return
        if invalid:
            self._log("Ignored malformed queue rows: " + ", ".join(invalid))

        urls = self._resolve_chapter_batch(urls)

        jobs = WorkerThread.build_jobs(urls, self.ch_count.value())
        if not jobs:
            self._log("The queue did not produce any runnable chapter jobs.")
            return

        output_root = Path(self.dir_in.text()).expanduser()
        needs_stitch = (
            self.chk_stitch.isChecked()
            or not self.chk_slice.isChecked()
            or self.chk_pdf.isChecked()
        )
        if needs_stitch and not self.chk_stitch.isChecked():
            self._log("Stitching was enabled for this run because scenes or PDF output require a full strip.")

        self._set_running(True)
        self.progress.setValue(0)
        self._reset_stats()
        self._populate_job_queue(jobs)
        self._log(
            f"Starting {len(jobs)} queued chapter(s) with "
            f"{min(3, self.parallel_count.value(), len(jobs))} browser slot(s)."
        )

        config_options = {
            "urls": urls,
            "series_name": self.name_in.text().strip(),
            "template_count": self.ch_count.value(),
            "parallel_count": self.parallel_count.value(),
            "retry_count": self.retry_count.value(),
            "profile_prefix": self.profile_in.text().strip() or "account",
            "path": output_root,
            "force_dl": self.chk_force_dl.isChecked(),
            "active_learning": self.chk_ml.isChecked(),
            "auto_stitching": needs_stitch,
            "stitch_individual": (
                needs_stitch
                and not self.chk_slice.isChecked()
                and self.chk_stitch_individual.isChecked()
            ),
            "headful_browsers": self.chk_headful.isChecked(),
            "browser_only": self.chk_browser_only.isChecked(),
            "learn_characters": self.chk_learn_chars.isChecked(),
            "analyze_scenes": self.chk_analyze_scenes.isChecked(),
            "human_behavior": self.chk_human.isChecked(),
            "ad_blocker": self.chk_adblock.isChecked(),
            "skip_ocr": self.chk_ocr.isChecked(),
            "skip_clean": self.chk_clean.isChecked(),
            "skip_slice": self.chk_slice.isChecked(),
            "generate_pdf": self.chk_pdf.isChecked(),
            "ai_scripting": self.chk_ai.isChecked() and not self.chk_ocr.isChecked(),
            "emotion_tags": self.chk_emotion.isChecked() and not self.chk_ocr.isChecked(),
        }

        self.worker = WorkerThread(config_options)
        self.worker.progress.connect(self._on_progress)
        self.worker.stats.connect(self._on_stats)
        self.worker.job_update.connect(self._on_job_update)
        self.worker.finished.connect(self._done)
        self.worker.start()

    def _request_stop(self):
        if self.worker:
            self.worker.request_stop()
            self._log("Stop requested. The worker will stop after the current phase.")
            self.status_pill.setText("STOPPING")
            self._set_pet_activity("waiting", "INKBIT // FINISHING THIS STEP")

    def _on_progress(self, msg: str):
        self._log(msg)

    def _on_stats(self, stats: dict):
        for key, value in stats.items():
            if key in self.stats:
                self.stats[key].set_value(value)
        if "progress" in stats:
            self.progress.setValue(int(stats["progress"]))
        if "stage" in stats:
            stage = str(stats["stage"])
            self.status_pill.setText(stage.upper())
            self._sync_pet_stage(stage)
        if "output_path" in stats:
            self.last_output_path = Path(stats["output_path"])
            self.current_path.setText(str(self.last_output_path))
        if "log_path" in stats:
            self.last_log_path = Path(stats["log_path"])
        self._sync_artifact_buttons()

    def _on_job_update(self, update: dict):
        index = int(update.get("index", 0))
        item = self.queue_items.get(index)
        if not item:
            return
        status = str(update.get("status", "queued")).upper()
        folder = str(update.get("folder", f"Chapter_{index}"))
        url = str(update.get("url", ""))
        item.setText(f"{index:02d}  {folder}   {status}   {url}")
        self.queue_states[index] = status.lower()
        if status in {"FAILED", "ERROR"}:
            self._set_pet_activity("failed", "INKBIT // NEEDS A HAND")
        elif status == "COMPLETE":
            self._set_pet_activity("jumping", "INKBIT // CHAPTER READY")
        elif status == "STARTING":
            self._set_pet_activity("running-right", "INKBIT // OPENING CHAPTER")

    def _done(self):
        self._set_running(False)
        self.progress.setValue(100 if self.progress.value() > 0 else 0)
        complete = sum(state == "complete" for state in self.queue_states.values())
        failed = sum(state == "failed" for state in self.queue_states.values())
        stopped = sum(state == "stopped" for state in self.queue_states.values())
        self._log(
            f"Run finished: {complete} complete, {failed} failed, {stopped} stopped."
        )
        self._set_pet_activity(
            "waving" if complete else "idle",
            "INKBIT // CHAPTER READY" if complete else "INKBIT // READY",
        )
        QTimer.singleShot(1800, lambda: self._set_pet_activity("idle", "INKBIT // READY"))
        self._refresh_library()
        self.worker = None

    def _reset_stats(self):
        for key, stat in self.stats.items():
            stat.set_value("-" if key == "chapter" else "0")
        self.current_path.setText("No output yet")

    def _sync_pet_stage(self, stage: str):
        stage = stage.strip().lower()
        if stage in {"error", "failed", "pdf error"}:
            self._set_pet_activity("failed", "INKBIT // NEEDS A HAND")
        elif stage in {"stopped", "stopping"}:
            self._set_pet_activity("waiting", "INKBIT // PAUSING SAFELY")
        elif stage == "chapter":
            self._set_pet_activity("running-right", "INKBIT // OPENING CHAPTER")
        elif stage == "download":
            self._set_pet_activity("running-right", "INKBIT // FETCHING PAGES")
        elif stage == "downloaded":
            self._set_pet_activity("running-right", "INKBIT // PAGES SECURED")
        elif stage == "cleaning":
            self._set_pet_activity("running", "INKBIT // CLEANING PAGES")
        elif stage == "cleaned":
            self._set_pet_activity("running", "INKBIT // PAGES READY")
        elif stage == "stitching":
            self._set_pet_activity("running", "INKBIT // STITCHING THE STRIP")
        elif stage == "stitched":
            self._set_pet_activity("running", "INKBIT // STRIP READY")
        elif stage == "slicing":
            self._set_pet_activity("review", "INKBIT // CUTTING SCENES")
        elif stage == "sliced":
            self._set_pet_activity("review", "INKBIT // SCENES READY")
        elif stage == "ocr":
            self._set_pet_activity("review", "INKBIT // READING DIALOGUE")
        elif stage == "text":
            self._set_pet_activity("review", "INKBIT // MAPPING DIALOGUE")
        elif stage == "context":
            self._set_pet_activity("review", "INKBIT // MAPPING CHARACTERS")
        elif stage == "script":
            self._set_pet_activity("running", "INKBIT // WRITING SCRIPT")
        elif stage == "pdf":
            self._set_pet_activity("running", "INKBIT // BINDING PDF")
        elif stage in {"complete", "done"}:
            self._set_pet_activity("jumping", "INKBIT // CHAPTER READY")

    def _set_pet_activity(self, state: str, activity: str):
        self.pet_stage.set_state(state)
        self.pet_activity.setText(activity)


class WorkerThread(QThread):
    finished = pyqtSignal()
    progress = pyqtSignal(str)
    stats = pyqtSignal(dict)
    job_update = pyqtSignal(dict)

    def __init__(self, config_options):
        super().__init__()
        self.config_options = config_options
        self._stop_requested = False
        self._progress_lock = threading.Lock()
        self._job_progress = {}
        self._job_urls = {}

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        if not EnhancedMangaFactory:
            self.progress.emit("Backend not found: manga_factory_enhanced.py")
            self.finished.emit()
            return

        try:
            url_targets, discovery_note = self.resolve_chapter_urls(
                self.config_options["urls"],
                self.config_options["template_count"],
            )
            if discovery_note:
                self.progress.emit(discovery_note)
            series_name = self._series_name(url_targets[0], self.config_options["series_name"])
            base_path = self.config_options["path"]
            jobs = self.build_jobs(url_targets, self.config_options["template_count"])

            if not jobs:
                self.progress.emit("No valid chapter jobs were created.")
                return

            if len(url_targets) == 1 and len(jobs) < self.config_options["template_count"]:
                self.progress.emit(
                    "Batch count reduced: use {chapter} or paste one exact reader URL per line."
                )

            parallel_count = min(
                max(1, self.config_options["parallel_count"]),
                len(jobs),
                3,
            )
            self._job_progress = {index: 0 for index in range(1, len(jobs) + 1)}
            self._job_urls = {job["index"]: job["url"] for job in jobs}
            for job in jobs:
                self.job_update.emit({
                    "index": job["index"],
                    "folder": job["folder"],
                    "url": job["url"],
                    "status": "queued",
                })
            profile_pool = queue.Queue()
            for slot in range(1, parallel_count + 1):
                profile_pool.put(f"{self.config_options['profile_prefix']}_{slot}")

            shared_proxy = None
            if self.config_options["active_learning"] and MLProxyManager:
                try:
                    shared_proxy = MLProxyManager(data_dir=str(base_path / series_name))
                    self.progress.emit("Shared UCB proxy bandit is active.")
                except Exception as exc:
                    self.progress.emit(f"UCB proxy manager unavailable: {exc}")

            shared_pipeline = None
            if self.config_options["active_learning"] and SmartPipelineManager:
                try:
                    shared_pipeline = SmartPipelineManager(data_dir=str(base_path / series_name))
                except Exception as exc:
                    self.progress.emit(f"Pipeline memory unavailable: {exc}")

            browser_mode = "headful account" if self.config_options["headful_browsers"] else "browser"
            self.progress.emit(
                f"Launching {parallel_count} isolated {browser_mode} slot(s)."
            )
            log_handler = self._attach_logger()
            try:
                outcomes = {"complete": 0, "failed": 0, "stopped": 0}
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=parallel_count,
                    thread_name_prefix="manga-chapter",
                ) as executor:
                    futures = [
                        executor.submit(
                            self._run_job,
                            job,
                            len(jobs),
                            series_name,
                            base_path,
                            profile_pool,
                            shared_proxy,
                            shared_pipeline,
                        )
                        for job in jobs
                    ]
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            outcome = future.result()
                            outcomes[outcome] = outcomes.get(outcome, 0) + 1
                        except Exception as exc:
                            self.progress.emit(f"Parallel chapter worker failed: {exc}")
                            outcomes["failed"] += 1
            finally:
                self._detach_logger(log_handler)

            self.stats.emit({"stage": "done", "progress": 100})
            self.progress.emit(
                "Pipeline complete: "
                f"{outcomes['complete']} complete, {outcomes['failed']} failed, "
                f"{outcomes['stopped']} stopped."
            )
        except Exception as exc:
            self.progress.emit(f"Fatal error: {exc}")
            self.stats.emit({"stage": "error"})
            time.sleep(1)
        finally:
            self.finished.emit()

    def _run_job(
        self,
        job,
        total,
        series_name,
        base_path,
        profile_pool,
        shared_proxy,
        shared_pipeline,
    ):
        index = int(job["index"])
        current_url = job["url"]
        if self._stop_requested:
            self.job_update.emit({
                "index": index,
                "folder": job["folder"],
                "url": current_url,
                "status": "stopped",
            })
            return "stopped"

        profile_name = profile_pool.get()
        chapter_name = job["folder"]
        chapter_dir = base_path / series_name / chapter_name
        chapter_dir.mkdir(parents=True, exist_ok=True)
        outcome = "failed"
        self.job_update.emit({
            "index": index,
            "folder": chapter_name,
            "url": current_url,
            "status": "starting",
        })
        self.progress.emit(
            f"[{index}/{total}] {chapter_name} using browser profile {profile_name}"
        )
        self.stats.emit({
            "stage": "chapter",
            "chapter": job["chapter_number"],
            "progress": self._aggregate_progress(),
            "output_path": str(chapter_dir),
            "log_path": str(chapter_dir / "manga_factory_enhanced.log"),
        })

        factory = None
        try:
            factory = EnhancedMangaFactory(
                str(chapter_dir),
                None,
                proxy_manager=shared_proxy,
                pipeline_manager=shared_pipeline,
                browser_profile_name=profile_name,
                force_headful_browser=self.config_options["headful_browsers"],
                browser_only=self.config_options["browser_only"],
                enable_source_learning=self.config_options["active_learning"],
            )
            factory.enable_human_behavior = self.config_options["human_behavior"]
            factory.enable_ad_blocker = self.config_options["ad_blocker"]
            outcome = self._run_chapter(factory, current_url, chapter_dir, index, total)
        except Exception as exc:
            self.progress.emit(f"{chapter_name} failed unexpectedly: {exc}")
            outcome = "failed"
        finally:
            if factory:
                try:
                    factory.cleanup()
                except Exception:
                    pass
            with self._progress_lock:
                self._job_progress[index] = 100
            profile_pool.put(profile_name)
        self.job_update.emit({
            "index": index,
            "folder": chapter_name,
            "url": current_url,
            "status": outcome,
        })
        return outcome

    def _run_chapter(self, factory, current_url: str, chapter_dir: Path, index: int, total: int):
        raw_dir = factory.dirs["raw"]
        has_files = raw_dir.exists() and any(raw_dir.iterdir())

        if has_files and not self.config_options["force_dl"]:
            self.progress.emit("Download skipped because raw files already exist.")
        else:
            self._emit_stage(factory, chapter_dir, "download", index, total, 5)
            downloaded = False
            attempts = max(1, int(self.config_options["retry_count"]) + 1)
            for attempt in range(1, attempts + 1):
                self.progress.emit(
                    f"Downloading from {current_url} (attempt {attempt}/{attempts})"
                )
                if factory.download_chapter(current_url):
                    downloaded = True
                    break
                if attempt < attempts:
                    delay = min(8, attempt * 2)
                    self.progress.emit(
                        f"Download attempt {attempt} failed; retrying in {delay}s."
                    )
                    time.sleep(delay)
            if not downloaded:
                self.progress.emit("Download failed after all attempts; chapter skipped.")
                self._emit_stage(factory, chapter_dir, "failed", index, total, 18)
                return "failed"
        self._emit_stage(factory, chapter_dir, "downloaded", index, total, 20)
        if self._should_stop("after download"):
            return "stopped"

        if self.config_options["skip_clean"]:
            self.progress.emit("Cleaning skipped by switch.")
        else:
            self._emit_stage(factory, chapter_dir, "cleaning", index, total, 30)
            cleaned_files = factory.clean_pages_enhanced()
            if not cleaned_files:
                self.progress.emit("Cleaning produced no usable images; chapter skipped.")
                self._emit_stage(factory, chapter_dir, "failed", index, total, 35)
                return "failed"
        self._emit_stage(factory, chapter_dir, "cleaned", index, total, 40)
        if self._should_stop("after cleaning"):
            return "stopped"

        if self.config_options["auto_stitching"]:
            self._emit_stage(factory, chapter_dir, "stitching", index, total, 48)
            stitch_result = factory.process_stitching_enhanced(
                None,
                extract_single_panels=self.config_options["stitch_individual"],
            )
            if stitch_result.get("success"):
                self.progress.emit(
                    f"{chapter_dir.name}: full strip + "
                    f"{stitch_result.get('part_count', 0)} part(s) + "
                    f"{stitch_result.get('video_scene_count', 0)} video scene(s) + "
                    f"{stitch_result.get('panel_count', 0)} archival cut(s)"
                )
            else:
                self.progress.emit(
                    f"{chapter_dir.name}: stitching failed: {stitch_result.get('error', 'unknown error')}"
                )
                self._emit_stage(factory, chapter_dir, "failed", index, total, 55)
                return "failed"
        else:
            self.progress.emit("Stitching skipped by switch.")
        self._emit_stage(factory, chapter_dir, "stitched", index, total, 55)
        if self._should_stop("after stitching"):
            return "stopped"

        if self.config_options["skip_slice"]:
            self.progress.emit("Panel slicing skipped by switch.")
        else:
            self._emit_stage(factory, chapter_dir, "slicing", index, total, 62)
            panels = factory.extract_panels_enhanced(skip_validation=False)
            if not panels:
                self.progress.emit("Scene panel extraction produced no usable panels; chapter skipped.")
                self._emit_stage(factory, chapter_dir, "failed", index, total, 68)
                return "failed"
        self._emit_stage(factory, chapter_dir, "sliced", index, total, 70)
        if self._should_stop("after slicing"):
            return "stopped"

        if self.config_options["skip_ocr"]:
            self.progress.emit("OCR skipped by switch.")
        else:
            self._emit_stage(factory, chapter_dir, "ocr", index, total, 76)
            factory.process_ocr_enhanced(ocr_lang="eng")
        self._emit_stage(factory, chapter_dir, "text", index, total, 82)
        if self._should_stop("after OCR"):
            return "stopped"

        if self.config_options["learn_characters"] or self.config_options["analyze_scenes"]:
            self._emit_stage(factory, chapter_dir, "context", index, total, 85)
            self._build_context(
                factory,
                build_characters=self.config_options["learn_characters"],
                build_scene_map=self.config_options["analyze_scenes"],
            )
        if self._should_stop("after optional analysis"):
            return "stopped"

        self._emit_stage(factory, chapter_dir, "script", index, total, 88)
        if self.config_options["ai_scripting"]:
            factory.generate_ai_enhanced_script(chapter_title=chapter_dir.name)
        else:
            factory.generate_script_enhanced(add_emotions=self.config_options["emotion_tags"])

        if self.config_options["active_learning"]:
            self.progress.emit("Shared source-learning memory recorded this chapter's strategy results.")
        else:
            self.progress.emit("Active learning skipped by switch.")

        if self.config_options["generate_pdf"]:
            self._emit_stage(factory, chapter_dir, "pdf", index, total, 94)
            try:
                from pdf_generator import generate_chapter_pdf
                pdf_path = generate_chapter_pdf(str(chapter_dir))
                if not pdf_path:
                    raise RuntimeError("the PDF writer did not produce a file")
                self.progress.emit(f"PDF ready: {pdf_path}")
            except Exception as exc:
                self.progress.emit(f"PDF generation failed: {exc}")
                self.stats.emit({"stage": "pdf error"})
                return "failed"
        else:
            self.progress.emit("PDF generation skipped by switch.")

        self._emit_stage(factory, chapter_dir, "complete", index, total, 100)
        self.progress.emit(f"Chapter {chapter_dir.name} complete.")
        return "complete"

    def _attach_logger(self):
        handler = QtLogHandler(self.progress.emit)
        handler.setLevel(logging.INFO)
        logging.root.addHandler(handler)
        return handler

    @staticmethod
    def _detach_logger(handler):
        try:
            logging.root.removeHandler(handler)
        except Exception:
            pass

    def _emit_stage(self, factory, chapter_dir: Path, stage: str, index: int, total: int, phase_progress: int):
        self.job_update.emit({
            "index": index,
            "folder": chapter_dir.name,
            "url": self._job_urls.get(index, ""),
            "status": stage,
        })
        self.stats.emit({
            "stage": stage,
            "chapter": chapter_dir.name.replace("Chapter_", ""),
            "raw": self._count_files(factory.dirs.get("raw")),
            "clean": self._count_files(factory.dirs.get("clean")),
            "parts": self._count_files(factory.dirs.get("stitched") / "parts"),
            "scenes": self._count_files(factory.dirs.get("stitched") / "video_scenes", {".png"}),
            "panels": self._count_files(factory.dirs.get("panels")),
            "scripts": self._count_files(factory.dirs.get("script"), {".txt", ".json", ".md"}),
            "pdf": self._count_files(chapter_dir, {".pdf"}),
            "progress": self._set_job_progress(index, phase_progress),
            "output_path": str(chapter_dir),
            "log_path": str(chapter_dir / "manga_factory_enhanced.log"),
        })

    @staticmethod
    def _count_files(path, suffixes=None):
        if not path or not Path(path).exists():
            return 0
        suffixes = suffixes or {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
        return sum(1 for item in Path(path).iterdir() if item.is_file() and item.suffix.lower() in suffixes)

    @staticmethod
    def _progress(done_chapters: int, total: int, phase_progress: int):
        total = max(total, 1)
        return min(100, int(((done_chapters + (phase_progress / 100)) / total) * 100))

    def _set_job_progress(self, index: int, phase_progress: int):
        with self._progress_lock:
            self._job_progress[index] = max(
                self._job_progress.get(index, 0),
                int(phase_progress),
            )
            return int(sum(self._job_progress.values()) / max(1, len(self._job_progress)))

    def _aggregate_progress(self):
        with self._progress_lock:
            return int(sum(self._job_progress.values()) / max(1, len(self._job_progress)))

    def _should_stop(self, location: str):
        if self._stop_requested:
            self.progress.emit(f"Stopped {location}.")
            self.stats.emit({"stage": "stopped"})
            return True
        return False

    @staticmethod
    def _series_name(url_target: str, manual_name: str):
        if manual_name:
            return manual_name
        name_match = re.search(r"/(?:manga|series|comic|title|read)/([^/?]+)", url_target)
        if name_match:
            return name_match.group(1).title().replace("-", " ")
        parts = [part for part in url_target.split("/") if part]
        if len(parts) >= 2:
            return parts[-2].title().replace("-", " ")
        from urllib.parse import urlparse
        domain = urlparse(url_target).netloc.replace("www.", "")
        return f"Auto_{domain or 'chapter'}"

    @classmethod
    def resolve_chapter_urls(cls, url_targets, template_count: int, timeout: int = 12):
        """Resolve a one-link batch from a site's own chapter navigation.

        Templates and proven sequential URL patterns stay local. Reader pages with
        non-sequential IDs (for example, RoliaScan) are inspected before jobs are
        created, so the worker never fabricates a chapter URL.
        """
        targets = [str(url).strip() for url in url_targets if str(url).strip()]
        requested = max(1, int(template_count))
        if len(targets) != 1 or requested == 1:
            return targets, None

        local_jobs = cls.build_jobs(targets, requested)
        if len(local_jobs) >= requested:
            return [job["url"] for job in local_jobs], (
                f"Resolved {len(local_jobs)} chapter URL(s) from the URL pattern."
            )

        discovered, error = cls._discover_reader_chapters(targets[0], requested, timeout)
        if len(discovered) >= requested:
            return discovered, (
                f"Resolved {len(discovered)} real chapter URL(s) from reader navigation."
            )
        return targets, (
            error
            or "Could not resolve the requested chapter count; the seed reader URL will run by itself."
        )

    @classmethod
    def _discover_reader_chapters(cls, seed_url: str, count: int, timeout: int):
        if requests is None:
            return [], "Chapter resolver is unavailable because requests is not installed."

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            response = requests.get(
                seed_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception as exc:
            return [], f"Could not inspect reader navigation: {exc}"

        current_url = response.url or seed_url
        chapter_options = cls._chapter_options(response.text, current_url)
        current_key = cls._url_key(current_url)
        for position, option_url in enumerate(chapter_options):
            if cls._url_key(option_url) == current_key:
                resolved = chapter_options[position:position + count]
                if len(resolved) >= count:
                    return resolved, None
                return [], "The reader does not have enough later chapters for the selected count."

        # Some readers expose only Previous/Next controls. Follow real next links
        # rather than synthesising URL IDs.
        resolved = [current_url]
        visited = {current_key}
        page_html = response.text
        while len(resolved) < count:
            next_url = cls._next_reader_url(page_html, current_url)
            if not next_url or cls._url_key(next_url) in visited:
                return [], "The reader does not expose enough next-chapter links for the selected count."
            visited.add(cls._url_key(next_url))
            resolved.append(next_url)
            try:
                response = requests.get(
                    next_url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True,
                )
                response.raise_for_status()
            except Exception as exc:
                return [], f"Could not inspect the next chapter: {exc}"
            current_url = response.url or next_url
            page_html = response.text
        return resolved, None

    @staticmethod
    def _chapter_options(html: str, base_url: str):
        options = []
        seen = set()
        for tag in re.findall(r"<option\b[^>]*>", html, flags=re.IGNORECASE):
            match = re.search(
                r"\bvalue\s*=\s*(['\"])(.*?)\1",
                tag,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not match:
                continue
            url = urljoin(base_url, unescape(match.group(2)).strip())
            key = WorkerThread._url_key(url)
            if key and key not in seen:
                options.append(url)
                seen.add(key)
        return options

    @staticmethod
    def _next_reader_url(html: str, base_url: str):
        for tag in re.findall(r"<(?:link|a)\b[^>]*>", html, flags=re.IGNORECASE):
            rel = re.search(r"\brel\s*=\s*(['\"])(.*?)\1", tag, flags=re.IGNORECASE)
            title = re.search(r"\btitle\s*=\s*(['\"])(.*?)\1", tag, flags=re.IGNORECASE)
            if not (
                (rel and "next" in rel.group(2).lower())
                or (title and "next chapter" in title.group(2).lower())
            ):
                continue
            href = re.search(r"\bhref\s*=\s*(['\"])(.*?)\1", tag, flags=re.IGNORECASE | re.DOTALL)
            if href:
                return urljoin(base_url, unescape(href.group(2)).strip())
        return None

    @staticmethod
    def _url_key(url: str):
        return url.split("#", 1)[0].rstrip("/")

    @classmethod
    def build_jobs(cls, url_targets, template_count: int):
        """Turn pasted URLs into stable, collision-free chapter jobs."""
        targets = [str(url).strip() for url in url_targets if str(url).strip()]
        expanded = []
        for target in targets:
            if "{chapter}" in target:
                expanded.extend(
                    target.replace("{chapter}", str(number))
                    for number in range(1, max(1, int(template_count)) + 1)
                )
            else:
                expanded.append(target)

        if len(expanded) == 1 and template_count > 1 and "{chapter}" not in expanded[0]:
            simple = re.search(
                r"^(.*(?:chapter-|chapter/|chapter_|episode-|episode/|ep-))(\d+)(/?)$",
                expanded[0],
                re.I,
            )
            if simple:
                prefix, start, suffix = simple.groups()
                width = len(start)
                start_number = int(start)
                expanded = [
                    f"{prefix}{str(start_number + offset).zfill(width)}{suffix}"
                    for offset in range(int(template_count))
                ]

        jobs = []
        folder_counts = {}
        for index, url in enumerate(expanded, start=1):
            chapter_number = cls._infer_chapter_number(url, index)
            base_folder = f"Chapter_{chapter_number}"
            folder_counts[base_folder] = folder_counts.get(base_folder, 0) + 1
            occurrence = folder_counts[base_folder]
            folder = (
                base_folder
                if occurrence == 1
                else f"{base_folder}_{occurrence:02d}"
            )
            jobs.append({
                "index": index,
                "url": url,
                "chapter_number": chapter_number,
                "folder": folder,
            })
        return jobs

    @staticmethod
    def _infer_chapter_number(url: str, fallback: int):
        match = re.search(r"(?:chapter|ch|episode|ep)[-_]?(\d+)", url, re.I)
        if match:
            return int(match.group(1))
        return fallback

    def _build_context(self, factory, build_characters: bool, build_scene_map: bool):
        requested = []
        if build_characters:
            requested.append("character profiles")
        if build_scene_map:
            requested.append("scene and speaker map")
        self.progress.emit("Building " + " + ".join(requested) + ".")
        try:
            result = factory.process_dialogue_context_enhanced(reprocess=False)
            stats = result.get("stats", {})
            summary = []
            if build_characters:
                summary.append(
                    f"{stats.get('character_profiles', 0)} character profiles "
                    f"({stats.get('named_character_profiles', 0)} named)"
                )
            if build_scene_map:
                summary.append(
                    f"{stats.get('text_blocks', 0)} text boxes, "
                    f"{stats.get('dark_panels', 0)} dark scenes, "
                    f"{len(stats.get('speakers', {}))} speaker labels"
                )
            self.progress.emit(
                "Context ready: " + "; ".join(summary) +
                f"; memory: {result.get('series_context')}"
            )
        except Exception as exc:
            self.progress.emit(f"Structured context failed: {exc}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = ZineWindow()
    window.show()
    sys.exit(app.exec())
