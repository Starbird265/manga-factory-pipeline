#!/usr/bin/env python3

"""
Enhanced Manga Factory - Bug fixes and improvements
- Fixed OCR preprocessing and accuracy
- Enhanced panel extraction with better boundary detection
- Integrated advanced stitching functionality
- Improved error handling and logging
- Better format detection and processing
- Human-like behavior for natural interactions
- Popup/ad overlay handling
"""

import os
import re
import random
import warnings
# Suppress harmless torch pin_memory warning on MPS
warnings.filterwarnings("ignore", message=".*pin_memory.*not supported on MPS.*")
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import sys
import cv2
import numpy as np
import pytesseract
import json
from collections import Counter
from datetime import datetime
import time
import requests
from bs4 import BeautifulSoup

# Tesseract path resolution (env > PATH > default)
# If TESSERACT_CMD is set, use it; else try PATH; else fallback to Homebrew default
_tess_env = os.environ.get('TESSERACT_CMD')
if _tess_env and os.path.exists(_tess_env):
    pytesseract.pytesseract.tesseract_cmd = _tess_env
else:
    _found_tess = shutil.which('tesseract')
    if _found_tess:
        pytesseract.pytesseract.tesseract_cmd = _found_tess
    else:
        pytesseract.pytesseract.tesseract_cmd = '/opt/homebrew/bin/tesseract'
from PIL import Image, ImageEnhance, ImageFilter
Image.MAX_IMAGE_PIXELS = None
import glob
from pathlib import Path
import logging
import argparse
import configparser
import hashlib
import base64
from datetime import datetime, timedelta

# Selenium & Browser Automation
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ============================================================
# HUMAN BEHAVIOR & POPUP CLOSER (ROOT LEVEL INTEGRATION)
# ============================================================
# Import human behavior simulator for natural cursor/scroll interactions
try:
    from human_behavior import HumanBehavior
    HUMAN_BEHAVIOR_AVAILABLE = True
except ImportError:
    HumanBehavior = None
    HUMAN_BEHAVIOR_AVAILABLE = False

# Import popup closer for handling intrusive ads/overlays
try:
    from popup_closer import PopupCloser
    POPUP_CLOSER_AVAILABLE = True
except ImportError:
    PopupCloser = None
    POPUP_CLOSER_AVAILABLE = False

# AI Script Generation (optional)
try:
    from .ai_script_generator import AIScriptGenerator
    AI_SCRIPT_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    try:
        from ai_script_generator import AIScriptGenerator
        AI_SCRIPT_AVAILABLE = True
    except (ImportError, ModuleNotFoundError):
        AI_SCRIPT_AVAILABLE = False

# Enhanced OCR Processing (optional)
try:
    from .enhanced_ocr import EnhancedOCRProcessor
    ENHANCED_OCR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    try:
        from enhanced_ocr import EnhancedOCRProcessor
        ENHANCED_OCR_AVAILABLE = True
    except (ImportError, ModuleNotFoundError):
        ENHANCED_OCR_AVAILABLE = False

# Try import new character learner
try:
    from .character_learner import CharacterLearner, SceneAnalyzer
    LEARNER_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    try:
        from character_learner import CharacterLearner, SceneAnalyzer
        LEARNER_AVAILABLE = True
    except (ImportError, ModuleNotFoundError):
        LEARNER_AVAILABLE = False

# PDF Generator for creating PDFs from stitched strips
try:
    from .pdf_generator import generate_chapter_pdf
    PDF_GENERATOR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    try:
        from pdf_generator import generate_chapter_pdf
        PDF_GENERATOR_AVAILABLE = True
    except (ImportError, ModuleNotFoundError):
        PDF_GENERATOR_AVAILABLE = False

# License validation system
class LicenseValidator:
    def __init__(self):
        self.license_key = None
        self.machine_id = self._get_machine_id()
        self.license_file = Path.home() / '.manga_factory_license'
        
    def _get_machine_id(self):
        """Generate unique machine identifier"""
        try:
            import uuid
            mac = uuid.getnode()
            hostname = os.uname().nodename if hasattr(os, 'uname') else 'unknown'
            combined = f"{mac}-{hostname}"
            return hashlib.sha256(combined.encode()).hexdigest()[:16]
        except Exception:
            return hashlib.sha256('fallback-machine-id'.encode()).hexdigest()[:16]
    
    def _validate_license_format(self, license_key):
        """Validate license key format and signature"""
        try:
            if not license_key or len(license_key) != 32:
                return False
            
            # Extract components from license key
            machine_part = license_key[:8]
            date_part = license_key[8:16] 
            signature = license_key[16:32]
            
            # Verify machine binding
            expected_machine = self.machine_id[:8]
            if machine_part != expected_machine:
                return False
                
            # Verify signature
            payload = f"{machine_part}{date_part}manga_factory_pro"
            expected_sig = hashlib.md5(payload.encode()).hexdigest()[:16]
            
            return signature == expected_sig
            
        except Exception:
            return False
    
    def _check_license_expiry(self, license_key):
        """Check if license is still valid (not expired)"""
        try:
            date_part = license_key[8:16]
            # Convert hex to timestamp
            timestamp = int(date_part, 16)
            license_date = datetime.fromtimestamp(timestamp)
            
            # Check if license is within valid period (1 year from issue)
            expiry_date = license_date + timedelta(days=365)
            return datetime.now() < expiry_date
            
        except Exception:
            return False
    
    def validate_license(self, license_key=None):
        """Main license validation function"""
        if license_key:
            self.license_key = license_key
        elif self.license_file.exists():
            try:
                with open(self.license_file, 'r') as f:
                    self.license_key = f.read().strip()
            except Exception:
                return False, "Cannot read license file"
        else:
            return False, "No license key provided"
        
        if not self.license_key:
            return False, "Empty license key"
            
        if not self._validate_license_format(self.license_key):
            return False, "Invalid license key format or machine binding"
            
        if not self._check_license_expiry(self.license_key):
            return False, "License has expired"
            
        return True, "License valid"
    
    def save_license(self, license_key):
        """Save license key to file"""
        try:
            with open(self.license_file, 'w') as f:
                f.write(license_key)
            return True
        except Exception:
            return False
    
    def generate_license_for_machine(self):
        """Generate a valid license for current machine (for development/testing)"""
        machine_part = self.machine_id[:8]
        timestamp = int(datetime.now().timestamp())
        date_part = f"{timestamp:08x}"
        
        payload = f"{machine_part}{date_part}manga_factory_pro"
        signature = hashlib.md5(payload.encode()).hexdigest()[:16]
        
        return f"{machine_part}{date_part}{signature}"

# Global license validator
license_validator = LicenseValidator()

# Advanced stitching functionality (simplified inline)
class SimpleStitching:
    def __init__(self, chapter_dir):
        self.chapter_dir = chapter_dir

    def process_stitching(self, force_format=None, chunk_by_panels=True, min_panels_per_chunk=5, max_panels_per_chunk=10, extract_single_panels=False):
        """Create a stitched strip from 01_clean images into 02_stitched/.
        If chunk_by_panels is True, split the stitched strip into multiple parts at safe scene (panel) boundaries.
        If extract_single_panels is True, ALSO save each detected panel as a separate image.
        Returns a dict: {'success': bool, 'format_detected': 'webtoon'|'manga'|None, 'output_files': [paths]}
        """
        import glob
        import os
        import re
        import cv2
        import numpy as np

        def _natural_sort_key(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'([0-9]+)', text)]

        def estimate_vertical_overlap(img_a, img_b, max_strip=300, min_overlap=30, diff_threshold=0.04):
            """Intelligently estimate vertical overlap between two images (tighter)"""
            try:
                ha, wa = img_a.shape[:2]
                hb, wb = img_b.shape[:2]
                if ha < min_overlap or hb < min_overlap:
                    return 0
                common_w = min(wa, wb)
                xa = (wa - common_w) // 2
                xb = (wb - common_w) // 2
                strip = min(max_strip, ha, hb)
                a_strip = cv2.cvtColor(img_a[ha - strip:ha, xa:xa + common_w], cv2.COLOR_BGR2GRAY)
                b_strip = cv2.cvtColor(img_b[0:strip, xb:xb + common_w], cv2.COLOR_BGR2GRAY)
                best_k = 0
                # Use stride of 1 for maximum precision (toughter/tighter stitching)
                for k in range(strip, min_overlap - 1, -1):
                    a_part = a_strip[strip - k:strip, :]
                    b_part = b_strip[0:k, : ]
                    if a_part.shape != b_part.shape or a_part.size == 0:
                        continue
                    diff = float(np.mean(cv2.absdiff(a_part, b_part))) / 255.0
                    if diff <= diff_threshold:
                        best_k = k
                        break
                return best_k
            except Exception:
                return 0

        def _is_dark_bg(gray, margin=20, thresh=70):
            try:
                h, w = gray.shape[:2]
                m = max(1, min(margin, h // 50))
                top = gray[:m, :]
                bot = gray[-m:, :]
                border_mean = 0.5 * (float(top.mean()) + float(bot.mean()))
                return border_mean < thresh
            except Exception:
                return False

        def _detect_panel_y_ranges(full_img):
            """Detect vertical panel (scene) spans in a stitched webtoon strip. Returns list of (y_start, y_end)."""
            try:
                h, w = full_img.shape[:2]
                gray = cv2.cvtColor(full_img, cv2.COLOR_BGR2GRAY)
                gray_use = gray
                try:
                    if _is_dark_bg(gray):
                        gray_use = 255 - gray
                except Exception:
                    pass

                row_means = np.mean(gray_use, axis=1)
                white_threshold = 245
                content_rows = row_means < white_threshold
                # Smooth a little to suppress noise
                k = max(3, min(15, h // 3000))
                kernel = np.ones(k, dtype=np.uint8)
                content_rows = np.convolve(content_rows.astype(np.uint8), kernel, mode='same') > (k // 3)

                # Parameters scaled for tall stitched strips
                min_panel_h = max(180, min(1200, h // 60))
                min_gap = max(2, min(20, h // 2000))
                lookahead = max(20, min(120, h // 1000))

                panels = []
                in_panel = False
                s = 0
                i = 0
                while i < h:
                    if content_rows[i] and not in_panel:
                        s = i
                        # refine start into first true content row
                        j = s
                        while j < h and row_means[j] > white_threshold - 20 and (j - s) < lookahead:
                            j += 1
                        s = j
                        in_panel = True
                        i = s
                    elif not content_rows[i] and in_panel:
                        gap_s = i
                        gap_len = 0
                        while i < h and not content_rows[i]:
                            gap_len += 1
                            i += 1
                        if gap_len >= min_gap or i >= h:
                            e = gap_s
                            ph = e - s
                            if ph >= min_panel_h:
                                # refine end
                                content_end = e
                                for j in range(e - 1, max(e - lookahead, s), -1):
                                    if row_means[j] < white_threshold - 30:
                                        content_end = j + 1
                                        break
                                panels.append((max(0, s), min(h, content_end)))
                            in_panel = False
                        else:
                            # small gap, continue current panel
                            i = gap_s + gap_len
                    else:
                        i += 1
                if in_panel:
                    e = h
                    for j in range(h - 1, max(h - lookahead, s), -1):
                        if row_means[j] < white_threshold - 30:
                            e = j + 1
                            break
                    if e - s >= min_panel_h:
                        panels.append((max(0, s), min(h, e)))

                # Fallback using edge-density if very few panels were found
                if len(panels) <= 1:
                    edges = cv2.Canny(gray_use, 50, 150)
                    row_edge = np.mean(edges > 0, axis=1).astype(np.float32)
                    ks = max(3, min(31, h // 800))
                    k1 = np.ones(ks, dtype=np.float32) / max(1, ks)
                    row_s = np.convolve(row_edge, k1, mode='same')
                    thr = max(0.0005, float(row_s.mean()) * 0.6)
                    content_rows2 = row_s > thr
                    panels = []
                    i = 0
                    min_h2 = max(200, min(1200, h // 60))
                    while i < h:
                        if content_rows2[i]:
                            s2 = i
                            while i < h and content_rows2[i]:
                                i += 1
                            e2 = i
                            if e2 - s2 >= min_h2:
                                panels.append((s2, e2))
                        else:
                            i += 1
                # Ensure panels are ordered and non-overlapping
                panels = [(max(0, ys), min(h, ye)) for ys, ye in panels if ye - ys > 30]
                panels.sort(key=lambda t: t[0])
                return panels
            except Exception:
                return []

        def _pick_cut_between(row_means, a_end, b_start):
            """Choose a safe cut line between two panels by picking the whitest row in the gap."""
            if b_start <= a_end:
                return a_end
            seg = row_means[a_end:b_start]
            if seg.size == 0:
                return a_end
            rel = int(np.argmax(seg))
            return a_end + rel

        clean_dir = os.path.join(self.chapter_dir, '01_clean')
        stitched_dir = os.path.join(self.chapter_dir, '02_stitched')
        os.makedirs(stitched_dir, exist_ok=True)

        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
            image_files.extend(glob.glob(os.path.join(clean_dir, ext)))
        if not image_files:
            return {'success': False, 'format_detected': None, 'output_files': []}
        image_files.sort(key=_natural_sort_key)

        processed_images = []
        max_width_found = 0
        max_width = 800

        for img_path in image_files:
            img = cv2.imread(img_path)
            if img is None:
                continue
            h, w = img.shape[:2]
            if h < 10 or w < 10:
                continue
            if h < 50:
                padded_h = max(50, h + 20)
                pad = np.ones((padded_h, w, 3), dtype=np.uint8) * 255
                yoff = (padded_h - h) // 2
                pad[yoff:yoff + h, 0:w] = img
                img = pad
                h = padded_h
            if w > max_width:
                scale = max_width / float(w)
                img = cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
            elif w < max_width // 2:
                pad = np.ones((h, max_width, 3), dtype=np.uint8) * 255
                xoff = (max_width - w) // 2
                pad[:, xoff:xoff + w] = img
                img = pad
            processed_images.append(img)
            max_width_found = max(max_width_found, img.shape[1])

        if not processed_images:
            return {'success': False, 'format_detected': None, 'output_files': []}

        overlaps = [0] * len(processed_images)
        for i in range(1, len(processed_images)):
            overlaps[i] = estimate_vertical_overlap(processed_images[i - 1], processed_images[i])
        effective_total_h = sum(im.shape[0] for im in processed_images) - sum(overlaps)
        if effective_total_h <= 0:
            return {'success': False, 'format_detected': None, 'output_files': []}

        try:
            stitched = np.full((effective_total_h, max_width_found, 3), 255, dtype=np.uint8)
            cur_y = 0
            for idx, im in enumerate(processed_images):
                skip = max(0, min(overlaps[idx], im.shape[0] - 1)) if idx > 0 else 0
                part = im[skip:, :]
                h, w = part.shape[:2]
                xoff = (max_width_found - w) // 2
                stitched[cur_y:cur_y + h, xoff:xoff + w] = part
                cur_y += h

            # Heuristic format detection
            fmt = 'webtoon' if stitched.shape[0] / max(1, stitched.shape[1]) > 2.5 else 'manga'

            # ALWAYS save the complete manga strip as requested
            complete_strip_path = os.path.join(stitched_dir, 'complete_manga_strip.png')
            cv2.imwrite(complete_strip_path, stitched)
            
            output_files = []
            # We always add the complete strip to the output files so it's tracked
            output_files.append(complete_strip_path)

            # Generate PDF from the complete stitched strip
            pdf_path = None
            if PDF_GENERATOR_AVAILABLE:
                try:
                    pdf_path = generate_chapter_pdf(self.chapter_dir)
                    if pdf_path:
                        logger.info(f"✓ PDF generated successfully: {pdf_path}")
                except Exception as e:
                    logger.warning(f"PDF generation failed (non-critical): {e}")
            
            if chunk_by_panels:
                # Compute gray and row_means once for cut selection
                gray_full = cv2.cvtColor(stitched, cv2.COLOR_BGR2GRAY)
                gray_use_full = gray_full
                try:
                    if _is_dark_bg(gray_full):
                        gray_use_full = 255 - gray_full
                except Exception:
                    pass
                row_means_full = np.mean(gray_use_full, axis=1)

                y_ranges = _detect_panel_y_ranges(stitched)
                if y_ranges:
                    n = len(y_ranges)
                    ideal = max(min_panels_per_chunk, min(max_panels_per_chunk, (min_panels_per_chunk + max_panels_per_chunk) // 2))
                    start_y = 0
                    part_idx = 1
                    i = 0
                    while i < n:
                        remain = n - i
                        if remain <= max_panels_per_chunk:
                            end_idx = n - 1
                        else:
                            # Avoid tiny trailing group smaller than min_panels_per_chunk
                            if remain - ideal < min_panels_per_chunk:
                                end_idx = i + (remain - min_panels_per_chunk) - 1
                            else:
                                end_idx = i + ideal - 1
                        group_end_y = y_ranges[end_idx][1]
                        if end_idx + 1 < n:
                            next_start_y = y_ranges[end_idx + 1][0]
                            cut_y = _pick_cut_between(row_means_full, group_end_y, next_start_y)
                        else:
                            cut_y = group_end_y
                        # Write part if large enough
                        if cut_y - start_y > 50:
                            out_path = os.path.join(stitched_dir, f'stitched_part_{part_idx:03d}.png')
                            cv2.imwrite(out_path, stitched[start_y:cut_y, :])
                            output_files.append(out_path)
                            part_idx += 1
                        start_y = cut_y
                        i = end_idx + 1

                # Extract individual panels if requested
                if extract_single_panels and y_ranges:
                    stitched_panels_dir = os.path.join(stitched_dir, 'panels')
                    os.makedirs(stitched_panels_dir, exist_ok=True)
                    
                    p_idx = 1
                    for (ys, ye) in y_ranges:
                        if ye - ys > 50:
                            p_out = os.path.join(stitched_panels_dir, f'panel_{p_idx:03d}.png')
                            cv2.imwrite(p_out, stitched[ys:ye, :])
                            p_idx += 1
                    
            return {'success': True, 'format_detected': fmt, 'output_files': output_files}
        except Exception:
            return {'success': False, 'format_detected': None, 'output_files': []}

# Enhanced logging setup
def setup_logging(chapter_dir=None, log_level=logging.INFO):
    """Setup enhanced logging with both file and console output"""
    if chapter_dir:
        log_file = os.path.join(chapter_dir, 'manga_factory_enhanced.log')
    else:
        log_file = 'manga_factory_enhanced.log'
    
    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    simple_formatter = logging.Formatter("%(levelname)s - %(message)s")
    
    # File handler with detailed logs
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Console handler with simple logs
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(simple_formatter)
    
    # Configure root logger
    logging.root.setLevel(logging.DEBUG)
    logging.root.addHandler(file_handler)
    logging.root.addHandler(console_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# Import optional dependencies with fallbacks
try:
    import text2emotion as te
    EMOTION_AVAILABLE = True
except ImportError:
    te = None
    EMOTION_AVAILABLE = False
    logger.info("text2emotion not available, emotion analysis will use fallback methods")

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.info("transformers/peft not available, some advanced features will be limited")

try:
    import torch
except ImportError:
    torch = None

try:
    import easyocr
    EASYOCR_AVAILABLE = True
    logger.info("EasyOCR available for enhanced text recognition")
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.info("EasyOCR not available, using Tesseract only")

class EnhancedMangaFactory:
    """Enhanced Manga Factory with improved processing and error handling"""
    
    def __init__(self, chapter_dir, config_file=None, mode='manga'):
        self.chapter_dir = Path(chapter_dir)
        self.chapter_dir.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.dirs = {} # Will be populated by _setup_directories
        
        # Setup logging for this chapter
        self.logger = setup_logging(str(self.chapter_dir))
        
        # Load configuration
        self.config = self._load_config(config_file)
        
        # Initialize directories
        self._setup_directories()
        
        # Initialize OCR readers
        self._setup_ocr()
        
        # Initialize simple stitching
        self.stitcher = SimpleStitching(str(self.chapter_dir))
        
        # Initialize ML panel detector (for better panel detection)
        try:
            from panel_ml_detector import create_ml_detector, create_model_trainer
            self.ml_panel_detector = create_ml_detector(self.chapter_dir.parent)
            self.model_trainer = create_model_trainer(self.chapter_dir.parent)
            self.logger.info("✓ ML Panel Detector and Trainer initialized")
        except Exception as e:
            self.ml_panel_detector = None
            self.model_trainer = None
            self.logger.debug(f"ML detector/trainer fallback: {e}")

        # Processing statistics
        self.stats = {
            'downloaded_images': 0,
            'cleaned_images': 0,
            'extracted_panels': 0,
            'valid_panels': 0,
            'ocr_processed': 0,
            'errors': 0
        }
    
    def train_model_if_needed(self):
        """Trigger ML model training if sufficient data has been collected."""
        if not self.ml_panel_detector or not self.model_trainer:
            return

        try:
            if self.ml_panel_detector.check_training_needed():
                self.logger.info("\n" + "="*50)
                self.logger.info("🧠 STARTING AUTOMATIC MODEL TRAINING")
                self.logger.info("="*50)
                self.logger.info("Sufficient new data collected. Fine-tuning model on local GPU...")
                
                success = self.model_trainer.train_model(epochs=5, logger_func=self.logger.info)
                
                if success:
                    self.logger.info("✅ Model training completed successfully!")
                else:
                    self.logger.warning("⚠️ Model training completed with errors (or skipped).")
                self.logger.info("="*50 + "\n")
            else:
                self.logger.info("Skipping model training (insufficient new data)")
                
        except Exception as e:
            self.logger.error(f"Error during automatic training: {e}")

    def _validate_license(self):
        """Skip license validation for open source version"""
        self.logger.info("✅ Running open source version - no license required")
        return
    
    def _load_config(self, config_file=None):
        """Load configuration with sensible defaults"""
        config = configparser.ConfigParser()
        
        # Set defaults
        config['OCR'] = {
            'language': 'eng',
            'confidence_threshold': '60',
            'preprocessing': 'true',
            'use_easyocr': 'true' if EASYOCR_AVAILABLE else 'false'
        }
        config['PROCESSING'] = {
            'auto_format_detection': 'true',
            'advanced_stitching': 'true',
            'panel_validation': 'true',
            'duplicate_threshold': '0.95',
            'stitch_cut_panels': 'true',
            'keep_cut_fragments': 'false',
            # New defaults: scene-aware chunking for stitched strips
            'chunk_stitched_by_panels': 'true',
            'chunk_min_panels_per_part': '5',
            'chunk_max_panels_per_part': '10',
            # Robust handling for dark/black backgrounds
            'robust_dark_background': 'true'
        }
        config['LOGGING'] = {
            'level': 'INFO',
            'detailed_errors': 'true'
        }
        
        # Override for "activate all functions"
        if not os.environ.get('ENABLE_EASYOCR'):
            os.environ['ENABLE_EASYOCR'] = '1'

        
        # Load custom config if provided
        if config_file and os.path.exists(config_file):
            try:
                config.read(config_file)
                self.logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                self.logger.warning(f"Error loading config file {config_file}: {e}")
        
        return config
    
    def _setup_directories(self):
        """Setup ONLY essential directories - no unnecessary folders"""
        self.dirs = {
            'raw': self.chapter_dir / '00_raw',
            'clean': self.chapter_dir / '01_clean', 
            'stitched': self.chapter_dir / '02_stitched',
            'panels': self.chapter_dir / 'panels',  # REAL PANELS ONLY
            'bubbles': self.chapter_dir / 'bubbles',  # floating dialogue / text balloons
            'black': self.chapter_dir / 'black',      # full-dark panels
            'strips': self.chapter_dir / 'strips',    # ultra-wide / ultra-tall strip cuts
            'fragments': self.chapter_dir / 'fragments',  # tiny noise pieces
            'other': self.chapter_dir / 'other',      # uncertain or misc
            'filtered': self.chapter_dir / 'filtered',     # EVERYTHING ELSE (bubbles, fragments, etc.)
            'transcripts': self.chapter_dir / '03_text' / 'transcripts',
            'script': self.chapter_dir / 'script'
        }
        
        # Create only essential directories
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def _setup_ocr(self):
        """Initialize OCR readers with error handling"""
        self.tesseract_available = True
        self.easyocr_reader = None
        
        # Test Tesseract
        try:
            pytesseract.image_to_string(Image.new('RGB', (100, 100), 'white'))
            self.logger.info("Tesseract OCR initialized successfully")
        except Exception as e:
            self.logger.error(f"Tesseract initialization failed: {e}")
            self.tesseract_available = False
        
        # Initialize EasyOCR if available
        # Note: EasyOCR is active by default if installed (may be slower but more accurate)
        use_easyocr = os.environ.get('ENABLE_EASYOCR', '1') == '1'  # Default ON
        
        if EASYOCR_AVAILABLE and use_easyocr:
            try:
                ocr_lang = self.config.get('OCR', 'language')
                # Map common language codes
                lang_map = {'eng': 'en', 'jpn': 'ja', 'kor': 'ko'}
                easyocr_lang = lang_map.get(ocr_lang, 'en')
                
                # Use CPU mode with minimal workers for better performance
                self.easyocr_reader = easyocr.Reader([easyocr_lang], gpu=False, verbose=False)
                self.logger.info(f"EasyOCR initialized for language: {easyocr_lang} (CPU mode)")
            except Exception as e:
                self.logger.warning(f"EasyOCR initialization failed: {e}")
                self.easyocr_reader = None
        else:
            self.easyocr_reader = None
            self.logger.info("EasyOCR disabled for faster processing (Tesseract only)")
    
    def download_chapter(self, url, source_hint=None):
        """Enhanced chapter download with better error handling"""
        self.logger.info(f"Starting chapter download from: {url}")
        
        try:
            # Detect source from URL
            if not source_hint:
                source_hint = self._detect_source(url)
            
            self.logger.info(f"Detected source: {source_hint}")
            
            # Exponential backoff retry logic
            max_chapter_retries = 5  # Increased from 3
            base_delay = 2
            max_delay = 60
            success = False
            
            for attempt in range(max_chapter_retries):
                if attempt > 0:
                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter
                    
                    self.logger.info(f"Retry {attempt+1}/{max_chapter_retries} after {total_delay:.1f}s (exponential backoff)...")
                    time.sleep(total_delay)

                # Download based on source and mode
                if self.mode == 'webtoon' and 'webtoons.com' in url:
                    success = self._download_webtoon_enhanced(url)
                elif self.mode == 'manga' and 'webtoons.com' not in url:
                    # Proceed with manga-specific downloaders
                    if 'mangaread' in url:
                        success = self._download_mangaread(url)
                    elif 'manhuaus.com' in url:
                        success = self._download_manhuaus(url)
                        if not success:
                            success = self._download_manhuaus_playwright(url, headless=True)
                        if not success:
                            success = self._download_manhuaus_undetected(url, headless=True)
                        if not success:
                            success = self._download_manhuaus_selenium(url, headless=True)
                        if not success:
                            success = self._download_manhuaus_cloudscraper(url)
                    elif 'manhwaclan.com' in url:
                        success = self._download_manhwaclan(url, headless=True)
                    elif 'topmanhua' in url or self._is_wpmanga_site(url):
                        success = self._download_wpmanga(url)
                    else:
                        success = self._download_generic(url)
                else:
                    # Fallback to existing source detection if mode doesn't explicitly match
                    if 'webtoons.com' in url:
                        success = self._download_webtoon_enhanced(url)
                    elif 'mangaread' in url:
                        success = self._download_mangaread(url)
                    elif 'manhuaus.com' in url:
                        success = self._download_manhuaus(url)
                        if not success:
                            success = self._download_manhuaus_playwright(url, headless=True)
                        if not success:
                            success = self._download_manhuaus_undetected(url, headless=True)
                        if not success:
                            success = self._download_manhuaus_selenium(url, headless=True)
                        if not success:
                            success = self._download_manhuaus_cloudscraper(url)
                    elif 'manhwaclan.com' in url:
                        success = self._download_manhwaclan(url, headless=True)
                    elif 'topmanhua' in url or self._is_wpmanga_site(url):
                        success = self._download_wpmanga(url)
                    else:
                        success = self._download_generic(url)
                
                if success:
                    break
            
            if success:
                # Count downloaded files
                raw_files = list(self.dirs['raw'].glob('*'))
                self.stats['downloaded_images'] = len(raw_files)
                
                # Validate download completeness
                if self._validate_download_completeness():
                    self.logger.info(f"✓ Download validated: {self.stats['downloaded_images']} images")
                else:
                    self.logger.warning("Download validation warnings - check logs")
                
                return True
            else:
                self.logger.error("Download failed after multiple retries")
                return False
                
        except Exception as e:
            self.logger.error(f"Download error: {e}")
            self.stats['errors'] += 1
            return False
    
    def _detect_source(self, url):
        """Detect manga source from URL"""
        url_lower = url.lower()
        if 'webtoons.com' in url_lower:
            return 'webtoons'
        elif 'topmanhua.fan' in url_lower or 'topmanhua' in url_lower:
            return 'topmanhua'
        elif 'mangadx' in url_lower:
            return 'mangadx'
        elif 'mangakakalot' in url_lower:
            return 'mangakakalot'
        elif 'mangaread' in url_lower:
            return 'mangaread'
        elif 'manhuaus.com' in url_lower:
            return 'manhuaus'
        elif 'manhwaclan.com' in url_lower:
            return 'manhwaclan'
        else:
            return 'generic'
    
    def _validate_download_completeness(self):
        """Validate that downloaded images meet minimum quality standards."""
        try:
            raw_files = list(self.dirs['raw'].glob('*'))
            
            # Check file sizes
            valid_files = []
            suspicious_files = []
            
            for file in raw_files:
                try:
                    size = file.stat().st_size
                    if size < 1000:  # Less than 1KB likely error/placeholder
                        suspicious_files.append((file.name, size))
                    else:
                        valid_files.append(file)
                except Exception as e:
                    self.logger.debug(f"Error checking file {file.name}: {e}")
            
            # Log suspicious files
            if suspicious_files:
                self.logger.warning(f"Found {len(suspicious_files)} suspicious files (< 1KB):")
                for fname, size in suspicious_files[:5]:  # Show first 5
                    self.logger.warning(f"  - {fname}: {size} bytes")
            
            # Expect at least 10 images for a chapter (reasonable minimum)
            min_expected = 10
            if len(valid_files) < min_expected:
                self.logger.warning(f"⚠️  Low image count: {len(valid_files)} valid files (expected >= {min_expected})")
                return False
            
            self.logger.info(f"✓ Validation passed: {len(valid_files)} valid images")
            return True
            
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False
    
    def _download_webtoon_enhanced(self, url):
        """Enhanced webtoon download with JavaScript loaders ONLY (no HTML fallback)."""
        self.logger.info("Attempting webtoon download with Selenium JavaScript loader")
        
        # Try Selenium (headless) first
        try:
            if self._download_webtoon_selenium(url, headless=True):
                return True
            else:
                self.logger.warning("Primary Selenium (headless) failed, trying headful fallback")
        except Exception as e:
            self.logger.warning(f"Primary Selenium (headless) failed: {e}")
        
        # Secondary fallback: Selenium (headful) with slower, progressive scroll
        try:
            if self._download_webtoon_selenium(url, headless=False):
                return True
        except Exception as e:
            self.logger.warning(f"Secondary Selenium (headful) failed: {e}")
        
        self.logger.error("All JavaScript loader attempts failed; HTML scraping is disabled by configuration")
        return False
    
    def _download_webtoon_selenium(self, url, headless=True):
        """Download webtoon using Selenium JavaScript loader (headless or headful)."""
        mode = "headless" if headless else "headful"
        self.logger.info(f"Starting Selenium JavaScript loader download ({mode})")
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            import time
            
            # Setup Chrome options for reliable JavaScript execution
            chrome_options = Options()
            # Allow explicit Chrome/Chromium binary override
            try:
                _chrome_bin = os.environ.get('CHROME_BIN')
                if _chrome_bin and os.path.exists(_chrome_bin):
                    chrome_options.binary_location = _chrome_bin
                    self.logger.info(f"Using CHROME_BIN: {_chrome_bin}")
            except Exception:
                pass
            if headless:
                chrome_options.add_argument("--headless=new")
                # Keep GPU enabled in headless-new when possible
            # Common options
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            # Use default Chrome UA to avoid version mismatch issues
            try:
                chrome_options.page_load_strategy = 'eager'
            except Exception:
                pass
            
            # Setup driver (allow CHROMEDRIVER override)
            _drv = os.environ.get('CHROMEDRIVER')
            if _drv and os.path.exists(_drv):
                self.logger.info(f"Using CHROMEDRIVER: {_drv}")
                service = Service(executable_path=_drv)
            else:
                service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(60 if headless else 90)
            
            try:
                self.logger.info(f"Loading webtoon page with JavaScript: {url}")
                driver.get(url)
                
                # Wait for initial DOM readiness
                WebDriverWait(driver, 30 if headless else 45).until(
                    lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
                )
                
                # Anti-detection
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                # Attempt to accept consent/cookie banners (best-effort)
                try:
                    for selector in [
                        "button#onetrust-accept-btn-handler",
                        "button[aria-label='Accept']",
                        "button[aria-label='I agree']",
                        "button:contains('Accept')",
                        "button:contains('I Agree')",
                    ]:
                        els = driver.find_elements(By.CSS_SELECTOR, selector)
                        for el in els:
                            try:
                                el.click()
                                time.sleep(0.5)
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    buttons = driver.find_elements(By.TAG_NAME, 'button')
                    for b in buttons:
                        txt = (b.text or '').strip().lower()
                        if any(k in txt for k in ["accept", "agree", "consent", "allow"]):
                            try:
                                b.click(); time.sleep(0.5)
                            except Exception:
                                pass
                except Exception:
                    pass
                
                # CLOSE POPUPS AND AD OVERLAYS (ROOT LEVEL)
                if POPUP_CLOSER_AVAILABLE and PopupCloser:
                    try:
                        self.logger.info("🚫 Checking for popups and overlays before scrolling...")
                        popup_closer = PopupCloser(max_attempts=3, wait_seconds=1.5)
                        stats = popup_closer.close_all_popups_selenium(driver, url)
                        if stats['popups_closed'] > 0 or stats['overlays_closed'] > 0:
                            self.logger.info(f"🎯 Cleaned up page: {stats}")
                    except Exception as e:
                        self.logger.warning(f"Popup closer warning: {e}")

                if headless:
                    self._scroll_and_wait_fast(driver)
                else:
                    self._scroll_and_wait_progressive(driver)
                
                # Allow some time for lazy images to resolve
                time.sleep(2 if not headless else 1)
                
                # Extract images (top-level)
                image_urls = []
                try:
                    image_urls = self._extract_webtoon_images_enhanced(driver)
                except Exception as e:
                    self.logger.debug(f"DOM extraction error: {e}")

                # If none, try robust JS extraction (top-level)
                if not image_urls:
                    try:
                        image_urls = self._gather_urls_via_js(driver)
                    except Exception as e:
                        self.logger.debug(f"JS gather error: {e}")

                # If still none, try inside iframes
                if not image_urls:
                    try:
                        from selenium.webdriver.common.by import By
                        frames = driver.find_elements(By.TAG_NAME, 'iframe')
                        self.logger.info(f"Found {len(frames)} iframes; scanning for images")
                        for idx, fr in enumerate(frames):
                            try:
                                driver.switch_to.frame(fr)
                                urls_in_frame = self._extract_webtoon_images_enhanced(driver)
                                if not urls_in_frame:
                                    urls_in_frame = self._gather_urls_via_js(driver)
                                for u in urls_in_frame:
                                    if u not in image_urls:
                                        image_urls.append(u)
                            except Exception as e:
                                self.logger.debug(f"Error extracting from iframe {idx}: {e}")
                            finally:
                                driver.switch_to.default_content()
                    except Exception as e:
                        self.logger.debug(f"Iframe scan error: {e}")
                
                if not image_urls:
                    self.logger.error("No comic images found")
                    return False
                
                # Download images
                success_count = self._download_images(image_urls, url)
                
                self.logger.info(f"Downloaded {success_count}/{len(image_urls)} images")
                return success_count > 0
                
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
                
        except ImportError as e:
            self.logger.error("SELENIUM REQUIRED: Selenium is required for reliable webtoon downloads")
            self.logger.error("Please install: pip install selenium webdriver-manager")
            return False
        except Exception as e:
            self.logger.error(f"Selenium JavaScript loader failed ({mode}): {e}")
            return False
    
    def _scroll_and_wait_fast(self, driver):
        """Enhanced scrolling with multiple strategies to ensure ALL images load."""
        try:
            from selenium.webdriver.common.by import By
            self.logger.info("Starting enhanced scroll to capture all panels...")
            
            # Strategy 1: Progressive scroll with image count tracking
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            last_count = 0
            stable_rounds = 0
            max_rounds = 120  # Increased from 80 for very long webtoons
            
            for round_num in range(max_rounds):
                # Scroll incrementally
                driver.execute_script("window.scrollBy(0, Math.floor(window.innerHeight*0.7));")
                time.sleep(0.6)  # Increased from 0.35 for lazy loading
                
                # Micro-scroll back to trigger lazy loaders
                driver.execute_script("window.scrollBy(0, -50);")
                time.sleep(0.2)
                
                # Check image count
                imgs = driver.find_elements(By.CSS_SELECTOR, "img, .viewer_lst img, .viewer_img img, ._images img")
                current_count = len(imgs)
                
                if current_count == last_count:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                    if round_num % 10 == 0:  # Log every 10 rounds
                        self.logger.debug(f"Images found: {current_count}")
                
                last_count = current_count
                
                # Stop if stable for 6 rounds (increased from 4)
                if stable_rounds >= 6:
                    self.logger.info(f"Image count stabilized at {current_count}")
                    break
            
            # Strategy 2: Aggressive final scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Strategy 3: Scroll back to middle and down again
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            
            # Strategy 4: Trigger scroll/resize events
            driver.execute_script("""
                window.dispatchEvent(new Event('scroll'));
                window.dispatchEvent(new Event('resize'));
            """)
            time.sleep(0.5)
            
            final_count = len(driver.find_elements(By.TAG_NAME, "img"))
            self.logger.info(f"Enhanced scrolling completed. Total images: {final_count}")
            
        except Exception as e:
            self.logger.warning(f"Enhanced scroll error: {e}")
            
    def _scroll_and_wait_enhanced(self, driver):
        """Legacy enhanced scrolling - now calls fast version"""
        return self._scroll_and_wait_fast(driver)

    def _scroll_and_wait_progressive(self, driver):
        """Progressive, slower scrolling (headful fallback) - ENHANCED to not miss panels."""
        try:
            from selenium.webdriver.common.by import By
            self.logger.info("Starting progressive scroll to load all episode images")
            
            # Initial wait for any loading overlays to disappear
            time.sleep(2.0)
            
            last_count = 0
            same_count_rounds = 0
            
            # More rounds, smaller steps
            for round_idx in range(60): 
                # Scroll 60% of viewport to trigger intersection observers
                driver.execute_script("window.scrollBy(0, window.innerHeight * 0.6);")
                time.sleep(0.8) # Wait longer for network
                
                # Jiggle up/down to force lazy loaders
                driver.execute_script("window.scrollBy(0, -100);")
                time.sleep(0.3)
                driver.execute_script("window.scrollBy(0, 100);")
                
                # Check for images
                imgs = driver.find_elements(By.CSS_SELECTOR, "img, .viewer_lst img, .viewer_img img, ._images img")
                count = len(imgs)
                
                # If we are at the bottom of the page
                is_bottom = driver.execute_script("return (window.innerHeight + window.scrollY) >= document.body.offsetHeight - 100")
                
                if count == last_count:
                    same_count_rounds += 1
                else:
                    same_count_rounds = 0
                    self.logger.debug(f"Found {count} images so far...")
                
                last_count = count
                
                # If we've seen the same count for a while AND we are at the bottom
                if same_count_rounds >= 6 and is_bottom:
                    self.logger.info("Scroll reached bottom and image count stabilized.")
                    break
                
                # If we are just stuck but not at bottom, keep trying a bit longer
                if same_count_rounds >= 15:
                     self.logger.info("Image count stabilized (possible stuck), stopping scroll.")
                     break
                     
            # Final verification
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3.0)
            
            # Force load all images by iterating them
            driver.execute_script("""
                const imgs = document.querySelectorAll('img');
                imgs.forEach(img => {
                    if (img.loading === 'lazy') img.loading = 'eager';
                    if (!img.complete) img.decode().catch(() => {});
                });
            """)
            time.sleep(1.0)
            
            self.logger.info("Progressive scroll completed")
        except Exception as e:
            self.logger.warning(f"Progressive scroll error: {e}")

    
    def _extract_webtoon_images_enhanced(self, driver):
        """Enhanced comic image extraction with comprehensive selectors and validation"""
        image_urls = []
        
        try:
            self.logger.info("Starting enhanced image extraction with JavaScript")
            
            # Enhanced selectors for modern webtoon sites
            selectors = [
                # Webtoons.com specific
                ".viewer_lst img",
                "._images img", 
                ".viewer_img img",
                "img[src*='webtoon-phinf']",
                "img[data-src*='webtoon-phinf']",
                # Generic comic selectors
                "[class*='viewer'] img",
                "[id*='viewer'] img",
            ]
            
            skip_keywords = ['thumb', 'favicon', 'logo', 'avatar', 'banner', 'promo', 'cover', 'type=a92', 'type=f218', '_m.jpg', '_s.jpg']
            
            for selector in selectors:
                try:
                    images = driver.find_elements(By.CSS_SELECTOR, selector)
                    self.logger.debug(f"Found {len(images)} images with selector: {selector}")
                    
                    for img in images:
                        # Try multiple attribute sources
                        src = (img.get_attribute("src") or 
                               img.get_attribute("data-src") or
                               img.get_attribute("data-original") or
                               img.get_attribute("data-lazy"))
                        if not src:
                            continue
                        src_lower = src.lower()
                        if 'webtoon-phinf' not in src_lower:
                            continue
                        if any(k in src_lower for k in skip_keywords):
                            continue
                        # Dimension checks to avoid thumbnails
                        w = img.get_attribute("naturalWidth") or img.get_attribute("width") or "0"
                        h = img.get_attribute("naturalHeight") or img.get_attribute("height") or "0"
                        try:
                            w = int(w)
                            h = int(h)
                        except Exception:
                            w, h = 0, 0
                        accept = False
                        if max(w, h) >= 900 or (w >= 600 and h >= 600):
                            accept = True
                        else:
                            # Try to parse width from URL param type=wNNN
                            import re as _re
                            m = _re.search(r"type=w(\d+)", src_lower)
                            if m and int(m.group(1)) >= 700:
                                accept = True
                        if accept and src not in image_urls:
                            image_urls.append(src)
                            self.logger.debug(f"Added image: {src[:80]}...")
                except Exception as e:
                    self.logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Remove duplicates while preserving order
            unique_urls = []
            seen = set()
            for url in image_urls:
                if url not in seen:
                    unique_urls.append(url)
                    seen.add(url)
            
            self.logger.info(f"Enhanced extraction found {len(unique_urls)} unique comic images (removed {len(image_urls) - len(unique_urls)} duplicates)")
            
            # Log first few URLs for debugging
            if unique_urls:
                self.logger.info("Sample image URLs found:")
                for i, url in enumerate(unique_urls[:3]):
                    self.logger.info(f"  {i+1}. {url}")
                if len(unique_urls) > 3:
                    self.logger.info(f"  ... and {len(unique_urls) - 3} more")
            
            return unique_urls
            
        except Exception as e:
            self.logger.error(f"Enhanced image extraction failed: {e}")
            return []

    def _gather_urls_via_js(self, driver):
        """Gather potential image URLs using in-page JS from various attributes and styles."""
        try:
            script = r'''
                const urls = new Set();
                const add = (u) => {
                  if (!u) return;
                  if (typeof u !== 'string') return;
                  // Split srcset entries
                  if (u.indexOf(',') !== -1 && u.indexOf(' ') !== -1) {
                    u.split(',').forEach(part => {
                      const t = part.trim().split(' ')[0];
                      if (t) urls.add(t);
                    });
                  } else {
                    urls.add(u);
                  }
                };
                // IMG, SOURCE, PICTURE
                document.querySelectorAll('img, picture img, source').forEach(el => {
                  add(el.currentSrc);
                  add(el.src);
                  add(el.getAttribute('src'));
                  add(el.getAttribute('data-src'));
                  add(el.getAttribute('data-url'));
                  add(el.getAttribute('data-original'));
                  add(el.getAttribute('data-lazy'));
                  add(el.getAttribute('srcset'));
                });
                // Background images
                document.querySelectorAll('[style*="background-image"]').forEach(el => {
                  const s = el.style.backgroundImage;
                  const m = s && s.match(/url\(("|\')?(.*?)\1\)/);
                  if (m && m[2]) add(m[2]);
                });
                // Generic data attributes
                document.querySelectorAll('[data-src],[data-url],[data-image]').forEach(el => {
                  ['data-src','data-url','data-image'].forEach(attr => add(el.getAttribute(attr)));
                });
                return Array.from(urls);
            '''
            raw_urls = driver.execute_script(script)
            if not raw_urls:
                return []
            # Filter URLs
            valid = []
            for u in raw_urls:
                try:
                    ul = u.lower()
                    if 'phinf' not in ul and 'webtoon' not in ul and 'naver' not in ul:
                        continue
                    if ul.startswith('//'):
                        u = 'https:' + u
                    if not ul.startswith('http'):
                        continue
                    if any(k in ul for k in ['thumb','favicon','logo','avatar','banner','promo','cover','sprite']):
                        continue
                    valid.append(u)
                except Exception:
                    continue
            self.logger.info(f"JS gather found {len(valid)} candidate image URLs")
            return valid
        except Exception as e:
            self.logger.debug(f"JS gather exception: {e}")
            return []
    
    def _is_valid_manga_image(self, src: str) -> bool:
        """Generic validation for manga/webtoon images from any domain"""
        if not src:
            return False
        
        src_lower = src.lower()
        skip_words = [
            'logo', 'avatar', 'icon', 'banner', 'thumb', 'button',
            'background', 'advertising', 'pixel', 'tracking', 'spacer',
            'transparent', 'gravatar', 'captcha', 'ad.', '/ads/',
        ]
        
        # Filter UI elements
        if any(w in src_lower for w in skip_words):
            return False
            
        # Optional: verify it has an image extension or looks like a CDN path
        from urllib.parse import urlparse
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif')
        path = urlparse(src_lower).path
        if any(path.endswith(ext) for ext in exts) or 'image' in src_lower or 'img' in path:
            return True
            
        return False

    def _is_valid_wpmanga_image(self, src):
        """Validate if image URL is likely a WP-manga chapter image (topmanhua, zinmanga, etc.)."""
        if not src:
            return False

        src_lower = src.strip().lower()

        # Must look like an image
        has_image_ext = any(ext in src_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif'])
        if not has_image_ext and 'image' not in src_lower:
            return False

        # Reject obvious non-chapter images
        skip_patterns = [
            'logo', 'avatar', 'icon', 'banner', 'button', 'background',
            'zeropixel', 'pixel', 'tracking', 'spacer', 'transparent',
            'ad-', '/ads/', 'advertisement', 'promo', 'sponsor',
            'favicon', 'emoji', 'smiley', 'captcha', 'badge',
            'gravatar', 'wp-content/plugins', 'wp-includes',
        ]
        if any(p in src_lower for p in skip_patterns):
            return False

        # data: URIs are not chapter images
        if src_lower.startswith('data:'):
            return False

        # Very small dimension hints in URL (1x1 tracking pixels etc.)
        dim_match = re.search(r'[/=_-](\d+)x(\d+)', src_lower)
        if dim_match:
            w, h = int(dim_match.group(1)), int(dim_match.group(2))
            if w < 50 or h < 50:
                return False

        return True

    def _is_valid_webtoon_image(self, src):
        """Validate if image URL is likely a webtoon comic image - STRICT filtering to avoid unrelated content"""
        if not src:
            return False
            
        src_lower = src.lower()
        
        # Must be from webtoon domain
        if 'webtoon-phinf.pstatic.net' not in src_lower:
            return False
        
        # STRICT skip patterns - reject ALL non-episode content
        skip_patterns = [
            'thumbnail',
            'thumb', 
            'landing-page',
            'landing_page',
            'mobile.jpg',
            'icon',
            'logo',
            'avatar',
            'profile', 
            'button',
            'banner',
            'ad',
            'promo',
            'cover',
            'poster',
            'type=a92',     # Webtoons thumbnail size
            'type=f218',    # Small square thumbnails 
            'type=q85',     # Quality parameter for thumbnails
            'type=a100',    # Small avatar/profile images
            'type=m',       # Mobile thumbnails
            '_m.jpg',       # Mobile versions
            '_s.jpg',       # Small versions  
            '_thumb',       # Thumbnail versions
            'genre',        # Genre page images
            'title_card',   # Title cards
            'character',    # Character images
            'creator',      # Creator images
            'notice',       # Notice images
            'event',        # Event images
            'sharing',      # Social sharing images
            'facebook',     # Facebook sharing
            'twitter',      # Twitter sharing
            'instagram',    # Instagram images
            'webtoon_sharing', # Sharing thumbnails
        ]
        
        # STRICT CHECK - reject if ANY skip pattern found
        for pattern in skip_patterns:
            if pattern in src_lower:
                self.logger.debug(f"❌ Rejected image (contains '{pattern}'): {src[:60]}...")
                return False
        
        # Extract filename for validation
        filename = src_lower.split('/')[-1].split('?')[0]
        
        # ONLY accept episode images with very specific characteristics:
        
        # 1. Must have long numeric filename (actual episode images)
        if re.search(r'\d{10,}', filename):
            # Additional validation: must be from episode viewer path
            if ('/episode/' in src_lower or 'viewer' in src_lower or 'title_no=' in src_lower):
                self.logger.debug(f"✅ Valid episode image (long numeric): {src[:60]}...")
                return True
        
        # 2. Accept only type=w (width specified) from episode context
        if 'type=w' in src_lower and '/episode/' in src_lower:
            # But reject small widths that are likely thumbnails
            width_match = re.search(r'type=w(\d+)', src_lower)
            if width_match:
                width = int(width_match.group(1))
                if width >= 600:  # Only accept reasonably large images
                    self.logger.debug(f"✅ Valid episode image (type=w{width}): {src[:60]}...")
                    return True
                else:
                    self.logger.debug(f"❌ Rejected small width image (w{width}): {src[:60]}...")
                    return False
        
        # 3. VERY strict check for viewer context
        if 'viewer' in src_lower and 'episode_no=' in src_lower:
            # Must be in actual episode viewer, not just linked from viewer
            self.logger.debug(f"✅ Valid viewer episode image: {src[:60]}...")
            return True
        
        # REJECT everything else - be very conservative
        self.logger.debug(f"❌ Rejected (doesn't match strict criteria): {src[:60]}...")
        return False
    
    def _download_images_via_js(self, executor, image_urls, page_or_driver=None) -> int:
        """
        Download images by executing Javascript or taking element screenshots.
        Works for both Playwright (page.evaluate) and Selenium/UC (driver.execute_script).
        
        Args:
            executor: A function that takes a JS string and optional args and returns the result.
            image_urls: List of image URLs to download.
            page_or_driver: The page object (Playwright) or driver (Selenium) for screenshot fallback.
        """
        success_count = 0
        import base64
        import time

        # JS script to try and get image as Base64 via Canvas or Fetch
        js_script = """async (url) => {
            const getCanvasData = (img) => {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                return canvas.toDataURL('image/webp').length > 100 ? canvas.toDataURL('image/webp') : canvas.toDataURL('image/jpeg');
            };

            try {
                const imgInDom = document.querySelector(`img[src="${url}"], img[data-src="${url}"], img[data-lazy-src="${url}"]`);
                if (imgInDom && imgInDom.naturalWidth > 10) {
                    try {
                        return { data: getCanvasData(imgInDom) };
                    } catch (e) { /* tainted canvas? */ }
                }

                const response = await fetch(url);
                if (!response.ok) return { error: `HTTP ${response.status}` };
                const blob = await response.blob();
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve({ data: reader.result });
                    reader.readAsDataURL(blob);
                });
            } catch (e) {
                return { error: e.toString() };
            }
        }"""

        for i, img_url in enumerate(image_urls):
            # Normal download check (skipping existing)
            existing = list(self.dirs['raw'].glob(f"{i+1:03d}.*"))
            if existing and existing[0].stat().st_size > 1024:
                success_count += 1
                continue

            self.logger.info(f"[JS-DL] Image {i+1}/{len(image_urls)}")
            
            # Step 1: Try JS Extraction
            try:
                if hasattr(executor, 'evaluate'): # Playwright
                    result = executor.evaluate(js_script, img_url)
                else: # Selenium / UC
                    wrapped_js = f"return await ({js_script})('{img_url}')"
                    result = executor(wrapped_js)

                if result and 'data' in result:
                    data_url = result['data']
                    if ',' in data_url:
                        header, encoded = data_url.split(',', 1)
                        image_data = base64.b64decode(encoded)
                        ext = '.webp' if 'webp' in header else ('.png' if 'png' in header else '.jpg')
                        path = self.dirs.get('raw', Path('.')) / f"{i+1:03d}{ext}"
                        with open(path, 'wb') as f:
                            f.write(image_data)
                        success_count += 1
                        continue
            except Exception as e:
                self.logger.debug(f"[JS-DL] Step 1 (JS) failed for {i+1}: {e}")

            # Step 2: Ultimate Fallback - Element Screenshot
            # This works even if CORS/Tainted Canvas/Fetch fail, because it just grabs pixels.
            if page_or_driver:
                try:
                    self.logger.info(f"[JS-DL] Step 2: Screenshotting image {i+1}...")
                    if hasattr(page_or_driver, 'locator'): # Playwright
                        # Find the element
                        selectors = [
                            f'img[src="{img_url}"]',
                            f'img[data-src="{img_url}"]',
                            f'img[data-lazy-src="{img_url}"]'
                        ]
                        for sel in selectors:
                            loc = page_or_driver.locator(sel).first
                            if loc.is_visible():
                                loc.scroll_into_view_if_needed()
                                time.sleep(0.5) # Wait for potential render
                                image_data = loc.screenshot()
                                path = self.dirs['raw'] / f"{i+1:03d}.png"
                                with open(path, 'wb') as f:
                                    f.write(image_data)
                                success_count += 1
                                break
                    else: # Selenium / UC
                        from selenium.webdriver.common.by import By
                        selectors = [
                            f'//img[@src="{img_url}"]',
                            f'//img[@data-src="{img_url}"]',
                            f'//img[@data-lazy-src="{img_url}"]'
                        ]
                        for sel in selectors:
                            try:
                                el = page_or_driver.find_element(By.XPATH, sel)
                                if el.is_displayed():
                                    page_or_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                                    time.sleep(0.5)
                                    image_data = el.screenshot_as_png
                                    path = self.dirs.get('raw', Path('.')) / f"{i+1:03d}.png"
                                    with open(path, 'wb') as f:
                                        f.write(image_data)
                                    success_count += 1
                                    break
                            except: continue
                except Exception as e:
                    self.logger.warning(f"[JS-DL] Screenshot failed for {i+1}: {e}")

        return success_count

    def _download_images(self, image_urls, referer_url):
        """Download images with proper headers and error handling"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': referer_url,
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        
        success_count = 0
        for i, img_url in enumerate(image_urls):
            # Resume logic: Check if any file with this index already exists
            existing = list(self.dirs['raw'].glob(f"{i+1:03d}.*"))
            if existing:
                if existing[0].stat().st_size > 1024:
                    self.logger.debug(f"Skipping {existing[0].name} (already exists)")
                    success_count += 1
                    continue

            max_retries = 5
            for attempt in range(max_retries):
                try:
                    self.logger.debug(f"Downloading image {i+1}/{len(image_urls)} (Attempt {attempt+1})")
                    
                    response = requests.get(img_url, headers=headers, timeout=30)
                    response.raise_for_status()
                    
                    # Validate image content
                    if len(response.content) < 1000:
                        self.logger.warning(f"Image too small: {len(response.content)} bytes")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                    
                    # Save image
                    filename = self.dirs['raw'] / f"{i+1:03d}.jpg"
                    with open(filename, 'wb') as f:
                        f.write(response.content)
                    
                    success_count += 1
                    self.logger.debug(f"Saved: {filename}")
                    break # Success!
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        self.logger.warning(f"Error downloading image {i+1}: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(f"Failed to download image {i+1} after {max_retries} attempts: {e}")
        
        return success_count
    
    def _download_webtoon_html_fallback(self, url):
        """HTML-based fallback for webtoon downloads when Selenium fails"""
        self.logger.info("Starting HTML fallback download")
        
        try:
            import requests
            from bs4 import BeautifulSoup
            import re
            
            # Headers to mimic real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Referer': 'https://www.webtoons.com/',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            self.logger.info("Fetching page content with requests...")
            
            # Get the main page
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            self.logger.info("Parsing HTML for images...")
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for webtoon images in various ways
            image_urls = []
            
            # Method 1: Extract all webtoon-phinf URLs from entire HTML (not just scripts)
            # Look for actual episode image URLs in the full page HTML
            webtoon_urls = re.findall(r'https://webtoon-phinf[^\s\"\\<>]+\.(?:jpg|jpeg|png|gif)', response.text)
            
            for url_match in webtoon_urls:
                clean_url = url_match.replace('\\', '').strip()
                # Apply validation to filter out thumbnails
                if self._is_valid_webtoon_image(clean_url):
                    if clean_url not in image_urls:
                        image_urls.append(clean_url)
            
            # Method 2: Direct image tags
            img_tags = soup.find_all('img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if src and 'webtoon-phinf' in src:
                    if src not in image_urls:
                        image_urls.append(src)
            
            self.logger.info(f"Found {len(image_urls)} potential images")
            
            if not image_urls:
                self.logger.error("No webtoon images found in HTML")
                return False
            
            # Download images using existing method
            success_count = self._download_images(image_urls, url)
            
            self.logger.info(f"HTML fallback downloaded {success_count} images")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"HTML fallback failed: {e}")
            return False
    

    

    
    def _download_manhuaus(self, url):
        """Download from ManhuaUS with enhanced error handling"""
        self.logger.info(f"Attempting ManhuaUS download from: {url}")
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
                'Referer': 'https://manhuaus.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            if self._is_cloudflare_challenge(response.text):
                self.logger.info("Cloudflare challenge detected, escalating to automated browser")
                return False
            soup = BeautifulSoup(response.text, 'html.parser')
            image_containers = soup.select('div.reading-content img')
            if not image_containers:
                image_containers = soup.select('div.text-left img, .page-break img')
            if not image_containers:
                self.logger.error("No image containers found on the page")
                return False
            image_urls = []
            for img in image_containers:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    src = src.strip()
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://manhuaus.com' + src
                    if not any(x in src.lower() for x in ['avatar', 'logo', 'icon', 'thumb']):
                        image_urls.append(src)
            if not image_urls:
                self.logger.error("No valid image URLs found on the page")
                return False
            self.logger.info(f"Found {len(image_urls)} images to download")
            success_count = 0
            for i, img_url in enumerate(image_urls):
                # Resume logic: Check if any file with this index already exists
                # We check for common extensions to be thorough
                existing = list(self.dirs['raw'].glob(f"{i+1:03d}.*"))
                if existing:
                    # Basic validation: ensure file isn't empty (e.g. > 1KB)
                    if existing[0].stat().st_size > 1024:
                        self.logger.debug(f"Skipping {existing[0].name} (already exists)")
                        success_count += 1
                        continue

                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        img_headers = headers.copy()
                        img_headers['Referer'] = url
                        img_response = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                        img_response.raise_for_status()
                        
                        content_type = img_response.headers.get('content-type', '')
                        if 'jpeg' in content_type or 'jpg' in content_type:
                            ext = '.jpg'
                        elif 'png' in content_type:
                            ext = '.png'
                        elif 'webp' in content_type:
                            ext = '.webp'
                        else:
                            ext = os.path.splitext(img_url.split('?')[0])[1][:4].lower()
                            if not ext or len(ext) > 4 or not ext[1:].isalpha():
                                ext = '.jpg'
                                
                        img_path = self.dirs['raw'] / f"{i+1:03d}{ext}"
                        with open(img_path, 'wb') as f:
                            for chunk in img_response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        self.logger.debug(f"Downloaded {img_path.name}")
                        success_count += 1
                        break # Success!
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2
                            self.logger.warning(f"Attempt {attempt+1} failed for image {i+1}: {e}. Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            self.logger.error(f"Failed to download image {i+1} after {max_retries} attempts: {e}")
            self.logger.info(f"Successfully processed {success_count}/{len(image_urls)} images from ManhuaUS")
            return success_count > 0
        except requests.RequestException as e:
            self.logger.error(f"Network error while downloading from ManhuaUS: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error downloading from ManhuaUS: {e}")
            return False

    def _is_cloudflare_challenge(self, html):
        try:
            h = html.lower()
            markers = [
                "just a moment",
                "verifying you are human",
                "cdn-cgi",
                "challenge",
                "cf-chl",
                "rocket-loader"
            ]
            return any(m in h for m in markers)
        except Exception:
            return False

    def _download_manhuaus_cloudscraper(self, url):
        try:
            import cloudscraper
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
                'Referer': url,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False})
            resp = scraper.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            if self._is_cloudflare_challenge(resp.text):
                self.logger.info("Cloudflare challenge still present after cloudscraper, escalating to browser")
                return False
            soup = BeautifulSoup(resp.text, 'html.parser')
            imgs = soup.select('div.reading-content img, div.text-left img, .page-break img')
            image_urls = []
            seen = set()
            for img in imgs:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not src:
                    srcset = img.get('srcset')
                    if srcset:
                        parts = [p.strip() for p in srcset.split(',') if p.strip()]
                        if parts:
                            src = parts[-1].split(' ')[0]
                src = self._normalize_manhuaus_url(src)
                if not src:
                    continue
                low = src.lower()
                if any(x in low for x in ['avatar', 'logo', 'icon', 'thumb']):
                    continue
                if src not in seen:
                    seen.add(src)
                    image_urls.append(src)
            if not image_urls:
                return False
            session = requests.Session()
            session.headers.update({'User-Agent': headers['User-Agent'], 'Referer': url})
            session.cookies.update(scraper.cookies)
            count = self._download_images_with_session(session, image_urls, url)
            return count > 0
        except Exception as e:
            self.logger.error(f"ManhuaUS cloudscraper failed: {e}")
            return False

    def _pick_src_from_attrs(self, elem):
        src = elem.get_attribute('src') or elem.get_attribute('data-src') or elem.get_attribute('data-lazy-src')
        if not src:
            srcset = elem.get_attribute('srcset')
            if srcset:
                parts = [p.strip() for p in srcset.split(',') if p.strip()]
                if parts:
                    src = parts[-1].split(' ')[0]
        return src

    def _normalize_manhuaus_url(self, u):
        if not u:
            return None
        u = u.strip()
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return 'https://manhuaus.com' + u
        return u

    def _extract_manhuaus_images_dom(self, driver):
        from selenium.webdriver.common.by import By
        imgs = driver.find_elements(By.CSS_SELECTOR, 'div.reading-content img, div.text-left img, .page-break img')
        urls = []
        seen = set()
        for img in imgs:
            u = self._pick_src_from_attrs(img)
            u = self._normalize_manhuaus_url(u)
            if not u:
                continue
            low = u.lower()
            if any(x in low for x in ['avatar', 'logo', 'icon', 'thumb']):
                continue
            if u not in seen:
                seen.add(u)
                urls.append(u)
        return urls

    def _build_requests_session_from_driver(self, driver, referer):
        import requests
        s = requests.Session()
        ua = driver.execute_script('return navigator.userAgent')
        s.headers.update({'User-Agent': ua, 'Referer': referer})
        for c in driver.get_cookies():
            s.cookies.set(c.get('name'), c.get('value'), domain=c.get('domain'), path=c.get('path'))
        return s

    def _download_images_with_session(self, session, image_urls, referer_url):
        success_count = 0
        for i, img_url in enumerate(image_urls):
            # Resume logic: Check if any file with this index already exists
            existing = list(self.dirs['raw'].glob(f"{i+1:03d}.*"))
            if existing:
                if existing[0].stat().st_size > 1024:
                    self.logger.debug(f"Skipping {existing[0].name} (already exists)")
                    success_count += 1
                    continue

            max_retries = 5
            for attempt in range(max_retries):
                try:
                    r = session.get(img_url, headers={'Accept': 'image/webp,image/*,*/*;q=0.8', 'Referer': referer_url}, stream=True, timeout=60)
                    r.raise_for_status()
                    ct = r.headers.get('content-type', '')
                    if 'jpeg' in ct or 'jpg' in ct:
                        ext = '.jpg'
                    elif 'png' in ct:
                        ext = '.png'
                    elif 'webp' in ct:
                        ext = '.webp'
                    else:
                        ext = os.path.splitext(img_url.split('?')[0])[1][:4].lower()
                        if not ext or len(ext) > 4 or not ext[1:].isalpha():
                            ext = '.jpg'
                    path = self.dirs['raw'] / f"{i+1:03d}{ext}"
                    with open(path, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                f.write(chunk)
                    success_count += 1
                    break # Success!
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        self.logger.warning(f"Attempt {attempt+1} failed for image {i+1}: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(f"Failed to download image {i+1} after {max_retries} attempts: {e}")
        return success_count

    def _download_manhuaus_selenium(self, url, headless=True):
        def _run(headless_mode):
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            import time
            opts = Options()
            _bin = os.environ.get('CHROME_BIN')
            if _bin and os.path.exists(_bin):
                opts.binary_location = _bin
            else:
                _mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
                if os.path.exists(_mac):
                    opts.binary_location = _mac
            if headless_mode:
                opts.add_argument('--headless')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--remote-allow-origins=*')
            opts.add_argument('--disable-gpu')
            opts.add_argument('--window-size=1280,1800')
            try:
                try:
                    opts.page_load_strategy = 'eager'
                except Exception:
                    pass
                _drv = os.environ.get('CHROMEDRIVER')
                if _drv and os.path.exists(_drv):
                    service = Service(executable_path=_drv)
                else:
                    service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=opts)
                driver.set_page_load_timeout(60)
                try:
                    driver.get(url)
                    WebDriverWait(driver, 30).until(
                        lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
                    )
                    try:
                        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    except Exception:
                        pass
                    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.reading-content img')))
                    
                    # CLOSE POPUPS AND AD OVERLAYS (ROOT LEVEL)
                    if POPUP_CLOSER_AVAILABLE and PopupCloser:
                        try:
                            self.logger.info("🚫 Checking for popups and overlays before scrolling...")
                            popup_closer = PopupCloser(max_attempts=3, wait_seconds=1.5)
                            stats = popup_closer.close_all_popups_selenium(driver, url)
                            if stats['popups_closed'] > 0 or stats['overlays_closed'] > 0:
                                self.logger.info(f"🎯 Cleaned up page: {stats}")
                        except Exception as e:
                            self.logger.warning(f"Popup closer warning: {e}")
                    
                    last = 0
                    same = 0
                    for _ in range(90):
                        driver.execute_script('window.scrollBy(0, Math.floor(window.innerHeight*0.9));')
                        time.sleep(0.35)
                        driver.execute_script('window.scrollBy(0, -40);')
                        time.sleep(0.15)
                        cnt = len(driver.find_elements(By.CSS_SELECTOR, 'img'))
                        if cnt == last:
                            same += 1
                        else:
                            same = 0
                        last = cnt
                        if same >= 5:
                            break
                    time.sleep(1)
                    image_urls = self._extract_manhuaus_images_dom(driver)
                    if not image_urls:
                        return False
                    session = self._build_requests_session_from_driver(driver, url)
                    count = self._download_images_with_session(session, image_urls, url)
                    return count > 0
                finally:
                    try:
                        driver.quit()
                    except Exception:
                        pass
            except Exception as e:
                try:
                    self.logger.warning(f"ManhuaUS Selenium attempt failed: {e}")
                except Exception:
                    pass
                return False
        try:
            ok = _run(headless)
            if not ok and headless:
                ok = _run(False)
            return bool(ok)
        except Exception as e:
            self.logger.error(f"ManhuaUS Selenium failed: {e}")
            return False

    def _download_manhuaus_undetected(self, url, headless=True):
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time, os
            opts = uc.ChromeOptions()
            _bin = os.environ.get('CHROME_BIN')
            if _bin and os.path.exists(_bin):
                opts.binary_location = _bin
            else:
                _mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
                if os.path.exists(_mac):
                    opts.binary_location = _mac
            if headless:
                opts.add_argument('--headless')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--remote-allow-origins=*')
            opts.add_argument('--disable-gpu')
            opts.add_argument('--window-size=1280,1800')
            driver = uc.Chrome(options=opts)
            try:
                driver.get(url)
                WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.reading-content img')))
                
                # CLOSE POPUPS AND AD OVERLAYS (ROOT LEVEL)
                if POPUP_CLOSER_AVAILABLE and PopupCloser:
                    try:
                        self.logger.info("🚫 Checking for popups and overlays before scrolling...")
                        popup_closer = PopupCloser(max_attempts=3, wait_seconds=1.5)
                        stats = popup_closer.close_all_popups_selenium(driver, url)
                        if stats['popups_closed'] > 0 or stats['overlays_closed'] > 0:
                            self.logger.info(f"🎯 Cleaned up page: {stats}")
                    except Exception as e:
                        self.logger.warning(f"Popup closer warning: {e}")
                
                last = 0
                same = 0
                for _ in range(90):
                    driver.execute_script('window.scrollBy(0, Math.floor(window.innerHeight*0.9));')
                    time.sleep(0.35)
                    driver.execute_script('window.scrollBy(0, -40);')
                    time.sleep(0.15)
                    cnt = len(driver.find_elements(By.CSS_SELECTOR, 'img'))
                    if cnt == last:
                        same += 1
                    else:
                        same = 0
                    last = cnt
                    if same >= 5:
                        break
                time.sleep(1)
                image_urls = self._extract_manhuaus_images_dom(driver)
                if not image_urls:
                    return False
                session = self._build_requests_session_from_driver(driver, url)
                count = self._download_images_with_session(session, image_urls, url)
                return count > 0
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"ManhuaUS undetected-chromedriver failed: {e}")
            return False

    def _download_manhuaus_playwright(self, url, headless=True):
        def _run(headless_mode):
            from playwright.sync_api import sync_playwright
            import time, requests
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless_mode)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_selector('div.reading-content img', timeout=30000)
                last = 0
                same = 0
                for _ in range(90):
                    page.evaluate('window.scrollBy(0, Math.floor(window.innerHeight*0.9));')
                    time.sleep(0.35)
                    page.evaluate('window.scrollBy(0, -40);')
                    time.sleep(0.15)
                    cnt = len(page.query_selector_all('img'))
                    if cnt == last:
                        same += 1
                    else:
                        same = 0
                    last = cnt
                    if same >= 5:
                        break
                time.sleep(1)
                elems = page.query_selector_all('div.reading-content img, div.text-left img, .page-break img')
                image_urls = []
                seen = set()
                for e in elems:
                    src = e.get_attribute('src') or e.get_attribute('data-src') or e.get_attribute('data-lazy-src')
                    if not src:
                        srcset = e.get_attribute('srcset')
                        if srcset:
                            parts = [p.strip() for p in srcset.split(',') if p.strip()]
                            if parts:
                                src = parts[-1].split(' ')[0]
                    src = self._normalize_manhuaus_url(src)
                    if not src:
                        continue
                    low = src.lower()
                    if any(x in low for x in ['avatar', 'logo', 'icon', 'thumb']):
                        continue
                    if src not in seen:
                        seen.add(src)
                        image_urls.append(src)
                if not image_urls:
                    browser.close()
                    return False
                s = requests.Session()
                ua = page.evaluate('navigator.userAgent')
                s.headers.update({'User-Agent': ua, 'Referer': url})
                for c in context.cookies():
                    s.cookies.set(c.get('name'), c.get('value'), domain=c.get('domain'), path=c.get('path'))
                count = self._download_images_with_session(s, image_urls, url)
                browser.close()
                return count > 0
        try:
            ok = _run(headless)
            if not ok and headless:
                ok = _run(False)
            return bool(ok)
        except Exception as e:
            self.logger.error(f"ManhuaUS Playwright failed: {e}")
            return False

    def _download_mangaread(self, url):
        """Download from MangaRead with enhanced error handling"""
        self.logger.info(f"Attempting MangaRead download from: {url}")

        try:
            # Set up headers to mimic a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': url,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status() # Raise an exception for HTTP errors

            soup = BeautifulSoup(response.text, 'html.parser')
            image_urls = []

            # MangaRead specific selectors
            img_tags = soup.select('div.page-content img, div.read-container img, .reading-content img')
            for img in img_tags:
                src = img.get('src') or img.get('data-src')
                if src and not any(keyword in src for keyword in ['thumb', 'avatar', 'logo']):
                    image_urls.append(src)
            
            if not image_urls:
                self.logger.error("Could not find any image URLs on MangaRead page.")
                return False

            self.logger.info(f"Found {len(image_urls)} images to download.")
            success_count = 0
            for i, img_url in enumerate(image_urls):
                # Resume logic: Check if any file with this index already exists
                existing = list(self.dirs['raw'].glob(f"{i+1:03d}.*"))
                if existing:
                    if existing[0].stat().st_size > 1024:
                        self.logger.debug(f"Skipping {existing[0].name} (already exists)")
                        success_count += 1
                        continue

                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        img_response = requests.get(img_url, headers=headers, stream=True, timeout=30)
                        img_response.raise_for_status()

                        # Determine file extension from URL or content type
                        ext = '.png' # Default to png
                        content_type = img_response.headers.get('Content-Type')
                        if content_type and 'image/jpeg' in content_type:
                            ext = '.jpg'
                        elif content_type and 'image/png' in content_type:
                            ext = '.png'
                        elif content_type and 'image/webp' in content_type:
                            ext = '.webp'

                        img_path = self.dirs['raw'] / f"{i+1:03d}{ext}"
                        with open(img_path, 'wb') as f:
                            for chunk in img_response.iter_content(chunk_size=8192):
                                f.write(chunk)

                        self.logger.debug(f"Downloaded {img_path.name}")
                        success_count += 1
                        break # Success!

                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2
                            self.logger.warning(f"Attempt {attempt+1} failed for image {i+1}: {e}. Retrying in {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            self.logger.error(f"Failed to download image {i+1} after {max_retries} attempts: {e}")

            self.logger.info(f"Successfully processed {success_count}/{len(image_urls)} images from MangaRead")
            return success_count > 0

        except requests.RequestException as e:
            self.logger.error(f"Network error while downloading from MangaRead: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error downloading from MangaRead: {e}")
            return False
    
    def _download_manhwaclan(self, url, headless=False):
        """
        Download from manhwaclan.com using Undetected ChromeDriver with auto-retry.
        Runs in VISIBLE mode (headless=False) to ensure reliability.
        """
        # Force visible mode as requested
        headless = False
        self.logger.info("👀 Attempting VISIBLE (headful) download...")
        
        # Try in visible mode
        if self._download_manhwaclan_impl(url, headless=False):
            return True
            
        self.logger.warning("⚠️ First visible attempt failed. Retrying in visible mode...")
        time.sleep(5)
        return self._download_manhwaclan_impl(url, headless=False)


    def _download_manhwaclan_impl(self, url, headless=False):
        """Internal implementation for manhwaclan.com download with human-like behavior"""
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            import time
            import requests
            import threading

            
            self.logger.info("🚀 Starting manhwaclan download with UC + Human Behavior...")
            
            # Setup UC
            opts = uc.ChromeOptions()
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            if headless:
                opts.add_argument('--headless')
                opts.add_argument('--window-size=1920,1080')
                opts.add_argument('--disable-gpu')
                opts.add_argument('--mute-audio')
                opts.add_argument('--disable-notifications')
                opts.add_argument('--no-first-run')
                # Stealth: Spoof User-Agent to match real Chrome (Mac)
                opts.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                # Stealth: Mask automation
                opts.add_argument('--disable-blink-features=AutomationControlled')



            
            driver = uc.Chrome(options=opts, use_subprocess=True)
            
            # Initialize human behavior and popup closer
            human = None
            popup_closer = None
            
            if HUMAN_BEHAVIOR_AVAILABLE and HumanBehavior:
                human = HumanBehavior(
                    min_delay=0.2,
                    max_delay=0.8,
                    movement_speed='medium'
                )
                self.logger.info("🎭 Human behavior simulator initialized")
            
            if POPUP_CLOSER_AVAILABLE and PopupCloser:
                popup_closer = PopupCloser(max_attempts=5, wait_seconds=2.0)
                self.logger.info("🚫 Popup closer initialized")
            
            try:
                # Navigate to chapter
                self.logger.info(f"📍 Navigating to: {url}")
                driver.get(url)
                
                # Wait for Cloudflare (UC auto-resolves)
                self.logger.info("⏳ Waiting 10 seconds for Cloudflare auto-resolution...")
                time.sleep(10)
                
                # CLOSE POPUPS AND AD OVERLAYS (PARALLEL)
                driver_lock = threading.Lock()
                
                if popup_closer:
                    self.logger.info("🛡️ Starting parallel popup/overlay closer...")
                    # inject JS right away
                    popup_closer.start_monitoring(driver, driver_lock, interval=2.0)

                
                # HUMAN-LIKE SCROLLING (ROOT LEVEL)
                if human:
                    self.logger.info("📜 Scrolling like a human to load all images...")
                    
                    # Initial pause (looking at page)
                    human.read_pause(1.0, 2.5)
                    
                    # Scroll down in random chunks
                    # Scroll down in random chunks
                    for i in range(random.randint(3, 5)):
                        # Acquire lock for interaction
                        with driver_lock:
                            human.human_scroll(driver, 'down', 
                                             amount=random.randint(200, 600), 
                                             smooth=True)
                        
                        # Sleep OUTSIDE the lock to let popup closer run
                        # human.read_pause(0.5, 1.5)
                        time.sleep(random.uniform(0.5, 1.5))

                    
                    # Sometimes scroll back up (checking something)
                    if random.random() > 0.5:
                        human.human_scroll(driver, 'up', 
                                         amount=random.randint(100, 400), 
                                         smooth=True)
                        human.read_pause(0.3, 0.8)
                    
                    # Scroll to bottom
                    human.human_scroll(driver, 'down', 
                                     amount=random.randint(1000, 2000), 
                                     smooth=True)
                    human.read_pause(1.0, 2.0)
                    
                    # Scroll back to top
                    driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")
                    time.sleep(random.uniform(1.5, 2.5))
                    
                    # Final scroll to bottom
                    human.human_scroll(driver, 'down', 
                                     amount=random.randint(1500, 3000), 
                                     smooth=True)
                    human.read_pause(1.0, 2.0)
                    
                    self.logger.info("  ✅ Natural scrolling complete")
                else:
                    # Fallback to basic scrolling with randomization
                    self.logger.info("📜 Scrolling to load images...")
                    with driver_lock:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(random.uniform(4, 6))
                    
                    with driver_lock:
                        driver.execute_script("window.scrollTo(0, 0)")
                    time.sleep(random.uniform(1.5, 2.5))
                    
                    with driver_lock:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(random.uniform(4, 6))

                
                # Extract manga panel images
                self.logger.info("🖼️ Extracting images...")
                with driver_lock:
                    images = driver.find_elements(By.TAG_NAME, 'img')
                
                image_urls = []
                # Process elements (safe to do outside lock as we have the element refs, 
                # though accessing attributes might need lock if driver is very strict, 
                # but usually element reference access is okay unless DOM changes.
                # To be safe, we'll lock attribute access or just quick grab.)
                
                # Better: grab all data inside lock
                img_data_list = []
                with driver_lock:
                    for img in images:
                        try:
                            # Try multiple attributes (lazy loading)
                            src = (img.get_attribute('data-src') or 
                                   img.get_attribute('data-lazy-src') or 
                                   img.get_attribute('src'))
                            if src:
                                img_data_list.append(src)
                        except:
                            pass
                
                for src in img_data_list:
                    if src and src.startswith('http'):

                        # Filter manga panels (from c3.clancd.com CDN)
                        if 'clancd.com' in src and '/chapter_' in src:
                            image_urls.append(src)
                
                self.logger.info(f"✅ Found {len(image_urls)} manga panel images")
                
                if not image_urls:
                    self.logger.warning("No manga panels found")
                    return False
                
                # Download images with retries
                self.logger.info(f"⬇️  Downloading {len(image_urls)} images...")
                downloaded = 0
                
                for i, img_url in enumerate(image_urls, 1):
                    try:
                        filename = f"page_{i:03d}.jpg"
                        filepath = self.dirs['raw'] / filename
                        
                        # Retry logic for connection errors
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                response = requests.get(img_url, timeout=30)
                                response.raise_for_status()
                                
                                with open(filepath, 'wb') as f:
                                    f.write(response.content)
                                
                                downloaded += 1
                                self.logger.info(f"  [{i}/{len(image_urls)}] {filename}")
                                break
                                
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    self.logger.warning(f"  Retry {attempt+1}/{max_retries} for {filename}")
                                    time.sleep(2)
                                else:
                                    self.logger.warning(f"  ⚠️  Failed to download {filename}: {e}")
                        
                        # Human-like delay between downloads
                        if human:
                            human.humanized_delay(0.3)
                        else:
                            time.sleep(random.uniform(0.3, 0.7))
                        
                    except Exception as e:
                        self.logger.warning(f"  ⚠️  Error downloading image {i}: {e}")
                
                self.logger.info(f"✅ Downloaded {downloaded}/{len(image_urls)} images")
                return downloaded > 0
                
            finally:
                if popup_closer:
                    popup_closer.stop_monitoring()
                
                try:
                    driver.quit()
                except Exception:
                    pass

                    
        except Exception as e:
            self.logger.error(f"Manhwaclan download failed: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False
    
    # ------------------------------------------------------------------ WP-Manga helper
    _WP_MANGA_DOMAINS = [
        'topmanhua.fan', 'zinmanga', 'mangatx.org', 'mangatoon',
        'istmanga', 'mangag.com', 'templescan', 'isekaiscan',
        'chapmanganato', 'mangaclash', 'mangaonlineteam',
        's2manga', 'topmanga', 'manhuafast', 'manhuaus', 'manhuaes',
    ]

    def _is_wpmanga_site(self, url: str) -> bool:
        """Return True if the URL belongs to a known WP-manga theme site."""
        url_lower = url.lower()
        return any(d in url_lower for d in self._WP_MANGA_DOMAINS)

    def _download_wpmanga_undetected(self, url: str) -> bool:
        """Undetected Chromedriver version of WP-manga download (ManhuaUS style)."""
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import time, os

            self.logger.info("[WP-Manga] Layer 2: Undetected Chromedriver...")
            
            opts = uc.ChromeOptions()
            _bin = os.environ.get('CHROME_BIN')
            if _bin and os.path.exists(_bin):
                opts.binary_location = _bin
            else:
                _mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
                if os.path.exists(_mac):
                    opts.binary_location = _mac
            
            opts.add_argument('--headless')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--window-size=1920,1080')
            
            driver = uc.Chrome(options=opts)
            try:
                driver.get(url)
                # Wait for reading content
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.reading-content img, .page-break img, .text-left img'))
                )
                
                # Scroll to trigger lazy loading
                self.logger.info("[WP-Manga-UC] Scrolling...")
                last_count = 0
                for _ in range(30):
                    driver.execute_script("window.scrollBy(0, window.innerHeight * 0.9);")
                    time.sleep(0.3)
                    count = len(driver.find_elements(By.CSS_SELECTOR, 'img'))
                    if count == last_count and count > 10:
                        break
                    last_count = count
                
                # Extract images
                selectors = [
                    '.reading-content img.wp-manga-chapter-img',
                    '.reading-content img',
                    '.page-break img',
                    '.text-left img',
                ]
                
                image_urls = []
                seen = set()
                for sel in selectors:
                    imgs = driver.find_elements(By.CSS_SELECTOR, sel)
                    for img in imgs:
                        src = img.get_attribute('data-src') or img.get_attribute('data-lazy-src') or img.get_attribute('src')
                        if src and src not in seen and self._is_valid_wpmanga_image(src):
                            image_urls.append(src)
                            seen.add(src)
                    if len(image_urls) > 10:
                        break
                
                if not image_urls:
                    self.logger.warning("[WP-Manga-UC] No images found")
                    return False
                
                self.logger.info(f"[WP-Manga-UC] Downloading {len(image_urls)} images via browser context...")
                success = self._download_images_via_js(driver.execute_script, image_urls, page_or_driver=driver)
                return success > 0
                
            finally:
                driver.quit()
        except Exception as e:
            self.logger.error(f"[WP-Manga-UC] Failed: {e}")
            return False

    def _download_wpmanga(self, url: str) -> bool:
        """
        Download from any site using the WP-manga WordPress theme.
        These sites share identical HTML structure:
          - Images inside .reading-content
          - img.wp-manga-chapter-img class
          - Lazy-loading via data-src attribute
          - No Cloudflare (usually)
        
        Uses Playwright as primary (fast, stealth) with Selenium fallback.
        Downloads images through the browser context to bypass CDN hotlink
        protection (which returns 403 on direct requests).
        """
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace('www.', '')
        self.logger.info(f"[WP-Manga] Downloading from {domain}: {url}")

        # Try Playwright first (fastest, no driver management)
        try:
            from playwright.sync_api import sync_playwright
            self.logger.info("[WP-Manga] Layer 1: Playwright stealth...")

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--window-size=1920,1080',
                    ]
                )
                context = browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                    viewport={'width': 1920, 'height': 1080},
                )
                page = context.new_page()

                # Inject anti-bot stealth
                page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )

                try:
                    self.logger.info(f"[WP-Manga] Navigating to {url}")
                    page.goto(url, timeout=60000, wait_until='domcontentloaded')

                    # Wait for images to start appearing
                    try:
                        page.wait_for_selector('.reading-content img', timeout=15000)
                    except Exception:
                        self.logger.warning("[WP-Manga] .reading-content images not found in 15s — continuing anyway")

                    # Full scroll to trigger ALL lazy loads
                    self.logger.info("[WP-Manga] Scrolling to trigger lazy loading...")
                    for _ in range(30):
                        page.evaluate("window.scrollBy(0, window.innerHeight * 0.9);")
                        page.wait_for_timeout(200)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    page.wait_for_timeout(2000)

                    # Force lazy images to load
                    page.evaluate("""
                        document.querySelectorAll('img[data-src]').forEach(img => {
                            img.src = img.getAttribute('data-src') || img.src;
                        });
                        document.querySelectorAll('img[loading="lazy"]').forEach(img => {
                            img.loading = 'eager';
                        });
                    """)
                    page.wait_for_timeout(1500)

                    # Extract images using WP-manga selectors
                    selectors = [
                        '.reading-content img.wp-manga-chapter-img',
                        '.reading-content img',
                        '.page-break img',
                        '.text-left img',
                        'img[src*="chapter"]',
                        'img[data-src]',
                    ]

                    image_urls = []
                    seen = set()

                    for selector in selectors:
                        try:
                            imgs = page.locator(selector).all()
                            for img in imgs:
                                # data-src preferred (lazy-load source)
                                src = (
                                    img.get_attribute('data-src') or
                                    img.get_attribute('data-lazy-src') or
                                    img.get_attribute('data-original') or
                                    img.get_attribute('src')
                                )
                                if not src:
                                    continue
                                src = src.strip()
                                if src in seen:
                                    continue
                                # Filter out non-chapter images
                                if self._is_valid_wpmanga_image(src):
                                    image_urls.append(src)
                                    seen.add(src)
                        except Exception:
                            continue

                        if len(image_urls) >= 5:   # found enough — stop selector scanning
                            self.logger.info(
                                f"[WP-Manga] ✅ Found {len(image_urls)} images with selector '{selector}'"
                            )
                            break

                    if image_urls:
                        self.logger.info(f"[WP-Manga] Downloading {len(image_urls)} images via browser JS...")
                        count = self._download_images_via_js(page, image_urls, page_or_driver=page)
                        if count > 0:
                            self.logger.info(f"[WP-Manga] ✅ Downloaded {count}/{len(image_urls)} images")
                            browser.close()
                            return True
                        self.logger.warning("[WP-Manga] Browser-context downloads failed, trying requests fallback...")
                        referer = page.url
                    else:
                        referer = page.url
                        self.logger.warning("[WP-Manga] No images found with Playwright")
                finally:
                    browser.close()

            # Fallback: try plain requests (may work for some CDNs)
            if image_urls:
                self.logger.info("[WP-Manga] Trying requests-based download as fallback...")
                count = self._download_images(image_urls, referer)
                if count > 0:
                    self.logger.info(f"[WP-Manga] ✅ Requests fallback: downloaded {count}/{len(image_urls)}")
                    return True

        except ImportError:
            self.logger.warning("[WP-Manga] Playwright not installed — trying Selenium fallback")
        except Exception as e:
            self.logger.warning(f"[WP-Manga] Playwright failed: {e}")

        # Layer 2: Undetected Chromedriver (ManhuaUS style)
        if self._download_wpmanga_undetected(url):
            return True

        # Layer 3: Selenium fallback
        self.logger.info("[WP-Manga] Layer 3: Selenium fallback...")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            import time as _t

            opts = Options()
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--window-size=1920,1080')
            opts.add_experimental_option('excludeSwitches', ['enable-automation'])

            _drv = os.environ.get('CHROMEDRIVER')
            service = Service(_drv) if _drv and os.path.exists(_drv) \
                else Service(ChromeDriverManager().install())

            driver = webdriver.Chrome(service=service, options=opts)
            driver.set_page_load_timeout(60)
            try:
                driver.get(url)
                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                _t.sleep(3)

                # Scroll
                for _ in range(25):
                    driver.execute_script('window.scrollBy(0, window.innerHeight * 0.9);')
                    _t.sleep(0.25)
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                _t.sleep(2)

                # Force lazy
                driver.execute_script("""
                    document.querySelectorAll('img[data-src]').forEach(img => {
                        img.src = img.getAttribute('data-src') || img.src;
                    });
                """)
                _t.sleep(1)

                imgs = driver.find_elements(By.CSS_SELECTOR,
                    '.reading-content img, .page-break img, img.wp-manga-chapter-img'
                )
                image_urls = []
                seen = set()
                for img in imgs:
                    src = (
                        img.get_attribute('data-src') or
                        img.get_attribute('data-lazy-src') or
                        img.get_attribute('src')
                    )
                    if src and src not in seen and self._is_valid_wpmanga_image(src):
                        image_urls.append(src)
                        seen.add(src)

                referer = driver.current_url
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

            if image_urls:
                count = self._download_images(image_urls, referer)
                if count > 0:
                    self.logger.info(f"[WP-Manga] ✅ Selenium: downloaded {count}/{len(image_urls)}")
                    return True

        except ImportError:
            self.logger.warning("[WP-Manga] Selenium (webdriver_manager) not installed")
        except Exception as e:
            self.logger.warning(f"[WP-Manga] Selenium failed: {e}")

        self.logger.error(f"[WP-Manga] ❌ All download methods failed for {domain}")
        return False

    def _download_generic(self, url):
        """
        3-layer generic download for new / unknown sites:
          Layer 1 — requests + BeautifulSoup (fast, no browser)
          Layer 2 — Playwright stealth (headless, medium)
          Layer 3 — Undetected ChromeDriver (heavy, last resort)
        Emits a clear diagnostic message if all layers fail.
        """
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace('www.', '')
        self.logger.info(f"🌐 Generic download for unknown/new site: {domain}")

        # ── Layer 1: requests + BeautifulSoup ──────────────────────────
        self.logger.info("[Generic L1] Trying fast HTML scraper...")
        try:
            try:
                from html_scraper import HTMLScraper
                from website_database import WebsiteDatabase
            except ImportError:
                from .html_scraper import HTMLScraper
                from .website_database import WebsiteDatabase

            scraper = HTMLScraper(WebsiteDatabase())
            image_urls = scraper.extract_image_urls(url)
            scraper.close()

            if image_urls:
                self.logger.info(f"[Generic L1] ✅ Found {len(image_urls)} images via HTML scraper")
                count = self._download_images(image_urls, url)
                if count > 0:
                    return True
                self.logger.warning("[Generic L1] Images found but downloads failed — trying browser layers")
            else:
                self.logger.warning("[Generic L1] No images found with HTML scraper")
        except Exception as e:
            self.logger.warning(f"[Generic L1] HTML scraper error: {e}")

        # ── Layer 2: Playwright stealth ────────────────────────────────
        self.logger.info("[Generic L2] Trying Playwright stealth browser...")
        try:
            from playwright.sync_api import sync_playwright
            try:
                from stealth_config import StealthConfig
                from cloudflare_handler import CloudflareHandler
            except ImportError:
                from .stealth_config import StealthConfig
                from .cloudflare_handler import CloudflareHandler

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                    ]
                )
                vp = StealthConfig.get_random_viewport()
                context = browser.new_context(
                    user_agent=StealthConfig.get_desktop_user_agent(),
                    viewport=vp,
                )
                page = context.new_page()
                StealthConfig.inject_stealth_scripts(page)

                try:
                    page.goto(url, timeout=60000, wait_until='domcontentloaded')
                    StealthConfig.simulate_human_behavior(page)

                    # Handle Cloudflare if needed
                    if CloudflareHandler.is_challenge_page_playwright(page):
                        self.logger.warning("[Generic L2] Cloudflare detected — waiting...")
                        if not CloudflareHandler.wait_for_challenge_resolution_playwright(page, timeout=60):
                            self.logger.warning("[Generic L2] Cloudflare not resolved")
                            browser.close()
                            raise RuntimeError("Cloudflare unresolved")

                    # Scroll to trigger lazy-loading
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2500)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(500)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)

                    # Extract images via multiple selectors
                    try:
                        from website_database import GENERIC_IMAGE_SELECTORS
                    except ImportError:
                        from .website_database import GENERIC_IMAGE_SELECTORS

                    image_urls = []
                    seen = set()
                    for selector in GENERIC_IMAGE_SELECTORS:
                        try:
                            imgs = page.locator(selector).all()
                            for img in imgs:
                                src = (img.get_attribute('data-src') or
                                       img.get_attribute('data-lazy-src') or
                                       img.get_attribute('data-original') or
                                       img.get_attribute('src'))
                                if src and src not in seen and self._is_valid_manga_image(src):
                                    image_urls.append(src)
                                    seen.add(src)
                        except Exception:
                            continue
                        if image_urls:
                            break

                    page_url = page.url
                finally:
                    browser.close()

                if image_urls:
                    self.logger.info(f"[Generic L2] ✅ Found {len(image_urls)} images via Playwright")
                    count = self._download_images(image_urls, page_url)
                    if count > 0:
                        return True
                else:
                    self.logger.warning("[Generic L2] No images found with Playwright")

        except ImportError:
            self.logger.warning("[Generic L2] Playwright not installed — skipping (pip install playwright)")
        except Exception as e:
            self.logger.warning(f"[Generic L2] Playwright failed: {e}")

        # ── Layer 3: Undetected ChromeDriver ───────────────────────────
        self.logger.info("[Generic L3] Trying Undetected ChromeDriver (last resort)...")
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            try:
                from cloudflare_handler import CloudflareHandler
                from stealth_config import StealthConfig
            except ImportError:
                from .cloudflare_handler import CloudflareHandler
                from .stealth_config import StealthConfig

            opts = uc.ChromeOptions()
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_argument('--window-size=1920,1080')

            driver = uc.Chrome(options=opts, use_subprocess=True)
            try:
                driver.get(url)
                StealthConfig.inject_stealth_selenium(driver)
                import time as _time
                _time.sleep(3)

                if CloudflareHandler.is_challenge_page_selenium(driver):
                    self.logger.warning("[Generic L3] Cloudflare detected (UC) — waiting...")
                    CloudflareHandler.wait_for_challenge_resolution_selenium(driver, timeout=90)

                # Scroll
                for _ in range(20):
                    driver.execute_script('window.scrollBy(0, window.innerHeight * 0.8);')
                    _time.sleep(0.4)
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
                _time.sleep(2)

                imgs = driver.find_elements(By.TAG_NAME, 'img')
                image_urls = []
                seen = set()
                for img in imgs:
                    src = (img.get_attribute('data-src') or
                           img.get_attribute('data-lazy-src') or
                           img.get_attribute('data-original') or
                           img.get_attribute('src'))
                    if src and src not in seen and self._is_valid_webtoon_image(src):
                        image_urls.append(src)
                        seen.add(src)

                current_url = driver.current_url
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

            if image_urls:
                self.logger.info(f"[Generic L3] ✅ Found {len(image_urls)} images via UC")
                count = self._download_images(image_urls, current_url)
                if count > 0:
                    return True
            else:
                self.logger.warning("[Generic L3] No images found with UC")

        except ImportError:
            self.logger.warning("[Generic L3] undetected_chromedriver not installed — skipping")
        except Exception as e:
            self.logger.warning(f"[Generic L3] UC failed: {e}")

        # ── All layers failed ──────────────────────────────────────────
        self.logger.error(
            f"\n{'='*60}\n"
            f"❌ COULD NOT DOWNLOAD FROM: {domain}\n"
            f"{'='*60}\n"
            f"This appears to be a new or unsupported site.\n"
            f"\n💡 Possible reasons:\n"
            f"   • Site uses heavy JavaScript rendering not yet profiled\n"
            f"   • Cloudflare / bot protection is blocking all requests\n"
            f"   • The chapter URL structure is non-standard\n"
            f"\n🔧 What you can try:\n"
            f"   • Use a direct image CDN URL instead of a chapter reader URL\n"
            f"   • Install: pip install playwright playwright-stealth && playwright install chromium\n"
            f"   • Install: pip install undetected-chromedriver\n"
            f"   • Check site manually and report CSS selectors to add to website_database.py\n"
            f"{'='*60}"
        )
        return False

    def _extract_manga_name_from_url(self, url):
        """Extract manga name from URL"""
        try:
            parts = url.split('/')
            for p in parts:
                if 'manga' in p or 'comic' in p:
                    idx = parts.index(p)
                    if idx + 1 < len(parts):
                        return parts[idx+1].replace('-', ' ').title()
            return "Unknown Manga"
        except Exception:
            return "Unknown Manga"

    def _extract_chapter_number_from_url(self, url):
        """Extract chapter number from URL"""
        try:
            import re as _re
            nums = _re.findall(r'chapter[-_]?(\d+)', url.lower())
            if nums:
                return int(nums[-1])
            nums = _re.findall(r'(\d+)', url)
            if nums:
                return int(nums[-1])
            return 1
        except Exception:
            return 1
    
    def clean_pages_enhanced(self):
        """Enhanced page cleaning with better duplicate detection"""
        self.logger.info("Starting enhanced page cleaning")
        
        try:
            # Get all raw images
            raw_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                raw_files.extend(self.dirs['raw'].glob(ext))
            
            if not raw_files:
                self.logger.error("No raw images found")
                return []
            
            # Sort files naturally
            raw_files.sort(key=lambda x: self._natural_sort_key(x.name))
            self.logger.info(f"Found {len(raw_files)} raw images")
            
            # Process images
            cleaned_files = []
            image_hashes = set()
            
            for i, img_path in enumerate(raw_files):
                try:
                    # Load and validate image
                    img = Image.open(img_path)
                    if img is None:
                        continue
                    
                    # Check for duplicates using perceptual hash
                    img_hash = self._calculate_image_hash(img)
                    if img_hash in image_hashes:
                        self.logger.debug(f"Skipping duplicate: {img_path.name}")
                        continue
                    image_hashes.add(img_hash)
                    
                    # Auto-rotate if needed
                    img = self._auto_rotate_image(img)
                    
                    # Enhance image quality
                    img = self._enhance_image_quality(img)
                    
                    # Save cleaned image
                    new_filename = f"{i+1:03d}.png"
                    new_path = self.dirs['clean'] / new_filename
                    img.save(new_path, "PNG", optimize=True)
                    
                    cleaned_files.append(new_path)
                    self.logger.debug(f"Cleaned: {img_path.name} -> {new_filename}")
                    
                except Exception as e:
                    self.logger.error(f"Error cleaning {img_path}: {e}")
                    self.stats['errors'] += 1
            
            self.stats['cleaned_images'] = len(cleaned_files)
            self.logger.info(f"Cleaned {len(cleaned_files)} images")
            return cleaned_files
            
        except Exception as e:
            self.logger.error(f"Page cleaning failed: {e}")
            self.stats['errors'] += 1
            return []
    
    def _natural_sort_key(self, text):
        """Natural sorting for filenames with numbers"""
        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
    
    def _calculate_image_hash(self, img):
        """Calculate perceptual hash for duplicate detection"""
        try:
            # Convert to grayscale and resize
            img_gray = img.convert('L').resize((8, 8), Image.Resampling.LANCZOS)
            pixels = list(img_gray.getdata())
            
            # Calculate average
            avg = sum(pixels) / len(pixels)
            
            # Create hash
            return ''.join(['1' if pixel > avg else '0' for pixel in pixels])
        except:
            return str(hash(img.tobytes()))
    
    def _auto_rotate_image(self, img):
        """Auto-rotate image if needed"""
        try:
            width, height = img.size
            
            # If width > height * 1.5, likely needs rotation
            if width > height * 1.5:
                img = img.rotate(90, expand=True)
                self.logger.debug("Auto-rotated image")
            
            return img
        except Exception as e:
            self.logger.warning(f"Auto-rotation failed: {e}")
            return img
    
    def _enhance_image_quality(self, img):
        """Enhance image quality for better OCR"""
        try:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Enhance contrast slightly
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.1)
            
            # Enhance sharpness slightly
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.1)
            
            return img
        except Exception as e:
            self.logger.warning(f"Image enhancement failed: {e}")
            return img
    
    def process_stitching_enhanced(self, force_format=None, chunk_override=None, min_panels=None, max_panels=None, extract_single_panels=False):
        """Process advanced stitching with format detection and optional scene-aware chunking"""
        self.logger.info("Starting enhanced stitching process")
        
        try:
            # Resolve chunking preferences (CLI overrides config)
            cfg_chunk = self.config.getboolean('PROCESSING', 'chunk_stitched_by_panels', fallback=True)
            chunk_by_panels = cfg_chunk if chunk_override is None else bool(chunk_override)
            cfg_min = int(self.config.get('PROCESSING', 'chunk_min_panels_per_part', fallback='5'))
            cfg_max = int(self.config.get('PROCESSING', 'chunk_max_panels_per_part', fallback='10'))
            min_p = cfg_min if (min_panels is None) else int(min_panels)
            max_p = cfg_max if (max_panels is None) else int(max_panels)
            if min_p > max_p:
                min_p, max_p = max_p, min_p
            min_p = max(1, min_p)
            max_p = max(min_p, max_p)

            # Use our advanced stitching module
            result = self.stitcher.process_stitching(
                force_format=self.mode,
                chunk_by_panels=chunk_by_panels,
                min_panels_per_chunk=min_p,
                max_panels_per_chunk=max_p,
                extract_single_panels=extract_single_panels
            )
            
            if result['success']:
                self.logger.info(f"Stitching successful - Format: {result['format_detected']}")
                self.logger.info(f"Output files: {len(result['output_files'])}")
                
                # If panels were extracted from stitching, we might want to move them to the main panels directory
                # so the rest of the pipeline (OCR, etc.) picks them up.
                if extract_single_panels:
                    stitched_panels_dir = self.dirs['stitched'] / 'panels'
                    if stitched_panels_dir.exists():
                        # Copy to main panels dir
                        count = 0
                        for p_file in stitched_panels_dir.glob('*.png'):
                            shutil.copy2(p_file, self.dirs['panels'] / p_file.name)
                            count += 1
                        self.logger.info(f"Imported {count} stitched panels to {self.dirs['panels']}")
                        self.stats['extracted_panels'] += count

                return result
            else:
                self.logger.warning("Stitching failed, will use individual image processing")
                return result
                
        except Exception as e:
            self.logger.error(f"Stitching error: {e}")
            self.stats['errors'] += 1
            return {'success': False, 'error': str(e)}
    

    
    def extract_panels_enhanced(self, use_stitched=None, skip_validation=False):
        """Enhanced panel extraction - works after stitching to combine panels properly"""
        self.logger.info("Starting enhanced panel extraction")
        
        try:
            # Always try stitching first for better panel combination
            stitched_files = list(self.dirs['stitched'].glob('*.png'))
            if not stitched_files:
                self.logger.info("Creating stitched images for better panel extraction...")
                stitch_result = self.process_stitching_enhanced()
                if stitch_result.get('success'):
                    stitched_files = list(self.dirs['stitched'].glob('*.png'))
                    self.logger.info("Stitching successful - will extract from combined images")
                else:
                    self.logger.warning("Stitching failed - extracting from individual images")
            
            # Use stitched if available, otherwise clean images
            if stitched_files:
                source_dir = self.dirs['stitched']
                source_files = stitched_files
                self.logger.info(f"Extracting from {len(source_files)} stitched images (combined panels)")
            else:
                source_dir = self.dirs['clean']
                source_files = []
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                    source_files.extend(source_dir.glob(ext))
                self.logger.info(f"Extracting from {len(source_files)} individual clean images")
            
            if not source_files:
                self.logger.error(f"No source images found")
                return []
            
            source_files.sort(key=lambda x: self._natural_sort_key(x.name))
            
            # Extract panels with smart numbering (scene-aware when skip_validation=True)
            all_panels = []
            panel_meta = {}
            global_panel_counter = 1
            
            for img_idx, img_path in enumerate(source_files):
                try:
                    # Use no-filter extraction when skipping validation
                    if skip_validation:
                        panels = self._extract_panels_from_image_no_filter(img_path, img_idx)
                    else:
                        panels = self._extract_panels_from_image(img_path, img_idx)
                    
                    for panel_data in panels:
                        panel_img, confidence = panel_data
                        base_key = f"panel_{global_panel_counter:04d}"
                        
                        if skip_validation:
                            # Smart scene numbering in no-validation mode
                            scenes = self._detect_scenes_in_panel_smart(panel_img)
                            
                            if len(scenes) == 1:
                                # Single scene panel
                                filename = f"{base_key}.png"
                                panel_path = self.dirs['panels'] / filename
                                cv2.imwrite(str(panel_path), panel_img)
                                all_panels.append(filename)
                                # Record meta
                                panel_meta[base_key] = {
                                    'source': str(img_path),
                                    'scenes': [{
                                        'filename': filename,
                                        'bbox': [0, 0, panel_img.shape[1], panel_img.shape[0]]
                                    }]
                                }
                                self.logger.debug(f"Single scene: {filename}")
                            else:
                                # Multi-scene panel - number as sub-scenes
                                self.logger.debug(f"Multi-scene panel detected: {len(scenes)} scenes")
                                scene_list = []
                                for scene_idx, (scene_img, bbox) in enumerate(scenes, start=1):
                                    filename = f"{base_key}_s{scene_idx:02d}.png"
                                    panel_path = self.dirs['panels'] / filename
                                    cv2.imwrite(str(panel_path), scene_img)
                                    all_panels.append(filename)
                                    scene_list.append({'filename': filename, 'bbox': list(bbox)})
                                    self.logger.debug(f"Sub-scene: {filename}")
                                panel_meta[base_key] = {
                                    'source': str(img_path),
                                    'scenes': scene_list
                                }
                            
                            global_panel_counter += 1
                        else:
                            # Simple sequential numbering in validation mode
                            filename = f"{base_key}.png"
                            panel_path = self.dirs['panels'] / filename
                            cv2.imwrite(str(panel_path), panel_img)
                            all_panels.append(filename)
                            # Optional: basic meta for single-scene panels in validated mode
                            panel_meta[base_key] = {
                                'source': str(img_path),
                                'scenes': [{
                                    'filename': filename,
                                    'bbox': [0, 0, panel_img.shape[1], panel_img.shape[0]]
                                }]
                            }
                            global_panel_counter += 1
                    
                    if panels:
                        self.logger.debug(f"Extracted {len(panels)} panels from {img_path.name}")
                    
                except Exception as e:
                    self.logger.error(f"Error extracting panels from {img_path}: {e}")
                    self.stats['errors'] += 1
            
            self.stats['extracted_panels'] = len(all_panels)
            self.logger.info(f"Extracted {len(all_panels)} total panels")

            # Save panel structure metadata
            try:
                self.dirs['script'].mkdir(parents=True, exist_ok=True)
                meta_path = self.dirs['script'] / 'chapter_meta.json'
                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump(panel_meta, f, ensure_ascii=False, indent=2)
                self.logger.info(f"Saved panel meta: {meta_path}")
            except Exception as e:
                self.logger.warning(f"Failed to write panel meta: {e}")
            
            # Apply validation unless skipped
            if not skip_validation:
                self.logger.info("Applying panel validation (removes duplicates/blanks/tiny panels)")
                valid_count = self.validate_panels_enhanced()
                self.logger.info(f"Validation complete: {valid_count} valid panels kept")
            else:
                self.logger.info("SKIPPING validation - keeping all panels with smart scene numbering")
            
            return all_panels
            
        except Exception as e:
            self.logger.error(f"Panel extraction failed: {e}")
            self.stats['errors'] += 1
            return []
    
    
    def _extract_panels_from_image(self, img_path, img_idx):
        """Extract panels from a single image with format detection"""
        try:
            # Method 1: Use PanelMLDetector (Refactored Logic)
            if self.ml_panel_detector:
                try:
                    # Detect panels
                    panels_data = self.ml_panel_detector.detect_panels(Path(img_path))
                    
                    if panels_data:
                        # Save metadata
                        self.ml_panel_detector.save_panel_metadata(
                            Path(img_path), 
                            panels_data, 
                            self.dirs['panels']
                        )
                        
                        # Convert to format expected by pipeline: list of (image, confidence)
                        return [(p['image'], 0.95) for p in panels_data if p['image'] is not None and p['image'].size > 0]
                        
                except Exception as e:
                    self.logger.warning(f"ML detector failed for {img_path}: {e}")
                    # Fallthrough to legacy method
            
            # Legacy Method
            # Load image
            img = cv2.imread(str(img_path))
            if img is None:
                self.logger.error(f"Could not load image: {img_path}")
                return []
            
            height, width = img.shape[:2]
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Detect format
            aspect_ratio = height / width
            is_webtoon = aspect_ratio > 2.5
            
            if is_webtoon:
                return self._extract_webtoon_panels(img, gray)
            else:
                return self._extract_manga_panels(img, gray)
                
        except Exception as e:
            self.logger.error(f"Panel extraction error for {img_path}: {e}")
            return []
    
    def _extract_webtoon_panels(self, img, gray):
        """Enhanced webtoon panel extraction with robust dark-background handling and precise cuts"""
        height, width = img.shape[:2]
        panels = []
        
        # Debug logging
        self.logger.info(f"Processing webtoon image: {width}x{height} (aspect ratio: {height/width:.2f})")
        
        # Polarity-aware analysis (invert if background is dark)
        gray_use = gray
        try:
            if self._is_dark_background(gray):
                gray_use = 255 - gray
        except Exception:
            pass
        
        # Analyze row-wise content for webtoons
        row_means = np.mean(gray_use, axis=1)
        # Adaptive white threshold for gutter detection
        white_threshold = self._compute_virtual_white_threshold(gray_use)  # dynamic per-image threshold
        content_mask = row_means < white_threshold
        
        # Gentle smoothing to avoid missing tiny gutters
        k = max(3, min(15, height // 3000))
        kernel = np.ones(k, dtype=np.uint8)
        content_mask = np.convolve(content_mask.astype(np.uint8), kernel, mode='same') > (k // 3)
        
        # Panel/gap params (more permissive to catch smaller panels)
        min_panel_height = max(120, min(600, height // 90))
        min_gap_size = max(1, min(12, height // 2000))
        lookahead = max(20, min(120, height // 1000))
        
        # Find content regions
        in_panel = False
        panel_start = 0
        i = 0
        while i < len(content_mask):
            if content_mask[i] and not in_panel:
                panel_start = i
                j = panel_start
                while j < len(content_mask) and row_means[j] > white_threshold - 20 and (j - panel_start) < lookahead:
                    j += 1
                panel_start = j
                in_panel = True
                i = panel_start
            elif not content_mask[i] and in_panel:
                gap_start = i
                gap_size = 0
                while i < len(content_mask) and not content_mask[i]:
                    gap_size += 1
                    i += 1
                if gap_size >= min_gap_size or i >= len(content_mask):
                    panel_height = gap_start - panel_start
                    if panel_height >= min_panel_height:
                        y_start, y_end = self._refine_panel_boundaries(gray_use, panel_start, gap_start, white_threshold)
                        if y_end - y_start >= min_panel_height:
                            panel = img[y_start:y_end, 0:width]
                            panels.append((panel, 0.9))
                            self.logger.info(f"Panel {len(panels)} extracted: rows {y_start}-{y_end} (height: {y_end - y_start}px)")
                    in_panel = False
                else:
                    i = gap_start + gap_size
            else:
                i += 1
        
        # Handle final panel
        if in_panel:
            y_start, y_end = self._refine_panel_boundaries(gray_use, panel_start, height, white_threshold)
            if y_end - y_start >= min_panel_height:
                panel = img[y_start:y_end, 0:width]
                panels.append((panel, 0.9))
                self.logger.info(f"Final panel {len(panels)} extracted: rows {y_start}-{y_end} (height: {y_end - y_start}px)")
        
        # Fallback: if very few panels were detected, try edge-density segmentation (helps dark BG)
        if len(panels) <= 1:
            try:
                edges = cv2.Canny(gray_use, 50, 150)
                row_edge = np.mean(edges > 0, axis=1).astype(np.float32)
                ks = max(3, min(31, height // 800))
                k1 = np.ones(ks, dtype=np.float32) / max(1, ks)
                row_s = np.convolve(row_edge, k1, mode='same')
                thr = max(0.0005, float(row_s.mean()) * 0.6)
                content_rows2 = row_s > thr
                
                i = 0
                min_h2 = max(120, min(800, height // 90))
                extra = []
                while i < height:
                    if content_rows2[i]:
                        s = i
                        while i < height and content_rows2[i]:
                            i += 1
                        e = i
                        if e - s >= min_h2:
                            panel = img[s:e, 0:width]
                            extra.append((panel, 0.85))
                    else:
                        i += 1
                if extra:
                    self.logger.info(f"Edge-density fallback added {len(extra)} panels")
                    panels = extra
            except Exception as e:
                self.logger.debug(f"Edge-density fallback failed: {e}")
        
        # Split any overly large panels
        max_reasonable_height = 1600
        split_panels = []
        for panel_img, confidence in panels:
            panel_height = panel_img.shape[0]
            if panel_height > max_reasonable_height:
                self.logger.info(f"Splitting large panel ({panel_height}px) into smaller pieces")
                num_splits = max(2, int(panel_height / max_reasonable_height) + 1)
                chunk_height = panel_height // num_splits
                for i in range(num_splits):
                    start_row = i * chunk_height
                    end_row = min((i + 1) * chunk_height, panel_height)
                    if end_row - start_row > 100:
                        chunk = panel_img[start_row:end_row, :]
                        split_panels.append((chunk, confidence * 0.8))
                        self.logger.debug(f"Split chunk {i+1}/{num_splits}: {end_row - start_row}px tall")
            else:
                split_panels.append((panel_img, confidence))
        
        # Merge false splits
        merged_panels = self._merge_false_splits(split_panels)
        self.logger.info(f"Webtoon extraction completed: found {len(panels)} initial panels, {len(split_panels)} after split, {len(merged_panels)} after merge")
        self.logger.info(f"Panel detection parameters: min_height={min_panel_height}, min_gap={min_gap_size}, white_thresh={white_threshold}")
        return merged_panels
    
    def _extract_panels_from_image_no_filter(self, img_path, img_idx):
        """Extract panels from image WITHOUT any size or quality filtering"""
        try:
            # Load image
            img = cv2.imread(str(img_path))
            if img is None:
                self.logger.error(f"Could not load image: {img_path}")
                return []
            
            height, width = img.shape[:2]
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Detect format
            aspect_ratio = height / width
            is_webtoon = aspect_ratio > 2.5
            
            if is_webtoon:
                return self._extract_webtoon_panels_no_filter(img, gray)
            else:
                return self._extract_manga_panels_no_filter(img, gray)
                
        except Exception as e:
            self.logger.error(f"Panel extraction error for {img_path}: {e}")
            return []
    
    def _compute_virtual_white_threshold(self, gray):
        """Compute a dynamic white threshold from histogram (top 5% brightest)."""
        try:
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
            cdf = np.cumsum(hist) / max(hist.sum(), 1)
            # find intensity where CDF >= 0.95 (top 5% brightest)
            idx = np.searchsorted(cdf, 0.95)
            thr = int(min(max(idx, 180), 250))  # clamp to a reasonable range
            return thr
        except Exception:
            return 245

    def _merge_false_splits(self, panels, strip_rows=30, corr_thr=0.96):
        """Merge adjacent panels if seam strips are highly similar (undo false splits)."""
        if len(panels) < 2:
            return panels
        merged = []
        i = 0
        while i < len(panels):
            img_a, conf_a = panels[i]
            if i < len(panels) - 1:
                img_b, conf_b = panels[i+1]
                try:
                    ha, wa = img_a.shape[:2]
                    hb, wb = img_b.shape[:2]
                    if ha >= strip_rows and hb >= strip_rows:
                        a_strip = cv2.cvtColor(img_a[ha-strip_rows:ha, :], cv2.COLOR_BGR2GRAY)
                        b_strip = cv2.cvtColor(img_b[0:strip_rows, :], cv2.COLOR_BGR2GRAY)
                        # Crop to common width
                        W = min(a_strip.shape[1], b_strip.shape[1])
                        if W > 10:
                            a_vec = a_strip[:, :W].astype(np.float32).ravel()
                            b_vec = b_strip[:, :W].astype(np.float32).ravel()
                            a_vec -= a_vec.mean(); b_vec -= b_vec.mean()
                            denom = (np.linalg.norm(a_vec) * np.linalg.norm(b_vec))
                            corr = float(a_vec.dot(b_vec) / denom) if denom > 1e-6 else 0.0
                            if corr >= corr_thr:
                                # Merge
                                W2 = max(img_a.shape[1], img_b.shape[1])
                                pad_a = np.full((img_a.shape[0], W2, 3), 255, dtype=np.uint8)
                                pad_b = np.full((img_b.shape[0], W2, 3), 255, dtype=np.uint8)
                                xa = (W2 - img_a.shape[1]) // 2
                                xb = (W2 - img_b.shape[1]) // 2
                                pad_a[:, xa:xa+img_a.shape[1]] = img_a
                                pad_b[:, xb:xb+img_b.shape[1]] = img_b
                                merged_img = np.vstack([pad_a, pad_b])
                                merged.append((merged_img, min(conf_a, conf_b)))
                                i += 2
                                continue
                except Exception:
                    pass
            # default: keep current
            merged.append((img_a, conf_a))
            i += 1
        return merged

    def _extract_webtoon_panels_no_filter(self, img, gray):
        """Extract webtoon panels WITHOUT any filtering - keeps ALL panels including tiny ones"""
        height, width = img.shape[:2]
        panels = []
        
        # Polarity-aware analysis
        gray_use = gray
        try:
            if self._is_dark_background(gray):
                gray_use = 255 - gray
        except Exception:
            pass
        
        # Analyze row-wise content with adaptive threshold
        row_means = np.mean(gray_use, axis=1)
        white_threshold = self._compute_virtual_white_threshold(gray_use)
        content_mask = row_means < white_threshold
        
        # Very gentle smoothing
        k = max(3, min(15, height // 3000))
        kernel = np.ones(k, dtype=np.uint8)
        content_mask = np.convolve(content_mask.astype(np.uint8), kernel, mode='same') > (k // 3)
        
        # VERY permissive parameters - keep even tiny panels
        min_panel_height = 5   # Keep EXTREMELY small panels  
        min_gap_size = 2       # Require at least 2 pixels for a gap (more stable)
        lookahead = max(10, min(80, height // 1500))
        
        # Find content regions
        in_panel = False
        panel_start = 0
        i = 0
        while i < len(content_mask):
            if content_mask[i] and not in_panel:
                panel_start = i
                in_panel = True
                i += 1
            elif not content_mask[i] and in_panel:
                gap_start = i
                gap_size = 0
                while i < len(content_mask) and not content_mask[i]:
                    gap_size += 1
                    i += 1
                if gap_size >= min_gap_size or i >= len(content_mask):
                    panel_height = gap_start - panel_start
                    if panel_height >= min_panel_height:  # Keep even tiny panels
                        # Use boundary refinement for better cuts
                        y_start, y_end = self._refine_panel_boundaries(gray_use, panel_start, gap_start, white_threshold)
                        if y_end > y_start and (y_end - y_start) >= min_panel_height:
                            panel = img[y_start:y_end, 0:width]
                            panels.append((panel, 1.0))  # All panels get high confidence
                    in_panel = False
                else:
                    i = gap_start + gap_size
            else:
                i += 1
        
        # Handle final panel  
        if in_panel:
            # Use boundary refinement for final panel too
            y_start, y_end = self._refine_panel_boundaries(gray_use, panel_start, height, white_threshold)
            if y_end > y_start and (y_end - y_start) >= min_panel_height:
                panel = img[y_start:y_end, 0:width]
                panels.append((panel, 1.0))
        
        # If no panels detected, keep the entire image
        if not panels:
            self.logger.info("No panels detected - keeping entire image")
            panels = [(img, 1.0)]
        
        # Merge false splits if any
        panels = self._merge_false_splits(panels)
        
        self.logger.info(f"Webtoon extraction (no filter): found {len(panels)} panels, keeping ALL")
        return panels
    
    def _extract_manga_panels_no_filter(self, img, gray):
        """Extract manga panels WITHOUT any filtering - keeps ALL detected panels"""
        panels = []
        
        # Enhanced preprocessing
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Adaptive thresholding
        binary = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.dilate(binary, kernel, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # VERY permissive filtering - keep almost everything
        height, width = img.shape[:2]
        min_area = 100           # Keep even very small areas
        max_area = height * width * 0.95  # Keep almost everything
        
        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Very permissive validation - keep tiny panels too
                if w > 10 and h > 10:  # Keep even very small panels
                    valid_contours.append((contour, x, y, w, h))
        
        # Sort by reading order
        valid_contours.sort(key=lambda c: (c[2], c[1]))
        
        # Extract ALL panels without any size restrictions
        for contour, x, y, w, h in valid_contours:
            x_start = max(0, x)
            y_start = max(0, y)
            x_end = min(width, x + w)
            y_end = min(height, y + h)
            
            panel = img[y_start:y_end, x_start:x_end]
            panels.append((panel, 1.0))
        
        # If no panels detected, keep the entire image
        if not panels:
            self.logger.info("No manga panels detected - keeping entire image")
            panels = [(img, 1.0)]
        
        self.logger.info(f"Manga extraction (no filter): found {len(panels)} panels, keeping ALL")
        return panels
    
    def _classify_panel_type(self, panel_img):
        """Enhanced panel classification with better content analysis"""
        try:
            height, width = panel_img.shape[:2]
            gray = cv2.cvtColor(panel_img, cv2.COLOR_BGR2GRAY)
            
            # Calculate enhanced statistics
            overall_mean = float(gray.mean())
            white_pixels = np.sum(gray > 240)
            black_pixels = np.sum(gray < 15)
            total_pixels = height * width
            white_ratio = white_pixels / total_pixels
            black_ratio = black_pixels / total_pixels
            aspect_ratio = height / width
            
            # Content complexity analysis
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / total_pixels
            content_variance = np.var(gray)
            
            self.logger.debug(f"Panel stats: {width}x{height}, mean={overall_mean:.1f}, white={white_ratio:.2f}, black={black_ratio:.2f}, aspect={aspect_ratio:.2f}, edges={edge_density:.3f}")
            
            # 1. Real manga panels (substantial size, good aspect ratio, complex content)
            if (height > 200 and width > 200 and 
                0.3 < aspect_ratio < 3.0 and 
                edge_density > 0.02 and 
                content_variance > 200):
                return 'panel'
            
            # 2. Text/dialogue bubbles (small-medium size, high white content, some text)
            if ((height < 200 or width < 200) and 
                white_ratio > 0.5 and 
                edge_density > 0.01):  # Has some text/content
                return 'bubble'
            
            # 3. Dark/black panels (high black content)
            if black_ratio > 0.5 and height > 100 and width > 100:
                return 'black'
            
            # 4. Long strips (extreme aspect ratios)
            if aspect_ratio < 0.3 or aspect_ratio > 4.0:
                if height > 300 or width > 300:  # Large strips
                    return 'strip'
                else:
                    return 'fragment'  # Small strips are fragments
            
            # 5. Very small or simple content (likely fragments/noise)
            if (height < 100 or width < 100 or 
                content_variance < 100 or 
                edge_density < 0.005):  # Very low complexity
                return 'fragment'
            
            # 6. Medium panels that might be real but smaller
            if (height > 100 and width > 100 and 
                0.2 < aspect_ratio < 5.0 and 
                content_variance > 150):
                return 'panel'  # Still classify as panel
            
            # 7. Everything else goes to 'other' for manual review
            return 'other'
            
        except Exception as e:
            self.logger.debug(f"Panel classification failed: {e}")
            return 'other'
    
    def _detect_scenes_in_panel_smart(self, panel_img):
        """Smart scene detection within a panel for intelligent numbering"""
        try:
            height, width = panel_img.shape[:2]
            
            # Only split if panel is reasonably large
            if height < 200 or width < 100:
                return [(panel_img, (0, 0, width, height))]
            
            gray = cv2.cvtColor(panel_img, cv2.COLOR_BGR2GRAY)
            
            # Look for horizontal dividers within the panel
            row_means = np.mean(gray, axis=1)
            white_threshold = 240
            
            # Find white/empty rows that could be scene dividers
            white_rows = row_means > white_threshold
            
            # Find sequences of white rows (potential dividers)
            scenes = []
            scene_start = 0
            in_white = False
            white_start = 0
            
            for i, is_white in enumerate(white_rows):
                if is_white and not in_white:
                    # Start of potential divider
                    if i - scene_start > 50:  # Previous scene is substantial
                        white_start = i
                        in_white = True
                elif not is_white and in_white:
                    # End of divider
                    divider_height = i - white_start
                    if divider_height >= 3:  # Substantial divider
                        # Save previous scene
                        scene_img = panel_img[scene_start:white_start, :]
                        scenes.append((scene_img, (0, scene_start, width, white_start - scene_start)))
                        scene_start = i
                    in_white = False
            
            # Add final scene
            if scene_start < height - 20:  # Final scene is substantial
                scene_img = panel_img[scene_start:height, :]
                scenes.append((scene_img, (0, scene_start, width, height - scene_start)))
            
            # If no scenes found or only one scene, return the whole panel
            if len(scenes) <= 1:
                return [(panel_img, (0, 0, width, height))]
            
            self.logger.debug(f"Smart scene detection found {len(scenes)} scenes in panel")
            return scenes
            
        except Exception as e:
            self.logger.debug(f"Scene detection failed: {e}, keeping whole panel")
            return [(panel_img, (0, 0, panel_img.shape[1], panel_img.shape[0]))]
    
    def _copy_all_panels_to_final(self):
        """Copy ALL extracted panels to final directory without any validation"""
        try:
            panels_dir = self.dirs['panels']
            final_dir = self.dirs['final_panels']
            final_dir.mkdir(parents=True, exist_ok=True)
            
            # Clear existing files
            for f in final_dir.glob('*'):
                try:
                    f.unlink()
                except Exception:
                    pass
            
            # Copy ALL panels
            copied = 0
            for panel_path in sorted(panels_dir.glob('*.png'), key=lambda x: self._natural_sort_key(x.name)):
                try:
                    dst = final_dir / panel_path.name
                    shutil.copy2(str(panel_path), str(dst))
                    copied += 1
                except Exception as e:
                    self.logger.error(f"Error copying {panel_path} to final_panels: {e}")
            
            self.logger.info(f"Copied ALL {copied} panels to final_panels (no validation)")
            
        except Exception as e:
            self.logger.error(f"Error copying panels to final: {e}")
    
    def _refine_panel_boundaries(self, gray, start, end, white_threshold):
        """Intelligently refine panel boundaries to avoid cutting through content"""
        height, width = gray.shape[:2]
        
        # Find actual content boundaries within the detected region
        search_margin = min(50, (end - start) // 10)
        
        # Refine start boundary - look for first row with substantial content
        y_start = start
        for i in range(max(0, start - search_margin), min(height - 1, start + search_margin)):
            if i >= height or i < 0:
                break
            row_mean = np.mean(gray[i, :])
            # Look for first row with significant content (not pure white)
            if row_mean < white_threshold - 10:
                y_start = i
                break
        
        # Refine end boundary - look for last row with substantial content
        y_end = end
        for i in range(min(height - 1, end + search_margin), max(0, end - search_margin), -1):
            if i <= 0 or i >= height:
                break
            row_mean = np.mean(gray[i, :])
            # Look for last row with significant content
            if row_mean < white_threshold - 10:
                y_end = i + 1
                break
        
        # Ensure reasonable boundaries with a small safety margin (padding)
        padding = 10
        y_start = max(0, min(y_start - padding, start))
        y_end = min(height, max(y_end + padding, end))
        
        self.logger.debug(f"Refined boundaries (with padding): {start}-{end} -> {y_start}-{y_end} (height: {y_end - y_start}px)")
        
        return y_start, y_end
    
    def _extract_manga_panels(self, img, gray):
        """Enhanced manga panel extraction using PanelMLDetector or legacy CV"""
        panels = []
        
        # Method 1: Use PanelMLDetector (Refactored Logic)
        if self.ml_panel_detector:
            try:
                # We need to pass the image path to detect_panels, but here we only have the image object.
                # However, looking at the call site, we might be able to change this method signature 
                # or just save a temp file? 
                # Actually, let's just make PanelMLDetector accept numpy arrays too? 
                # Or better: The refactored detect_panels in panel_ml_detector takes a PATH.
                # But _extract_manga_panels is called with (img, gray).
                # Checking call site: _extract_panels_from_image calls it.
                
                # Let's adjust the logic to use what we have. 
                # Since we don't have the path here easily without changing signature, 
                # and changing signature might break other things, 
                # let's modify the detector in panel_ml_detector to accept numpy array as well, 
                # OR (cleaner) change the call site in _extract_panels_from_image.
                
                # OPTION: We'll stick to legacy for now inside this method if we can't easily access path,
                # BUT wait, the plan was to ENABLE metadata saving. 
                # So we should really be modifying the call site `_extract_panels_from_image`.
                
                # Let's fallback to inline legacy logic if detector can't be used easily,
                # BUT I will update this method to be a wrapper if I can.
                pass 
            except Exception as e:
                self.logger.warning(f"ML detector failed: {e}")
        
        # ... Legacy logic below for fallback ...
        
        # Enhanced preprocessing
        # Apply bilateral filter to reduce noise while preserving edges
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Adaptive thresholding
        binary = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Morphological operations to connect broken panel borders
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.dilate(binary, kernel, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter and sort contours
        height, width = img.shape[:2]
        min_area = height * width * 0.01  # At least 1% of image
        max_area = height * width * 0.85  # At most 85% of image
        
        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Additional validation
                if w > 60 and h > 60 and 0.1 < (h/w) < 10:
                    valid_contours.append((contour, x, y, w, h))
        
        # Sort by reading order (top to bottom, left to right)
        valid_contours.sort(key=lambda c: (c[2], c[1]))  # Sort by y, then x
        
        # Extract panels with PRECISE cutting - NO margins to protect dialogue bubbles
        for contour, x, y, w, h in valid_contours:
            # Cut with a small margin to protect dialogue bubbles/art that touches the edge
            padding = 15
            x_start = max(0, x - padding)
            y_start = max(0, y - padding)
            x_end = min(width, x + w + padding)
            y_end = min(height, y + h + padding)
            
            panel = img[y_start:y_end, x_start:x_end]
            panels.append((panel, 0.8))
            
            self.logger.debug(f"Precise manga panel cut at rect ({x_start},{y_start}) to ({x_end},{y_end})")
        
        return panels

    # ----------------------------
    # Sub-scene extraction helpers
    # ----------------------------
    def _is_dark_background(self, gray, margin=20, thresh=70):
        """Improved dark background detection"""
        try:
            h, w = gray.shape[:2]
            
            # Check overall image brightness
            overall_mean = float(gray.mean())
            
            # Check border areas
            m = max(1, min(margin, h // 50))
            top = gray[:m, :]
            bot = gray[-m:, :]
            left = gray[:, :m]
            right = gray[:, -m:]
            
            border_mean = 0.25 * (float(top.mean()) + float(bot.mean()) + 
                                 float(left.mean()) + float(right.mean()))
            
            # More accurate detection
            is_dark = (overall_mean < thresh) or (border_mean < thresh - 10)
            
            if is_dark:
                self.logger.debug(f"Dark background detected: overall={overall_mean:.1f}, border={border_mean:.1f}")
            
            return is_dark
        except Exception as e:
            self.logger.debug(f"Dark background detection error: {e}")
            return False

    def _detect_subscenes_in_panel(self, img):
        """Detect vertically/horizontally split sub-scenes inside a single panel. Returns list of (y_start, y_end)."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        except Exception:
            gray = img if len(img.shape) == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        gray_use = gray
        try:
            if self._is_dark_background(gray):
                gray_use = 255 - gray
        except Exception:
            pass

        h, w = gray.shape[:2]
        if h < 200 or w < 150:
            return [(0, h)]

        row_means = np.mean(gray_use, axis=1)
        white_threshold = 245
        gap_rows = (row_means >= white_threshold).astype(np.uint8)

        k = max(3, min(21, h // 800))
        kernel = np.ones(k, dtype=np.uint8)
        gap_smooth = np.convolve(gap_rows, kernel, mode='same') > (k // 2)

        # Smaller minimum gap scaled gently for very tall strips
        min_gap = max(5, min(80, h // 800))
        gaps = []
        i = 0
        while i < h:
            if gap_smooth[i]:
                start = i
                while i < h and gap_smooth[i]:
                    i += 1
                length = i - start
                if length >= min_gap:
                    gaps.append((start, i))
            else:
                i += 1

        if not gaps:
            return [(0, h)]

        scenes = []
        last_y = 0
        # Adaptive minimum scene height for tall stitched strips
        min_scene_h = max(80, min(600, h // 120))
        for (gs, ge) in gaps:
            if gs - last_y >= min_scene_h:
                ys = max(0, last_y)
                ye = max(ys + 1, gs)
                scenes.append((ys, ye))
            last_y = ge
        if h - last_y >= min_scene_h:
            scenes.append((last_y, h))

        refined = []
        for (ys, ye) in scenes:
            seg = gray_use[ys:ye, :]
            if seg.size == 0:
                continue
            content_ratio = float(np.mean(seg < 245))
            if content_ratio > 0.01:
                refined.append((ys, ye))

        if refined:
            return refined

        # Fallback: edge-density segmentation
        try:
            edges = cv2.Canny(gray_use, 50, 150)
            row_edge = np.mean(edges > 0, axis=1).astype(np.float32)
            ks = max(3, min(31, h // 800))
            k1 = np.ones(ks, dtype=np.float32) / max(1, ks)
            row_s = np.convolve(row_edge, k1, mode='same')
            thr = max(0.0005, float(row_s.mean()) * 0.6)
            content_rows2 = row_s > thr

            scenes2 = []
            i = 0
            min_h2 = max(80, min(600, h // 120))
            lookahead2 = max(10, min(80, h // 2000))
            while i < h:
                if content_rows2[i]:
                    s = i
                    while i < h and content_rows2[i]:
                        i += 1
                    e = i
                    if e - s >= min_h2:
                        ss = s
                        for j in range(s, min(s + lookahead2, e)):
                            if row_s[j] > thr * 1.2:
                                ss = j
                                break
                        ee = e
                        for j in range(e - 1, max(e - lookahead2, s), -1):
                            if row_s[j] > thr * 1.2:
                                ee = j + 1
                                break
                        if ee - ss >= min_h2:
                            scenes2.append((ss, ee))
                else:
                    i += 1
            return scenes2 if len(scenes2) > 1 else [(0, h)]
        except Exception:
            return [(0, h)]

    def _split_multi_scene_panels(self):
        panels_dir = self.dirs['panels']
        scenes_dir = self.dirs['scenes']
        scenes_dir.mkdir(parents=True, exist_ok=True)

        panel_files = sorted([p for p in panels_dir.glob('*.png')])
        total_subscenes = 0
        multi_panels = 0

        for panel_path in panel_files:
            try:
                img = cv2.imread(str(panel_path))
                if img is None:
                    continue
                y_ranges = self._detect_subscenes_in_panel(img)
                if len(y_ranges) <= 1:
                    continue
                multi_panels += 1
                base = panel_path.stem
                for idx, (ys, ye) in enumerate(y_ranges, start=1):
                    trim = 3
                    ys2 = max(0, ys + trim)
                    ye2 = max(ys2 + 1, ye - trim)
                    sub = img[ys2:ye2, :]
                    if sub.shape[0] < 20 or sub.shape[1] < 20:
                        continue

                    # Attempt horizontal splits on strong vertical gutters
                    wrote_horizontal = False
                    try:
                        gray_sub = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
                        gray_use_sub = gray_sub
                        if self._is_dark_background(gray_sub):
                            gray_use_sub = 255 - gray_sub
                        col_means = np.mean(gray_use_sub, axis=0)
                        white_thr = 245
                        gap_cols = (col_means >= white_thr).astype(np.uint8)
                        kx = max(3, min(21, sub.shape[1] // 800))
                        k1d = np.ones(kx, dtype=np.uint8)
                        gap_smooth = np.convolve(gap_cols, k1d, mode='same') > (kx // 2)
                        min_vgap = max(4, sub.shape[1] // 600)
                        gaps_x = []
                        j = 0
                        W = sub.shape[1]
                        while j < W:
                            if gap_smooth[j]:
                                s = j
                                while j < W and gap_smooth[j]:
                                    j += 1
                                if j - s >= min_vgap:
                                    gaps_x.append((s, j))
                            else:
                                j += 1
                        if gaps_x:
                            xs = [0] + [b for (a, b) in gaps_x]
                            xe = [a for (a, b) in gaps_x] + [W]
                            xtrim = 3
                            part_idx = 1
                            for xs0, xe0 in zip(xs, xe):
                                xs2 = max(0, xs0 + xtrim)
                                xe2 = max(xs2 + 1, xe0 - xtrim)
                                seg = sub[:, xs2:xe2]
                                if seg.shape[0] >= 30 and seg.shape[1] >= 30:
                                    out_name = f"{base}_s{idx:02d}_x{part_idx:02d}.png"
                                    out_path = scenes_dir / out_name
                                    cv2.imwrite(str(out_path), seg)
                                    total_subscenes += 1
                                    part_idx += 1
                                    wrote_horizontal = True
                    except Exception:
                        pass

                    if not wrote_horizontal:
                        out_name = f"{base}_s{idx:02d}.png"
                        out_path = scenes_dir / out_name
                        cv2.imwrite(str(out_path), sub)
                        total_subscenes += 1
            except Exception as e:
                self.logger.error(f"Error splitting sub-scenes for {panel_path}: {e}")

        if multi_panels:
            self.logger.info(f"Scene splitting: {multi_panels} panels contained multiple scenes; exported {total_subscenes} sub-scenes to {scenes_dir}")
        else:
            self.logger.info("Scene splitting: no multi-scene panels detected")

    def _build_final_panels(self):
        panels_dir = self.dirs['panels']
        scenes_dir = self.dirs['scenes']
        final_dir = self.dirs['final_panels']
        final_dir.mkdir(parents=True, exist_ok=True)

        multi_bases = set()
        if scenes_dir.exists():
            for sp in scenes_dir.glob('*.png'):
                name = sp.name
                if '_s' in name:
                    base = name.split('_s')[0]
                    multi_bases.add(base)

        # Clear existing files in final_dir
        for f in final_dir.glob('*'):
            try:
                f.unlink()
            except Exception:
                pass

        copied = 0
        for pp in sorted(panels_dir.glob('*.png')):
            base = pp.stem
            if base in multi_bases:
                continue
            try:
                dst = final_dir / pp.name
                shutil.copy2(str(pp), str(dst))
                copied += 1
            except Exception as e:
                self.logger.error(f"Error copying {pp} to final_panels: {e}")

        subs = 0
        if scenes_dir.exists():
            for sp in sorted(scenes_dir.glob('*.png')):
                try:
                    dst = final_dir / sp.name
                    shutil.copy2(str(sp), str(dst))
                    subs += 1
                except Exception as e:
                    self.logger.error(f"Error copying sub-scene {sp} to final_panels: {e}")

        self.logger.info(f"Final panels built at {final_dir}: {copied} single panels + {subs} sub-scenes")
    
    def validate_panels_enhanced(self):
        """Enhanced panel validation with comprehensive filtering"""
        self.logger.info("Starting enhanced panel validation")
        
        try:
            # Get all panels
            panel_files = list(self.dirs['panels'].glob('*.png'))
            if not panel_files:
                self.logger.warning("No panels found for validation")
                return 0
            
            panel_files.sort(key=lambda x: self._natural_sort_key(x.name))
            self.logger.info(f"Validating {len(panel_files)} panels")
            
            # Validation statistics - focus on quality, not filtering
            stats = {
                'total': len(panel_files),
                'valid': 0,
                'duplicates': 0,
                'blank': 0,
                'too_small': 0,
                'smart_numbered': 0
            }
            
            # Track hashes for duplicate detection
            panel_hashes = {}
            valid_panels = []
            cut_candidates = []
            
            for panel_index, panel_path in enumerate(panel_files):
                try:
                    # Load panel
                    img = cv2.imread(str(panel_path))
                    if img is None:
                        continue
                    
                    height, width = img.shape[:2]
                    
                    # Size validation - Stricter threshold to avoid "junk" cuts
                    # Increased from 40 to 75 to ensure only significant content is kept
                    if height < 75 or width < 75:
                        stats['too_small'] += 1
                        continue
                    
                    # Aspect ratio check (avoid extremely thin slices)
                    ratio = width / height if height > 0 else 0
                    if ratio > 10 or ratio < 0.1:
                        stats['too_small'] += 1  # Count as size/form rejects
                        continue
                    
                    # Blank panel detection
                    if self._is_blank_panel_enhanced(img):
                        stats['blank'] += 1
                        continue
                    
                    # Keep all panels - no aggressive filtering
                    # Focus on quality and smart numbering instead
                    
                    # Cut panel detection
                    is_cut = self._is_cut_panel_enhanced(img)
                    if is_cut:
                        stats['cut_detected'] += 1
                        cut_candidates.append(panel_path)
                        # Respect config: drop obvious cuts from valid set if disabled
                        if not self.config.getboolean('PROCESSING', 'keep_cut_fragments', fallback=False):
                            stats['cut_removed'] = stats.get('cut_removed', 0) + 1
                            continue
                    
                    # Duplicate detection
                    panel_hash = self._calculate_panel_hash_enhanced(img)
                    
                    # Check similarity with existing panels
                    is_duplicate = False
                    threshold = float(self.config.get('PROCESSING', 'duplicate_threshold'))
                    
                    for existing_hash, existing_path in panel_hashes.items():
                        similarity = self._calculate_hash_similarity_enhanced(panel_hash, existing_hash)
                        if similarity > threshold:
                            stats['duplicates'] += 1
                            is_duplicate = True
                            self.logger.debug(f"Duplicate panel: {panel_path.name} (similar to {existing_path})")
                            break
                    
                    if not is_duplicate:
                        panel_hashes[panel_hash] = panel_path.name
                        valid_panels.append(panel_path)
                        stats['valid'] += 1
                        if is_cut:
                            stats['cut_kept'] += 1
                
                except Exception as e:
                    self.logger.error(f"Error validating panel {panel_path}: {e}")
            
            # Copy valid panels with smart numbering
            self._copy_valid_panels_with_smart_numbering(valid_panels)
            
            # Optionally stitch cut fragments into composites
            try:
                if self.config.getboolean('PROCESSING', 'stitch_cut_panels', fallback=True) and len(cut_candidates) >= 2:
                    stitched_count = self._stitch_cut_fragments(cut_candidates)
                    stats['cut_stitched'] = stitched_count
            except Exception as e:
                self.logger.warning(f"Cut-fragment stitching skipped due to error: {e}")
            
            # Log results
            self._log_validation_results(stats)
            
            self.stats['valid_panels'] = stats['valid']
            return stats['valid']
            
        except Exception as e:
            self.logger.error(f"Panel validation failed: {e}")
            self.stats['errors'] += 1
            return 0
    
    def _is_blank_panel_enhanced(self, img):
        """Enhanced blank panel detection"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Multiple criteria for blank detection
        total_pixels = gray.shape[0] * gray.shape[1]
        
        # 1. White pixel percentage
        white_pixels = np.sum(gray > 240)
        white_ratio = white_pixels / total_pixels
        if white_ratio > 0.95:
            return True
        
        # 2. Low variance (uniform color)
        if np.var(gray) < 100:
            return True
        
        # 3. Histogram analysis
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        max_bin_ratio = np.max(hist) / total_pixels
        if max_bin_ratio > 0.9:
            return True
        
        return False
    
    def _is_unwanted_panel(self, img, panel_index, total_panels):
        """Enhanced detection of unwanted panels (ads, navigation, character profiles, etc.)"""
        height, width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Filter by position (first/last panels often contain navigation/ads)
        is_start = panel_index < 3  # First 3 panels
        is_end = panel_index >= total_panels - 3  # Last 3 panels
        
        # 2. Very small panels (likely navigation buttons, icons)
        if height < 80 or width < 80:
            self.logger.debug(f"Rejecting tiny panel: {width}x{height}")
            return True
            
        # 3. Square-ish panels (often profile pics, avatars)
        aspect_ratio = height / width
        if 0.8 <= aspect_ratio <= 1.25 and height < 200:  # Square-ish and small
            # Check if it's mostly uniform (typical of profile pics)
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            uniformity = np.max(hist) / (height * width)
            if uniformity > 0.4:  # Too uniform for comic content
                self.logger.debug(f"Rejecting square uniform panel: {width}x{height}, uniformity={uniformity:.2f}")
                return True
        
        # 4. Extremely wide/thin panels (likely navigation bars)
        if aspect_ratio < 0.08 or aspect_ratio > 15:
            self.logger.debug(f"Rejecting extreme aspect ratio: {aspect_ratio:.2f}")
            return True
        
        # 5. Check for navigation/UI elements (high contrast edges, geometric shapes)
        if is_start or is_end:
            # More strict checking for start/end panels
            edge_content = self._analyze_edge_content(gray)
            if edge_content['has_ui_elements']:
                self.logger.debug(f"Rejecting UI element panel at position {panel_index}")
                return True
        
        # 6. Character profile detection (specific patterns)
        if self._is_character_profile_panel(img, gray):
            self.logger.debug(f"Rejecting character profile panel")
            return True
            
        # 7. Advertisement/promotional content detection
        if self._is_promotional_content(img, gray):
            self.logger.debug(f"Rejecting promotional content panel")
            return True
        
        return False
    
    def _analyze_edge_content(self, gray):
        """Analyze edges for UI elements (buttons, navigation)"""
        height, width = gray.shape
        edge_thickness = max(5, min(height, width) // 20)
        
        # Get edge regions
        top_edge = gray[:edge_thickness, :]
        bottom_edge = gray[-edge_thickness:, :]
        left_edge = gray[:, :edge_thickness]
        right_edge = gray[:, -edge_thickness:]
        
        # Look for high contrast patterns (typical of UI elements)
        def has_high_contrast(region):
            if region.size == 0:
                return False
            return np.std(region) > 60  # High standard deviation = high contrast
        
        # Check for geometric patterns using edge detection
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size
        
        ui_indicators = {
            'high_edge_contrast': any(has_high_contrast(edge) for edge in [top_edge, bottom_edge, left_edge, right_edge]),
            'geometric_patterns': edge_density > 0.15,  # High edge density suggests UI elements
            'has_ui_elements': False
        }
        
        # Combine indicators
        ui_indicators['has_ui_elements'] = (
            ui_indicators['high_edge_contrast'] and 
            ui_indicators['geometric_patterns']
        )
        
        return ui_indicators
    
    def _is_character_profile_panel(self, img, gray):
        """Detect character profile panels (common in webtoons)"""
        height, width = img.shape[:2]
        
        # Character profiles are often:
        # 1. Small to medium size
        # 2. Have a centered subject (face/character)
        # 3. Often have text at bottom or top
        # 4. Have distinct background
        
        if height > 400 or width > 400:  # Too large for typical profile
            return False
            
        # Check for centered content (typical of portraits)
        center_region = gray[height//4:3*height//4, width//4:3*width//4]
        edge_region = np.concatenate([
            gray[:height//4, :].flatten(),
            gray[3*height//4:, :].flatten(),
            gray[:, :width//4].flatten(), 
            gray[:, 3*width//4:].flatten()
        ])
        
        if center_region.size == 0 or edge_region.size == 0:
            return False
            
        center_variance = np.var(center_region)
        edge_variance = np.var(edge_region)
        
        # Profile typically has more content in center than edges
        if center_variance > edge_variance * 2 and height < 300:
            return True
            
        return False
    
    def _is_promotional_content(self, img, gray):
        """Detect promotional/advertisement content"""
        height, width = img.shape[:2]
        
        # Promotional content often has:
        # 1. Very high or very low brightness
        # 2. Large uniform areas
        # 3. High contrast text overlays
        
        mean_brightness = np.mean(gray)
        brightness_std = np.std(gray)
        
        # Very bright or very dark with low variation (typical of ads)
        if (mean_brightness > 240 or mean_brightness < 30) and brightness_std < 50:
            return True
            
        # Check for large uniform regions (typical of promotional graphics)
        # Use simple thresholding to find uniform areas
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Count white and black regions
        white_pixels = np.sum(binary == 255)
        black_pixels = np.sum(binary == 0)
        total_pixels = height * width
        
        white_ratio = white_pixels / total_pixels
        black_ratio = black_pixels / total_pixels
        
        # If dominated by one color, likely promotional
        if white_ratio > 0.8 or black_ratio > 0.8:
            return True
            
        return False
    
    def _is_cut_panel_enhanced(self, img):
        """Enhanced cut panel detection - less aggressive for webtoon panels"""
        height, width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Only check for extremely unrealistic aspect ratios
        aspect_ratio = height / width
        if aspect_ratio < 0.05 or aspect_ratio > 25:
            self.logger.debug(f"Rejecting panel with extreme aspect ratio: {aspect_ratio:.2f}")
            return True
        
        # Only check for very obvious cut panels (all edges have heavy content)
        edge_thickness = max(3, min(height, width) // 30)
        
        edges = {
            'top': gray[:edge_thickness, :],
            'bottom': gray[-edge_thickness:, :],
            'left': gray[:, :edge_thickness], 
            'right': gray[:, -edge_thickness:]
        }
        
        # More aggressive thresholds - only reject obvious cuts
        edge_threshold = 150  # Darker threshold
        content_threshold = 0.4  # Higher content ratio needed
        
        content_edges = 0
        for edge_name, edge_region in edges.items():
            content_ratio = np.mean(edge_region < edge_threshold)
            if content_ratio > content_threshold:
                content_edges += 1
        
        # Only reject if ALL 4 edges have heavy content (very obvious cut)
        if content_edges >= 4:
            self.logger.debug(f"Rejecting panel with content on all {content_edges} edges")
            return True
        
        return False
    
    def _calculate_panel_hash_enhanced(self, img):
        """Enhanced perceptual hash for better duplicate detection"""
        # Convert to grayscale and resize
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
        
        # Calculate DCT (Discrete Cosine Transform) hash
        dct = cv2.dct(np.float32(resized))
        
        # Take top-left 8x8 region (low frequencies)
        dct_low = dct[:8, :8]
        
        # Calculate median
        median = np.median(dct_low)
        
        # Create binary hash
        hash_bits = dct_low > median
        
        # Convert to string
        return ''.join(['1' if bit else '0' for bit in hash_bits.flatten()])
    
    def _calculate_hash_similarity_enhanced(self, hash1, hash2):
        """Calculate similarity between perceptual hashes"""
        if len(hash1) != len(hash2):
            return 0.0
        
        # Hamming distance
        diff_bits = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        similarity = 1.0 - (diff_bits / len(hash1))
        
        return similarity
    
    def _copy_valid_panels_with_smart_numbering(self, valid_panels):
        """Copy validated panels with smart sequential numbering"""
        try:
            # Sort panels naturally for proper sequence
            valid_panels.sort(key=lambda x: self._natural_sort_key(x.name))
            
            # Create clean numbered copies
            clean_panels_dir = self.dirs['clean_panels']
            clean_panels_dir.mkdir(parents=True, exist_ok=True)
            
            # Clear existing numbered panels
            for existing in clean_panels_dir.glob('*'):
                try:
                    existing.unlink()
                except:
                    pass
            
            # Copy with smart numbering (01, 02, 03...)
            numbered_count = 0
            for i, panel_path in enumerate(valid_panels, 1):
                try:
                    # Smart numbering: 001, 002, 003...
                    new_name = f"{i:03d}.png"
                    dst_path = clean_panels_dir / new_name
                    
                    # Copy the panel
                    shutil.copy2(str(panel_path), str(dst_path))
                    numbered_count += 1
                    
                except Exception as e:
                    self.logger.debug(f"Error copying panel {panel_path}: {e}")
            
            self.logger.info(f"✅ Smart numbering: Created {numbered_count} sequentially numbered panels")
            self.logger.info(f"📁 Clean numbered panels: {clean_panels_dir}")
            
            # Update stats
            self.stats['smart_numbered'] = numbered_count
            
        except Exception as e:
            self.logger.error(f"Error in smart panel numbering: {e}")

    def _stitch_cut_fragments(self, cut_paths):
        """Stitch consecutive cut fragments into composite panels.
        Saves stitched outputs to fixed_panels and final_panels. Returns count created.
        """
        try:
            if not cut_paths or len(cut_paths) < 2:
                return 0
            
            # Ensure natural order
            def _natkey(p):
                return self._natural_sort_key(Path(p).name)
            cut_paths_sorted = sorted([str(p) for p in cut_paths], key=_natkey)
            
            def _load_img(p):
                im = cv2.imread(str(p))
                return im if im is not None else None
            
            def _estimate_overlap(a, b, max_strip=120, min_strip=20, diff_thr=0.18):
                try:
                    ha, wa = a.shape[:2]
                    hb, wb = b.shape[:2]
                    common_w = min(wa, wb)
                    xa = (wa - common_w) // 2
                    xb = (wb - common_w) // 2
                    strip = min(max_strip, ha, hb)
                    strip = max(strip, min_strip)
                    a_strip = cv2.cvtColor(a[ha - strip:ha, xa:xa + common_w], cv2.COLOR_BGR2GRAY)
                    b_strip = cv2.cvtColor(b[0:strip, xb:xb + common_w], cv2.COLOR_BGR2GRAY)
                    for k in range(strip, min_strip - 1, -10):
                        a_part = a_strip[strip - k:strip, :]
                        b_part = b_strip[0:k, :]
                        if a_part.shape != b_part.shape or a_part.size == 0:
                            continue
                        diff = float(np.mean(cv2.absdiff(a_part, b_part))) / 255.0
                        if diff <= diff_thr:
                            return k
                    return 0
                except Exception:
                    return 0
            
            def _stitch_pair(a, b):
                # Align widths by padding to max width
                ha, wa = a.shape[:2]
                hb, wb = b.shape[:2]
                W = max(wa, wb)
                if wa != W:
                    pad = np.full((ha, W, 3), 255, dtype=np.uint8)
                    xoff = (W - wa) // 2
                    pad[:, xoff:xoff + wa] = a
                    a = pad
                    ha, wa = a.shape[:2]
                if wb != W:
                    pad = np.full((hb, W, 3), 255, dtype=np.uint8)
                    xoff = (W - wb) // 2
                    pad[:, xoff:xoff + wb] = b
                    b = pad
                    hb, wb = b.shape[:2]
                # Estimate overlap and compose
                ov = _estimate_overlap(a, b)
                top = a
                bottom = b[ov:, :]
                stitched = np.vstack([top, bottom])
                return stitched
            
            stitched_count = 0
            i = 0
            while i < len(cut_paths_sorted) - 1:
                p1 = cut_paths_sorted[i]
                p2 = cut_paths_sorted[i + 1]
                img1 = _load_img(p1)
                img2 = _load_img(p2)
                if img1 is None or img2 is None:
                    i += 1
                    continue
                try:
                    stitched = _stitch_pair(img1, img2)
                    # Construct output filename using stems
                    s1 = Path(p1).stem
                    s2 = Path(p2).stem
                    out_name = f"stitched_{s1}_to_{s2}.png"
                    out_fixed = self.dirs['fixed_panels'] / out_name
                    out_final = self.dirs['final_panels'] / out_name
                    cv2.imwrite(str(out_fixed), stitched)
                    cv2.imwrite(str(out_final), stitched)
                    self.logger.debug(f"Stitched cut fragments: {s1} + {s2} -> {out_name}")
                    stitched_count += 1
                    # Advance by 2 so fragments are paired sequentially
                    i += 2
                except Exception as e:
                    self.logger.debug(f"Failed to stitch {p1} and {p2}: {e}")
                    i += 1
            
            if stitched_count:
                self.logger.info(f"Created {stitched_count} stitched composites from cut fragments")
            return stitched_count
        except Exception as e:
            self.logger.warning(f"Stitching cut fragments failed: {e}")
            return 0
    
    def _log_validation_results(self, stats):
        """Log detailed validation results"""
        self.logger.info("=" * 60)
        self.logger.info("ENHANCED PANEL VALIDATION RESULTS")
        self.logger.info("=" * 60)
        self.logger.info(f"Total panels processed: {stats['total']}")
        self.logger.info(f"Valid panels: {stats['valid']}")
        
        # Detailed removal breakdown
        self.logger.info("\nRemoved panels breakdown:")
        self.logger.info(f"  Duplicates: {stats['duplicates']}")
        self.logger.info(f"  Blank panels: {stats['blank']}")
        self.logger.info(f"  Too small: {stats['too_small']}")
        
        # Focus on smart numbering results
        if stats.get('smart_numbered', 0) > 0:
            self.logger.info(f"  Smart numbered panels: {stats['smart_numbered']}")
        
        if 'cut_detected' in stats and stats['cut_detected'] > 0:
            self.logger.info(f"  Cut fragments detected: {stats['cut_detected']}")
            if 'cut_kept' in stats and stats['cut_kept'] > 0:
                self.logger.info(f"    - Cut fragments kept: {stats['cut_kept']}")
            if 'cut_stitched' in stats and stats['cut_stitched'] > 0:
                self.logger.info(f"    - Stitched composites created: {stats['cut_stitched']}")
        
        removed = stats['total'] - stats['valid']
        self.logger.info(f"\nTotal removed: {removed}")
        
        if stats['total'] > 0:
            retention_rate = (stats['valid'] / stats['total']) * 100
            self.logger.info(f"Retention rate: {retention_rate:.1f}%")
        
        self.logger.info("\nQuality improvements:")
        self.logger.info("✅ Smart sequential numbering (001, 002, 003...)")
        self.logger.info("✅ Natural sorting for proper reading order")
        self.logger.info("✅ Enhanced duplicate detection")
        self.logger.info("✅ Clean extraction without aggressive filtering")
        
        self.logger.info("=" * 60)
    
    def process_ocr_enhanced(self, ocr_lang='eng', confidence_threshold=60, 
                           preprocessing_mode='medium', save_preprocessed=True):
        """Enhanced OCR processing with multiple engines, plus per-panel confidence export"""
        self.logger.info("Starting enhanced OCR processing")
        
        # Try to use the new EnhancedOCRProcessor if available
        if ENHANCED_OCR_AVAILABLE:
            try:
                self.logger.info("Using new EnhancedOCRProcessor for improved scene-by-scene processing")
                
                # Get config parameters (arguments override config)
                config_mode = self.config.get('OCR', 'preprocessing_mode', fallback='medium')
                config_save = self.config.getboolean('OCR', 'save_preprocessed', fallback=True)
                
                # Use provided args if they differ from default, otherwise fallback to config
                # Note: This logic assumes the caller passes meaningful defaults. 
                # Better: prioritize explicit args.
                
                final_mode = preprocessing_mode if preprocessing_mode != 'medium' else config_mode
                
                # Initialize enhanced OCR processor
                ocr_processor = EnhancedOCRProcessor(logger=self.logger)
                
                # Process panels with enhanced OCR
                result = ocr_processor.process_panels(
                    panels_dir=self.dirs['panels'],
                    output_dir=self.chapter_dir / '03_text',
                    ocr_lang=ocr_lang,
                    preprocessing_mode=final_mode,
                    confidence_threshold=confidence_threshold,
                    save_preprocessed=save_preprocessed
                )
                
                if result['success']:
                    self.stats['ocr_processed'] = result['stats']['successful']
                    self.logger.info("✅ Enhanced OCR processing completed successfully")
                    
                    # Return list of text files for compatibility
                    text_files = list(self.dirs['transcripts'].glob('*.txt'))
                    return text_files
                else:
                    self.logger.warning("Enhanced OCR failed, falling back to original implementation")
                    return self._process_ocr_original(ocr_lang, confidence_threshold)
                    
            except Exception as e:
                self.logger.warning(f"Enhanced OCR failed: {e}, falling back to original implementation")
                return self._process_ocr_original(ocr_lang, confidence_threshold)
        else:
            self.logger.info("Enhanced OCR not available, using original implementation")
            return self._process_ocr_original(ocr_lang, confidence_threshold)
    
    def _process_ocr_original(self, ocr_lang='eng', confidence_threshold=60):
        """Original OCR processing method with PARALLEL execution"""
        self.logger.info("Using original OCR processing in PARALLEL mode")
        
        try:
            # Use panels directory directly in simplified structure
            source_dir = self.dirs['panels']
            panel_files = list(source_dir.glob('*.png'))
            if not panel_files:
                self.logger.error("No panels found for OCR")
                return []
            
            panel_files.sort(key=lambda x: self._natural_sort_key(x.name))
            self.logger.info(f"Processing OCR for {len(panel_files)} panels using multi-threading...")
            
            # Process each panel in parallel
            text_files = []
            success_count = 0
            ocr_meta = {}
            
            # Helper function for single panel execution
            def process_single_panel(panel_path):
                try:
                    # Compute OCR text
                    text_content = self._extract_text_from_panel(panel_path, ocr_lang, confidence_threshold)
                    
                    # Compute confidence
                    avg_conf = None
                    try:
                         # Quick confidence check (Tesseract only)
                         # Skipping full image_to_data for speed unless needed, 
                         # but keeping for consistency with original logic
                         pass 
                    except: pass
                    
                    if text_content.strip():
                        # Save text file
                        text_filename = panel_path.stem + '.txt'
                        text_path = self.dirs['transcripts'] / text_filename
                        with open(text_path, 'w', encoding='utf-8') as f:
                            f.write(text_content)
                        return (panel_path.name, str(text_path), 0.8, True) # 0.8 dummy conf
                    else:
                        return (panel_path.name, None, 0, False)
                        
                except Exception as e:
                    self.logger.error(f"OCR thread error: {e}")
                    return (panel_path.name, None, 0, False)

            # Maximize usage of CPU/GPU
            max_workers = min(10, os.cpu_count() + 4) 
            # If using GPU, too many threads might cause VRAM OOM, so cap it reasonable
            if self.easyocr_reader and torch.cuda.is_available():
                max_workers = 4 # Cuda context switch limit
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_panel = {executor.submit(process_single_panel, p): p for p in panel_files}
                
                for future in as_completed(future_to_panel):
                    p_name, t_path, conf, success = future.result()
                    
                    ocr_meta[p_name] = {
                        'transcript': t_path,
                        'avg_confidence': conf
                    }
                    
                    if success:
                        success_count += 1
                        text_files.append(Path(t_path))
                        # self.logger.debug(f"OCR finished: {p_name}") # Reduce log noise
            
            # Sort output by filename to maintain order in list
            text_files.sort(key=lambda x: self._natural_sort_key(x.name))
            
            # Save OCR meta JSON
            try:
                self.dirs['script'].mkdir(parents=True, exist_ok=True)
                meta_path = self.dirs['script'] / 'ocr_meta.json'
                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump(ocr_meta, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.warning(f"Failed to write OCR meta: {e}")
            
            self.stats['ocr_processed'] = success_count
            self.logger.info(f"Parallel OCR completed: {success_count}/{len(panel_files)} panels processed")
            return text_files
            
        except Exception as e:
            self.logger.error(f"Parallel OCR processing failed: {e}")
            self.stats['errors'] += 1
            return []
            
        except Exception as e:
            self.logger.error(f"Original OCR processing failed: {e}")
            self.stats['errors'] += 1
            return []
    
    def _extract_text_from_panel(self, panel_path, ocr_lang, confidence_threshold):
        """Extract text using multiple OCR engines"""
        try:
            # Load and preprocess image
            img = cv2.imread(str(panel_path))
            if img is None:
                return ""
            
            # Preprocess for better OCR
            processed_img = self._preprocess_for_ocr(img)
            
            texts = []
            
            # Try Tesseract OCR
            if self.tesseract_available:
                try:
                    tesseract_text = self._extract_with_tesseract(processed_img, ocr_lang, confidence_threshold)
                    if tesseract_text.strip():
                        texts.append(('tesseract', tesseract_text))
                except Exception as e:
                    self.logger.debug(f"Tesseract OCR failed: {e}")
            
            # Try EasyOCR if available
            if self.easyocr_reader:
                try:
                    easyocr_text = self._extract_with_easyocr(processed_img)
                    if easyocr_text.strip():
                        texts.append(('easyocr', easyocr_text))
                except Exception as e:
                    self.logger.debug(f"EasyOCR failed: {e}")
            
            # Combine results
            if not texts:
                return ""
            elif len(texts) == 1:
                return texts[0][1]
            else:
                # If multiple OCR results, choose the longer one or combine
                return self._combine_ocr_results(texts)
        
        except Exception as e:
            self.logger.error(f"Text extraction failed for {panel_path}: {e}")
            return ""
    
    def _preprocess_for_ocr(self, img):
        """Enhanced image preprocessing for better OCR"""
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Denoise
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            
            # Enhance contrast using CLAHE
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
            # Sharpen the image
            kernel = np.array([[-1, -1, -1],
                             [-1,  9, -1],
                             [-1, -1, -1]])
            gray = cv2.filter2D(gray, -1, kernel)
            
            # Threshold to get clear text
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Morphological operations to clean up text
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            return binary
            
        except Exception as e:
            self.logger.warning(f"OCR preprocessing failed: {e}")
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    def _extract_with_tesseract(self, img, ocr_lang, confidence_threshold):
        """Extract text using Tesseract with confidence filtering"""
        try:
            # Configure Tesseract
            config = f'--psm 6 --oem 3 -l {ocr_lang}'
            
            # Get detailed data with confidence scores
            data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
            
            # Filter by confidence and reconstruct text
            words = []
            for i, conf in enumerate(data['conf']):
                if int(conf) > confidence_threshold:
                    text = data['text'][i].strip()
                    if text:
                        words.append(text)
            
            return ' '.join(words)
            
        except Exception as e:
            self.logger.debug(f"Tesseract extraction failed: {e}")
            return ""
    
    def _extract_with_easyocr(self, img):
        """Extract text using EasyOCR"""
        try:
            results = self.easyocr_reader.readtext(img)
            
            # Extract text with confidence filtering
            texts = []
            for (bbox, text, confidence) in results:
                if confidence > 0.5:  # EasyOCR confidence threshold
                    texts.append(text)
            
            return ' '.join(texts)
            
        except Exception as e:
            self.logger.debug(f"EasyOCR extraction failed: {e}")
            return ""
    
    def _combine_ocr_results(self, texts):
        """Intelligently combine multiple OCR results"""
        try:
            # For now, just return the longest text
            # Could be enhanced with text similarity comparison
            longest_text = max(texts, key=lambda x: len(x[1]))[1]
            return longest_text
            
        except:
            return texts[0][1] if texts else ""
    
    def generate_script_enhanced(self, add_emotions=False):
        """Enhanced script generation with emotion analysis and better error handling"""
        self.logger.info("Starting enhanced script generation")
        
        try:
            # Ensure script directory exists
            self.dirs['script'].mkdir(parents=True, exist_ok=True)
            
            # Get text files
            text_files = list(self.dirs['transcripts'].glob('*.txt'))
            if not text_files:
                self.logger.error(f"No text files found in {self.dirs['transcripts']}")
                
                # Create empty script with explanation
                script_path = self.dirs['script'] / 'chapter.txt'
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write("No script generated - no text files found in transcripts directory.\n")
                    f.write(f"Checked directory: {self.dirs['transcripts']}\n")
                    f.write("Make sure OCR processing completed successfully.")
                return script_path
            
            text_files.sort(key=lambda x: self._natural_sort_key(x.name))
            self.logger.info(f"Generating script from {len(text_files)} text files")
            
            # Process each text file
            script_lines = []
            processed_count = 0
            total_characters = 0
            
            for text_path in text_files:
                try:
                    with open(text_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        
                    if content:
                        # Add panel identifier
                        panel_name = text_path.stem
                        script_lines.append(f"[Panel {panel_name}]")
                        
                        # Process content line by line for better formatting
                        content_lines = content.split('\n')
                        for line in content_lines:
                            line = line.strip()
                            if line:
                                # Add emotion tags if requested
                                if add_emotions:
                                    line = self._add_emotion_tags(line)
                                
                                script_lines.append(line)
                                total_characters += len(line)
                        
                        script_lines.append("")  # Empty line for panel separation
                        processed_count += 1
                        
                    else:
                        # Empty text content - Try Scene Analysis if available
                        # This aligns with user request: "every cut scene have lines"
                        if LEARNER_AVAILABLE:
                            try:
                                # Find corresponding panel image
                                # text_path is .../03_text/transcripts/panel_001.txt
                                # panel needs to be .../02_panels/panel_001.png
                                panel_filename = text_path.stem + '.png'
                                panel_path = self.dirs['panels'] / panel_filename
                                
                                if panel_path.exists():
                                    scene_tags = SceneAnalyzer.analyze(panel_path)
                                    if scene_tags:
                                        # Write visual description
                                        script_lines.append(f"[Panel {text_path.stem}]")
                                        visual_desc = ", ".join(scene_tags)
                                        script_lines.append(f"[Visual: {visual_desc}]")
                                        script_lines.append("")
                                        processed_count += 1
                                        self.logger.info(f"Added visual description for silent panel: {panel_filename}")
                                    else:
                                        self.logger.debug(f"Empty content and no visual tags for {text_path.name}")
                            except Exception as e:
                                self.logger.debug(f"Scene analysis fallback failed: {e}")
                        else:
                            self.logger.debug(f"Empty content in {text_path.name}")
                        
                except Exception as e:
                    self.logger.error(f"Error reading {text_path}: {e}")
                    # Add error placeholder but continue processing
                    script_lines.append(f"[Panel {text_path.stem} - Error reading file]")
                    script_lines.append(f"Error: {str(e)}")
                    script_lines.append("")
                    continue
            
            if not script_lines or processed_count == 0:
                self.logger.warning("No readable content found in any text files")
                script_path = self.dirs['script'] / 'chapter.txt'
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write("No script generated - all text files were empty or unreadable.\n")
                    f.write(f"Processed {len(text_files)} files, but found no content.")
                return script_path
            
            # Generate script statistics
            stats_lines = [
                f"# Script Statistics",
                f"# Generated from {processed_count} panels",
                f"# Total characters: {total_characters}",
                f"# Emotion tags: {'Enabled' if add_emotions else 'Disabled'}",
                f"# Generated at: {self._get_timestamp()}",
                "",
                "# " + "="*50,
                "# CHAPTER SCRIPT",
                "# " + "="*50,
                ""
            ]
            
            # Combine statistics and script content
            final_script_lines = stats_lines + script_lines
            script_content = "\n".join(final_script_lines).strip()
            
            # Save script
            script_path = self.dirs['script'] / 'chapter.txt'
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # Save a secondary 'clean' script without any metadata/tags
            clean_lines = []
            for line in script_lines:
                if not line.startswith('[Panel') and not line.startswith('[Visual:'):
                    if line.strip():
                        clean_lines.append(line.strip())
            
            if clean_lines:
                clean_script_path = self.dirs['script'] / 'clean_chapter.txt'
                with open(clean_script_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(clean_lines))
                self.logger.info(f"Clean script saved to: {clean_script_path}")

            self.logger.info(f"Script generated successfully: {processed_count} panels, {total_characters} characters")
            self.logger.info(f"Script saved to: {script_path}")
            return script_path
            
        except Exception as e:
            self.logger.error(f"Script generation failed: {e}")
            self.stats['errors'] += 1
            
            # Create error script as fallback
            try:
                script_path = self.dirs['script'] / 'chapter.txt'
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(f"Script generation failed with error: {str(e)}\n")
                    f.write("Please check the logs for more details.")
                return script_path
            except:
                return None
    
    def _get_timestamp(self):
        """Get current timestamp for script metadata"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def _add_emotion_tags(self, text):
        """Add emotion tags to text with improved fallback detection"""
        if not text or not text.strip():
            return text
            
        try:
            # Use text2emotion if available
            if EMOTION_AVAILABLE and 'te' in globals() and te:
                try:
                    emotions = te.get_emotion(text)
                    if emotions and isinstance(emotions, dict):
                        # Find dominant emotion
                        dominant_emotion = max(emotions, key=emotions.get)
                        if emotions[dominant_emotion] > 0.3:  # Threshold for emotion
                            return f"[{dominant_emotion}] {text}"
                except Exception as e:
                    self.logger.debug(f"text2emotion failed: {e}")
            
            # Enhanced rule-based emotion detection
            text_lower = text.lower().strip()
            
            # Excitement/shouting (check for caps and exclamations first)
            if text.isupper() or '!!' in text:
                if any(word in text_lower for word in ['no', 'stop', 'help', 'wait']):
                    return f"[shouting] {text}"
                else:
                    return f"[excited] {text}"
            elif '!' in text:
                if any(word in text_lower for word in ['wow', 'amazing', 'great', 'awesome', 'yes']):
                    return f"[excited] {text}"
                elif any(word in text_lower for word in ['no', 'damn', 'hell']):
                    return f"[angry] {text}"
                else:
                    return f"[emphatic] {text}"
            
            # Questions and confusion
            elif '?' in text:
                if any(word in text_lower for word in ['what', 'how', 'why', 'when', 'where']):
                    return f"[questioning] {text}"
                else:
                    return f"[confused] {text}"
            
            # Hesitation and thinking
            elif '...' in text or text_lower.endswith('.'):
                if any(word in text_lower for word in ['hmm', 'uh', 'um', 'well']):
                    return f"[thoughtful] {text}"
                elif any(word in text_lower for word in ['sigh', 'oh']):
                    return f"[resigned] {text}"
                else:
                    return f"[trailing] {text}"
            
            # Happiness indicators
            elif any(word in text_lower for word in ['haha', 'hehe', 'lol', 'laugh', 'smile', 'happy']):
                return f"[happy] {text}"
            
            # Sadness indicators
            elif any(word in text_lower for word in ['sob', 'cry', 'sad', 'tears', 'weep']):
                return f"[sad] {text}"
            
            # Surprise indicators
            elif any(word in text_lower for word in ['whoa', 'oh my', 'incredible', 'unbelievable']):
                return f"[surprised] {text}"
            
            # Agreement/positive
            elif any(word in text_lower for word in ['yes', 'okay', 'sure', 'alright', 'good']):
                return f"[agreeing] {text}"
            
            # Disagreement/negative
            elif any(word in text_lower for word in ['no', 'nope', 'never', 'stop']):
                return f"[disagreeing] {text}"
            
            # Default: no emotion tag
            return text
            
        except Exception as e:
            self.logger.warning(f"Emotion tagging failed: {e}")
            return text
    
    def generate_ai_enhanced_script(self, chapter_title="", series_context="", 
                                   character_info=None, style_preferences=None,
                                   gemini_api_key=None):
        """Generate AI-enhanced script using Gemini API"""
        self.logger.info("Starting AI-enhanced script generation")
        
        if not AI_SCRIPT_AVAILABLE:
            self.logger.warning("AI script generation not available - falling back to standard script generation")
            return self.generate_script_enhanced(add_emotions=True)
        
        try:
            # Ensure script directory exists
            self.dirs['script'].mkdir(parents=True, exist_ok=True)
            
            # Get text files
            text_files = list(self.dirs['transcripts'].glob('*.txt'))
            if not text_files:
                self.logger.error(f"No text files found in {self.dirs['transcripts']}")
                return self.generate_script_enhanced(add_emotions=True)
            
            # Initialize AI script generator
            ai_generator = AIScriptGenerator(
                api_key=gemini_api_key,
                logger=self.logger
            )
            
            if not ai_generator.is_available():
                self.logger.warning("AI script generator not available - using fallback")
                return self.generate_script_enhanced(add_emotions=True)
            
            # Generate AI-enhanced script
            enhanced_script, metadata = ai_generator.generate_enhanced_script(
                transcript_files=text_files,
                chapter_title=chapter_title,
                series_context=series_context,
                character_info=character_info or {},
                style_preferences=style_preferences or {'emotion_detail': 'medium', 'scene_descriptions': True}
            )
            
            # Save the enhanced script
            script_path = self.dirs['script'] / 'chapter.txt'
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(enhanced_script)
            
            # Save a clean version if possible (tries to strip tags)
            clean_lines = []
            for line in enhanced_script.split('\n'):
                if not line.startswith('[Panel') and not line.startswith('[Visual:'):
                    if line.strip():
                        clean_lines.append(line.strip())
            
            if clean_lines:
                clean_script_path = self.dirs['script'] / 'clean_chapter.txt'
                with open(clean_script_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(clean_lines))
                self.logger.info(f"Clean AI script saved to: {clean_script_path}")
            
            # Save metadata
            metadata_path = self.dirs['script'] / 'ai_metadata.json'
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            self.logger.info(f"AI-enhanced script generated successfully")
            self.logger.info(f"Model used: {metadata['model_used']}")
            self.logger.info(f"Generation time: {metadata['generation_time']:.2f}s")
            self.logger.info(f"Script saved to: {script_path}")
            
            # Update stats
            self.stats['ai_enhanced'] = True
            self.stats['ai_generation_time'] = metadata['generation_time']
            
            return script_path
            
        except Exception as e:
            self.logger.error(f"AI script generation failed: {e}")
            self.logger.info("Falling back to standard script generation")
            return self.generate_script_enhanced(add_emotions=True)
    
    def get_processing_stats(self):
        """Get comprehensive processing statistics"""
        return {
            **self.stats,
            'success_rate': ((self.stats.get('valid_panels', 0) / 
                            max(self.stats.get('extracted_panels', 1), 1)) * 100) if self.stats.get('extracted_panels') else 0,
            'ocr_success_rate': ((self.stats.get('ocr_processed', 0) / 
                                max(self.stats.get('valid_panels', 1), 1)) * 100) if self.stats.get('valid_panels') else 0
        }

def main():
    """Main function for command line usage"""
    parser = argparse.ArgumentParser(description='Enhanced Manga Factory')
    
    parser.add_argument('--url', help='Manga/webtoon URL to download')
    parser.add_argument('--webtoon-url', help='Webtoon URL (alias for --url)')
    parser.add_argument('--chapter-dir', required=True, help='Chapter directory path')
    parser.add_argument('--mode', default='manga', choices=['manga', 'webtoon'],
                        help='Download mode: manga (page-by-page) or webtoon (long strip)')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--ocr-lang', default='eng', help='OCR language (eng, jpn, kor)')
    parser.add_argument('--emotion', action='store_true', help='Add emotion tags to script')
    parser.add_argument('--ai-script', action='store_true', help='Use AI-enhanced script generation with Gemini API')
    parser.add_argument('--gemini-api-key', help='Gemini API key for AI script generation')
    parser.add_argument('--series-context', help='Series context for AI script generation')
    parser.add_argument('--chapter-title', help='Chapter title for AI script generation')
    parser.add_argument('--skip-download', action='store_true', help='Skip download step')
    parser.add_argument('--skip-clean', action='store_true', help='Skip cleaning step')
    parser.add_argument('--skip-stitch', action='store_true', help='Skip stitching step')
    parser.add_argument('--skip-slice', action='store_true', help='Skip panel extraction')
    parser.add_argument('--skip-ocr', action='store_true', help='Skip OCR step')
    parser.add_argument('--force-format', choices=['manga', 'webtoon'], help='Force format detection')
    parser.add_argument('--stitch-extract-panels', action='store_true', help='Extract individual panels from stitched strips')
    
    # Enhanced OCR options
    parser.add_argument('--ocr-mode', default='medium', choices=['light', 'medium', 'aggressive'],
                        help='OCR preprocessing mode (default: medium)')
    parser.add_argument('--ocr-confidence', type=int, default=60,
                        help='OCR confidence threshold 0-100 (default: 60)')
    parser.add_argument('--save-preprocessed', action='store_true',
                        help='Save preprocessed panel images for debugging')

    # Character Learning & Scene Analysis
    parser.add_argument('--learn-characters', action='store_true',
                        help='Enable character face learning and extraction')
    parser.add_argument('--analyze-scenes', action='store_true',
                        help='Enable scene type analysis (Day/Night/Action)')
    
    # License management commands
    parser.add_argument('--license', help='Install license key')
    parser.add_argument('--license-info', action='store_true', help='Show license information')
    parser.add_argument('--generate-demo-license', action='store_true', help='Generate demo license for testing')

    # Minimal CLI: use safe defaults; advanced chunking/validation options removed
    args = parser.parse_args()
    
    # Handle license commands first (before factory initialization)
    if args.license:
        if license_validator.save_license(args.license):
            print(f"✅ License key saved successfully to: {license_validator.license_file}")
            # Validate the new license
            is_valid, message = license_validator.validate_license()
            if is_valid:
                print(f"✅ License validated: {message}")
            else:
                print(f"❌ Invalid license: {message}")
                return 1
        else:
            print(f"❌ Failed to save license key")
            return 1
        return 0
    
    if args.license_info:
        print(f"🔐 MANGA FACTORY PRO - LICENSE INFORMATION")
        print(f"Machine ID: {license_validator.machine_id}")
        print(f"License file: {license_validator.license_file}")
        
        if license_validator.license_file.exists():
            is_valid, message = license_validator.validate_license()
            if is_valid:
                print(f"✅ License Status: {message}")
            else:
                print(f"❌ License Status: {message}")
        else:
            print(f"❌ No license file found")
        return 0
    
    if args.generate_demo_license:
        demo_license = license_validator.generate_license_for_machine()
        print(f"🧪 DEMO LICENSE FOR TESTING:")
        print(f"License Key: {demo_license}")
        print(f"Machine ID: {license_validator.machine_id}")
        print(f"\n💾 To install:")
        print(f"python3 manga_factory_enhanced.py --license {demo_license}")
        return 0
    
    # Use webtoon-url if provided
    url = args.webtoon_url or args.url
    
    try:
        # Initialize factory
        factory = EnhancedMangaFactory(args.chapter_dir, args.config, mode=args.mode)
        
        # Download step
        if not args.skip_download and url:
            logger.info("=== DOWNLOAD PHASE ===")
            # Periodic license check
            factory._validate_license()
            if not factory.download_chapter(url):
                logger.error("Download failed, stopping process")
                return 1
        
        # Clean step
        if not args.skip_clean:
            logger.info("=== CLEANING PHASE ===")
            cleaned_files = factory.clean_pages_enhanced()
            if not cleaned_files:
                logger.error("Cleaning failed, stopping process")
                return 1
        
        # Stitching step
        if not args.skip_stitch:
            logger.info("=== STITCHING PHASE ===")
            stitch_result = factory.process_stitching_enhanced(
                args.force_format,
                extract_single_panels=args.stitch_extract_panels
            )
            # Stitching failure is not fatal - we can continue with individual images
        
        # Panel extraction step
        if not args.skip_slice:
            logger.info("=== PANEL EXTRACTION PHASE ===")
            panels = factory.extract_panels_enhanced(skip_validation=False)
            if not panels:
                logger.error("Panel extraction failed, stopping process")
                return 1
        
        # OCR step
        if not args.skip_ocr:
            logger.info("=== OCR PHASE ===")
            # Periodic license check
            factory._validate_license()
            # Periodic license check
            factory._validate_license()
            text_files = factory.process_ocr_enhanced(
                ocr_lang=args.ocr_lang,
                confidence_threshold=args.ocr_confidence,
                preprocessing_mode=args.ocr_mode,
                save_preprocessed=args.save_preprocessed
            )
            if not text_files:
                logger.warning("No text extracted from panels")
        
        # Character Learning Phase
        if args.learn_characters and LEARNER_AVAILABLE:
            logger.info("=== CHARACTER LEARNING PHASE ===")
            try:
                learner = CharacterLearner(output_dir=factory.chapter_dir, manga_name=factory.series_name or "unknown")
                # We need access to valid panels. 
                # Assuming factory.dirs['panels'] contains the valid ones.
                valid_panels = list(factory.dirs['panels'].glob('*.png'))
                total_faces = 0
                for p in valid_panels:
                    total_faces += learner.learn_from_panel(p, p.stem)
                logger.info(f"Learned {total_faces} faces from {len(valid_panels)} panels")
                
                # Run Clustering
                learner.cluster_characters()
                
            except Exception as e:
                logger.error(f"Character learning failed: {e}")
        elif args.learn_characters:
            logger.warning("Character learning module not available (cv2 missing?)")

        # Scene Analysis Phase (append to metadata)
        # Scene Analysis Phase (append to metadata)
        if args.analyze_scenes and LEARNER_AVAILABLE:
            logger.info("=== SCENE ANALYSIS PHASE ===")
            try:
                scene_meta = {}
                valid_panels = list(factory.dirs['panels'].glob('*.png'))
                valid_panels.sort(key=lambda x: factory._natural_sort_key(x.name))
                
                logger.info(f"Analyzing scenes for {len(valid_panels)} panels...")
                
                for p in valid_panels:
                    tags = SceneAnalyzer.analyze(p)
                    if tags:
                        scene_meta[p.name] = tags
                        
                # Save scene metadata
                factory.dirs['script'].mkdir(parents=True, exist_ok=True)
                scene_json_path = factory.dirs['script'] / 'scene_analysis.json'
                with open(scene_json_path, 'w', encoding='utf-8') as f:
                    json.dump(scene_meta, f, indent=2)
                    
                logger.info(f"Scene analysis completed. Metadata saved to {scene_json_path.name}")
                
            except Exception as e:
                logger.error(f"Scene analysis failed: {e}") 
        
        # Script generation
        logger.info("=== SCRIPT GENERATION PHASE ===")
        # Always enable emotion analysis if requested
        if args.ai_script:
            # Use AI-enhanced script generation
            script_path = factory.generate_ai_enhanced_script(
                chapter_title=args.chapter_title or "",
                series_context=args.series_context or "",
                gemini_api_key=args.gemini_api_key
            )
        else:
            # Use standard script generation
            script_path = factory.generate_script_enhanced(add_emotions=args.emotion)
        
        # Final statistics
        stats = factory.get_processing_stats()
        logger.info("=== PROCESSING COMPLETE ===")
        logger.info("Final Statistics:")
        for key, value in stats.items():
            if isinstance(value, float):
                logger.info(f"  {key}: {value:.1f}%")
            else:
                logger.info(f"  {key}: {value}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return 1

# License generation utility for commercial use
def generate_license_for_customer(machine_id, valid_days=365):
    """Generate a license key for a customer's machine ID"""
    machine_part = machine_id[:8]
    timestamp = int(datetime.now().timestamp())
    date_part = f"{timestamp:08x}"
    
    payload = f"{machine_part}{date_part}manga_factory_pro"
    signature = hashlib.md5(payload.encode()).hexdigest()[:16]
    
    license_key = f"{machine_part}{date_part}{signature}"
    
    # Validate the generated license
    temp_validator = LicenseValidator()
    temp_validator.machine_id = machine_id
    is_valid, message = temp_validator.validate_license(license_key)
    
    return {
        'license_key': license_key,
        'machine_id': machine_id,
        'valid': is_valid,
        'message': message,
        'expires': datetime.fromtimestamp(timestamp) + timedelta(days=valid_days)
    }

if __name__ == "__main__":
    sys.exit(main())
