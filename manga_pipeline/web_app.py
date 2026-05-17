#!/usr/bin/env python3

"""
Simple Web Interface for Manga Factory Pipeline
Uses built-in Python HTTP server and existing manga_factory.py
"""

import os
import sys
import json
import urllib.parse
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import time
import re
import webbrowser
import mimetypes
import requests
from bs4 import BeautifulSoup

# Add current and repo root to path for imports
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import enhanced pipeline
from manga_factory_enhanced import EnhancedMangaFactory

# License manager disabled for open source version
LICENSE_MANAGER = None

# Import AI script generator (optional)
try:
    from ai_script_generator import AIScriptGenerator
    AI_SCRIPT_AVAILABLE = True
except ImportError:
    AI_SCRIPT_AVAILABLE = False

# AI environment status (do NOT read or print secrets)
AI_ENV_KEY_PRESENT = bool(os.environ.get('GEMINI_API_KEY'))

# Import PDF generator
try:
    import pdf_generator
    PDF_GENERATOR_AVAILABLE = True
except ImportError:
    PDF_GENERATOR_AVAILABLE = False
    print("Warning: pdf_generator module not found.")

# Global processing status
processing_status = {
    'is_processing': False,
    'current_step': 'Ready',
    'progress': 0,
    'logs': [],
    'current_chapter': '',
    'current_chapter_name': ''
}

# Import ML Orchestrator
try:
    from ml_orchestrator import create_ml_orchestrator
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("Warning: ml_orchestrator module not found.")

# Use a user-accessible base directory for outputs
OUTPUT_BASE = Path.home() / 'MangaFactory'
OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

def add_log(message, level='info'):
    """Add a log message to the processing status"""
    from datetime import datetime
    timestamp = datetime.now().strftime('%H:%M:%S')
    processing_status['logs'].append({
        'timestamp': timestamp,
        'message': str(message),
        'level': level
    })
    # Keep only last 100 logs
    if len(processing_status['logs']) > 100:
        processing_status['logs'] = processing_status['logs'][-100:]
    print(f"[{timestamp}] {level.upper()}: {message}")

def resolve_episode_url(series_name: str, chapter_number: int):
    """Resolve a Webtoons episode URL from series name and episode/chapter number.
    Strategy: use Webtoons search page to find the series list (title_no), then
    open the list page and pick the episode link with matching episode_no.
    Returns a full viewer URL or None.
    """
    try:
        if not series_name or not chapter_number:
            return None
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        # 1) Search the series
        q = urllib.parse.quote(series_name)
        search_url = f"https://www.webtoons.com/en/search?keyword={q}"
        r = requests.get(search_url, headers=headers, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        # Find first series list link (…/list?title_no=XXXX)
        list_link = None
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/list?title_no=' in href:
                list_link = href if href.startswith('http') else urllib.parse.urljoin('https://www.webtoons.com', href)
                break
        if not list_link:
            return None
        # 2) Open series list and find the episode link
        r2 = requests.get(list_link, headers=headers, timeout=20)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, 'html.parser')
        needle = f"episode_no={int(chapter_number)}"
        for a in soup2.find_all('a', href=True):
            href = a['href']
            if 'viewer' in href and 'episode_no=' in href and needle in href:
                return href if href.startswith('http') else urllib.parse.urljoin('https://www.webtoons.com', href)
        return None
    except Exception:
        return None


def run_manga_pipeline(url, chapter_name, options):
    """Run the complete manga processing pipeline"""
    try:
        processing_status['is_processing'] = True
        processing_status['current_chapter'] = chapter_name
        processing_status['current_chapter_name'] = os.path.basename(str(chapter_name))
        processing_status['progress'] = 0
        processing_status['logs'] = []
        
        add_log("Starting processing for: " + chapter_name)
        # Log AI mode intent (without exposing secrets)
        if options.get('ai_script', False):
            ai_mode = "ON"
        else:
            ai_mode = "OFF"
        add_log(f"AI Mode: {ai_mode}")
        if AI_SCRIPT_AVAILABLE:
            add_log(f"AI Backend: installed")
        else:
            add_log(f"AI Backend: not installed")
        if options.get('ai_script', False):
            if os.environ.get('GEMINI_API_KEY') or options.get('gemini_api_key'):
                add_log("AI Key: provided (hidden)")
            else:
                add_log("AI Key: not provided (will fallback)")
        
        # Initialize enhanced pipeline
        factory = EnhancedMangaFactory(chapter_name)
        
        # Step 1: Download
        processing_status['current_step'] = 'Downloading'
        processing_status['progress'] = 20
        add_log("Starting download (enhanced)...")
        
        try:
            ok = factory.download_chapter(url)
            if not ok:
                add_log("Download failed", 'error')
                processing_status['current_step'] = 'Failed'
                return
            add_log("Downloaded images to 00_raw/")
        except Exception as e:
            add_log(f"Download error: {str(e)}", 'error')
            processing_status['current_step'] = 'Failed'
            return
        
        # Step 2: Clean
        processing_status['current_step'] = 'Cleaning'
        processing_status['progress'] = 40
        add_log("Cleaning images...")
        
        try:
            cleaned = factory.clean_pages_enhanced()
            add_log(f"Images cleaned: {len(cleaned)}")
        except Exception as e:
            add_log(f"Cleaning error: {str(e)}", 'error')
        
        # Step 3: Stitch (defaults)
        processing_status['current_step'] = 'Stitching'
        processing_status['progress'] = 52
        add_log("Stitching...")
        try:
            factory.process_stitching_enhanced()
            add_log("Stitching complete")
        except Exception as e:
            add_log(f"Stitching error: {str(e)}", 'error')
        
        # Step 4: Extract panels
        processing_status['current_step'] = 'Extracting Panels'
        processing_status['progress'] = 60
        add_log("Extracting panels (enhanced with validation)...")
        try:
            panels = factory.extract_panels_enhanced(use_stitched=True)
            add_log(f"Panels extracted: {len(panels)}")
        except Exception as e:
            add_log(f"Panel extraction error: {str(e)}", 'error')
        
        # Step 5: Validate panels
        processing_status['current_step'] = 'Validating Panels'
        processing_status['progress'] = 70
        add_log("Validating panels (remove thumbnails/cuts/dupes)...")
        try:
            valid_count = factory.validate_panels_enhanced()
            add_log(f"Valid panels: {valid_count}")
        except Exception as e:
            add_log(f"Validation error: {str(e)}", 'error')
        
        # Step 6: OCR
        processing_status['current_step'] = 'Processing Text (OCR)'
        processing_status['progress'] = 82
        add_log("Running OCR on panels...")
        
        try:
            factory.process_ocr_enhanced(options.get('ocr_lang', 'eng'))
            add_log("OCR completed successfully")
        except Exception as e:
            add_log(f"OCR error: {str(e)}", 'error')
        
        # Step 7: Generate script
        processing_status['current_step'] = 'Generating Script'
        processing_status['progress'] = 90
        
        try:
            if options.get('ai_script', False) and AI_SCRIPT_AVAILABLE:
                add_log("Generating AI-enhanced script with Gemini API...")
                
                # Use AI-enhanced script generation
                script_path = factory.generate_ai_enhanced_script(
                    chapter_title=options.get('chapter_title', ''),
                    series_context=options.get('series_context', ''),
                    gemini_api_key=options.get('gemini_api_key')
                )
                add_log("AI-enhanced script generated successfully with advanced features!")
            else:
                add_log("Generating standard script with emotion analysis...")
                factory.generate_script_enhanced(True)  # Enable emotion tags by default
                add_log("Script generated successfully with emotion analysis")
        except Exception as e:
            add_log(f"Script generation error: {str(e)}", 'error')

        # Step 8: PDF Generation (New Feature)
        if options.get('generate_pdf', False) and PDF_GENERATOR_AVAILABLE:
            processing_status['current_step'] = 'Generating PDF'
            processing_status['progress'] = 95
            add_log("Generating PDF...")
            
            try:
                # We need the chapter directory. 
                # factory.chapter_dir should provide the absolute path to the processed chapter
                chapter_dir = factory.chapter_dir
                
                # Verify stitched strip exists before trying
                stitched_path = os.path.join(chapter_dir, "02_stitched", "complete_manga_strip.png")
                if os.path.exists(stitched_path):
                    pdf_path = pdf_generator.generate_chapter_pdf(chapter_dir)
                    if pdf_path:
                        add_log(f"PDF Generated: {os.path.basename(pdf_path)}")
                    else:
                        add_log("PDF Generation failed (check logs)", 'error')
                else:
                     add_log("Skipping PDF: Stitched strip not found", 'warning')
            except Exception as e:
                add_log(f"PDF error: {str(e)}", 'error')

        # Step 9: ML Processing (New Feature)
        if options.get('run_ml', False) and ML_AVAILABLE:
            processing_status['current_step'] = 'ML Processing'
            processing_status['progress'] = 98
            add_log("Starting ML Processing (Active Learning)...")
            try:
                # Initialize orchestrator with repo root
                repo_root = Path(os.path.dirname(os.path.dirname(__file__)))
                orchestrator = create_ml_orchestrator(repo_root)
                
                # Use the chapter directory from the factory
                if factory.chapter_dir:
                    # We need to determine the manga series name slightly better if possible
                    # But factory.series_name should be available if we modify EnhancedMangaFactory to expose it
                    # Or just infer it from path
                    series_name = os.path.basename(os.path.dirname(factory.chapter_dir))
                    
                    ml_result = orchestrator.process_chapter(Path(factory.chapter_dir), manga_name=series_name)
                    if ml_result.get('success'):
                        q_score = ml_result.get('quality_score', 0)
                        add_log(f"ML Complete. Quality Score: {q_score:.2f}")
                        if q_score < 0.8:
                            add_log("Quality Warning: Low confidence score.", 'warning')
                    else:
                         add_log(f"ML Process failed: {ml_result.get('error')}", 'error')
                else:
                    add_log("Skipping ML: Chapter directory not found", 'error')
            except Exception as e:
                add_log(f"ML Orchestration Error: {str(e)}", 'error')

        
        # Complete
        processing_status['current_step'] = 'Complete'
        processing_status['progress'] = 100
        add_log("Processing completed successfully!", 'success')
        
    except Exception as e:
        add_log(f"Pipeline error: {str(e)}", 'error')
        processing_status['current_step'] = 'Failed'
    
    finally:
        processing_status['is_processing'] = False

def _license_status():
    # Open source version - always valid
    return {'valid': True, 'reason': 'Open source version', 'days_remaining': 9999, 'expiry': None}


def _license_valid():
    # Open source version - always valid
    return True


class MangaFactoryHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Manga Factory web interface"""
    
    def do_GET(self):
        """Handle GET requests"""
        # License gating (allow license endpoints even if invalid)
        license_paths = ['/license', '/license/', '/license/status']
        if not _license_valid() and not any(self.path.startswith(p) for p in license_paths):
            return self.serve_license_html()

        if self.path == '/' or self.path == '/index.html':
            self.serve_html()
        elif self.path.startswith('/status'):
            self.serve_json(processing_status)
        elif self.path.startswith('/ai-status'):
            # Report AI availability and env key presence (no secrets)
            self.serve_json({
                'available': AI_SCRIPT_AVAILABLE,
                'env_key': AI_ENV_KEY_PRESENT,
                'model': 'gemini-1.5-flash'
            })
        elif self.path.startswith('/chapters'):
            self.serve_chapters()
        elif self.path.startswith('/chapter'):
            self.serve_chapter_detail()
        elif self.path.startswith('/file'):
            self.serve_file()
        elif self.path.startswith('/license/status'):
            self.serve_json(_license_status())
        elif self.path.startswith('/license'):
            self.serve_license_html()
        else:
            self.send_error(404, "File not found")
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/license/activate':
            return self.handle_license_activate()
        # License gate for other actions
        if not _license_valid():
            self.send_response(403)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'License required'}).encode('utf-8'))
            return
        if self.path == '/process':
            # If in grace, allow UI but block heavy processing
            st = _license_status()
            if st.get('grace'):
                self.send_response(402)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'License expired (grace). Renew to process.'}).encode('utf-8'))
                return
            self.handle_process()
        else:
            self.send_error(404, "Endpoint not found")
    
    def serve_html(self):
        """Serve the Clean Pixelated HTML page"""
        st = _license_status()
        banner = ''
        if st.get('revoked'):
            banner = '<div class="notice notice-warn">❌ License revoked.</div>'
        elif st.get('grace'):
            banner = f'<div class="notice notice-warn">⚠️ License expired. Grace: {st.get("grace_days_remaining", 0)} days.</div>'
            
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manga Factory PIXEL</title>
    <link href="https://fonts.googleapis.com/css2?family=VT323&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #fcfcfc;
            --primary-blue: #0033cc;
            --text-color: #000;
            --beche: #fffbe6;
            --border: 3px solid #0033cc;
            --accent-red: #ff3b30;
            --accent-yellow: #ffcc00;
            --accent-green: #34c759;
            --shadow: 5px 5px 0px rgba(0, 51, 204, 0.2);
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'VT323', monospace;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 40px 20px;
            font-size: 24px;
            /* Grid pattern background */
            background-image: 
                linear-gradient(var(--primary-blue) 1px, transparent 1px),
                linear-gradient(90deg, var(--primary-blue) 1px, transparent 1px);
            background-size: 40px 40px;
            background-position: -1px -1px;
            /* Make grid subtle */
            background-color: #fdfdfd; 
            backdrop-filter: opacity(10%);
        }
        
        /* Main Application Window */
        .window-container {
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
            border: var(--border);
            box-shadow: 10px 10px 0px #000;
            position: relative;
        }

        /* Window Title Bar */
        .window-header {
            background: #fff;
            border-bottom: var(--border);
            padding: 10px 15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .window-controls {
            display: flex;
            gap: 8px;
        }
        .dot {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid #000;
        }
        .dot.red { background: var(--accent-red); }
        .dot.yellow { background: var(--accent-yellow); }
        .dot.green { background: var(--accent-green); }

        .window-title {
            font-size: 1.5em;
            font-weight: bold;
            color: var(--primary-blue);
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .content { padding: 40px; }

        /* Typography */
        h1 {
            color: var(--primary-blue);
            text-align: center;
            font-size: 3.5em;
            margin: 0 0 30px 0;
            text-transform: uppercase;
            text-shadow: 3px 3px 0px rgba(0,0,0,0.1);
        }
        
        h2 { 
            color: var(--primary-blue);
            border-bottom: 3px solid var(--primary-blue); 
            display: inline-block;
            margin-top: 40px; 
            margin-bottom: 20px;
            padding-bottom: 5px;
            font-size: 2em;
            text-transform: uppercase;
        }

        /* Forms & Inputs */
        .input-group { margin-bottom: 25px; }
        label { 
            display: block; 
            font-weight: bold; 
            margin-bottom: 8px; 
            font-size: 1.3em;
            color: var(--primary-blue);
        }
        input[type="text"], input[type="password"] { 
            width: 100%; 
            padding: 12px; 
            font-family: 'VT323', monospace; 
            font-size: 1.3em; 
            background: #fff; 
            border: 3px solid #000; 
            color: #000;
            box-shadow: 4px 4px 0px #ccc;
            outline: none;
            transition: 0.1s;
        }
        input:focus { 
            border-color: var(--primary-blue); 
            box-shadow: 4px 4px 0px var(--primary-blue);
        }

        /* Buttons */
        .btn {
            background: var(--primary-blue);
            color: #fff;
            border: 3px solid #000;
            padding: 15px;
            font-family: 'VT323', monospace;
            font-size: 1.5em;
            cursor: pointer;
            box-shadow: 5px 5px 0px #000;
            text-transform: uppercase;
            width: 100%;
            transition: all 0.1s;
        }
        .btn:hover { transform: translate(-2px, -2px); box-shadow: 7px 7px 0px #000; }
        .btn:active { transform: translate(2px, 2px); box-shadow: 3px 3px 0px #000; }
        .btn:disabled { background: #999; cursor: not-allowed; transform: none; box-shadow: none; }
        
        .btn-small { 
            background: #fff;
            color: var(--primary-blue);
            border: 2px solid var(--primary-blue);
            padding: 5px 15px; 
            font-family: 'VT323', monospace;
            font-size: 1em;
            cursor: pointer;
            box-shadow: 3px 3px 0px #ccc;
            text-transform: uppercase; 
        }
        .btn-small:hover { background: var(--primary-blue); color: #fff; box-shadow: 3px 3px 0px #000; }

        /* Checkbox Box - "Traffic Light" Style or Simple Box */
        .checkbox-wrapper {
            background: #f0f0f0;
            border: 3px solid #000;
            padding: 15px;
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
            box-shadow: 5px 5px 0px #ddd;
        }
        input[type="checkbox"] {
            appearance: none;
            width: 28px;
            height: 28px;
            border: 3px solid #000;
            background: #fff;
            cursor: pointer;
            position: relative;
        }
        input[type="checkbox"]:checked {
            background: var(--primary-blue);
        }
        input[type="checkbox"]:checked::after {
            content: '✓';
            color: #fff;
            font-size: 28px;
            position: absolute;
            left: 2px;
            bottom: 0px;
            line-height: 24px;
        }

        /* Status & Logs */
        .status-box {
            border: 3px solid #000;
            background: #fff;
            padding: 20px;
            margin: 30px 0;
            display: none;
            box-shadow: 8px 8px 0px #eee;
        }
        .status-box.active { display: block; }
        
        .progress-bar-container {
            border: 3px solid #000;
            height: 30px;
            background: #fff;
            margin-bottom: 10px;
        }
        .progress-bar {
            height: 100%;
            background: var(--primary-blue);
            width: 0%;
            transition: width 0.3s;
        }
        .logs { 
            height: 200px; 
            overflow-y: auto; 
            font-family: 'Courier New', monospace; 
            font-size: 16px; 
            border: 2px solid #ccc;
            padding: 10px;
            background: #f9f9f9;
            color: #333;
        }
        .log-error { color: red; font-weight: bold; }
        .log-success { color: green; font-weight: bold; }

        /* Library Items */
        .chapter-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #fff;
            border: 2px solid #000;
            padding: 15px;
            margin-bottom: 10px;
            box-shadow: 4px 4px 0px #ddd;
            transition: 0.2s;
        }
        .chapter-item:hover {
            transform: translate(-1px, -1px);
            box-shadow: 6px 6px 0px #ccc;
        }
        .chapter-info h4 { margin: 0; color: var(--primary-blue); font-size: 1.4em; }
        .chapter-info p { margin: 0; color: #666; font-size: 0.9em; }

        .hidden { display: none; }
        .badge { background: var(--primary-blue); color: #fff; padding: 2px 6px; font-size: 0.8em; border-radius: 4px; }
        
        /* Helper for "Likings/Skills" style sections if needed */
        .section-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
    </style>
</head>
<body>
    <div class="window-container">
        <!-- Mac/Window Style Header -->
        <div class="window-header">
            <div class="window-controls">
                <div class="dot red"></div>
                <div class="dot yellow"></div>
                <div class="dot green"></div>
            </div>
            <div class="window-title">MANGA.FACTORY.EXE</div>
            <div style="width: 50px;"></div> <!-- Spacer -->
        </div>

        <div class="content">
            <h1>MANGA FACTORY</h1>
            ''' + banner + '''
            
            <form id="processForm">
                <div class="input-group">
                    <label>📝 URL (WEBTOONS / MANGADX)</label>
                    <input type="text" name="url" placeholder="http://..." required>
                </div>
                
                <div class="input-group">
                    <label>📂 CHAPTER NAME (OPTIONAL)</label>
                    <input type="text" name="chapter_name" placeholder="Auto-detect if empty">
                </div>

                <h2>CONFIGURATIONS</h2>
                <div class="section-grid">
                    <!-- ML Options -->
                    <div class="checkbox-wrapper">
                        <input type="checkbox" name="run_ml" id="run_ml" checked>
                        <div>
                            <label for="run_ml" style="margin:0; cursor:pointer;">ACTIVE LEARNING (ML)</label>
                            <div style="font-size:0.8em; color:#666;">Enhance panels & story</div>
                        </div>
                    </div>

                    <!-- PDF Options -->
                    <div class="checkbox-wrapper">
                        <input type="checkbox" name="generate_pdf" id="generate_pdf" checked>
                        <div>
                            <label for="generate_pdf" style="margin:0; cursor:pointer;">GENERATE PDF</label>
                            <div style="font-size:0.8em; color:#666;">Create printable doc</div>
                        </div>
                    </div>
                </div>

                <div style="text-align: right; margin-bottom: 15px;">
                     <button type="button" class="btn-small" onclick="document.getElementById('adv-options').classList.toggle('hidden')">
                        [+] ADVANCED SETTINGS
                    </button>
                </div>

                <div id="adv-options" class="hidden" style="border: 3px dashed #ccc; padding: 20px; margin-bottom: 20px; background: #fafafa;">
                     <div class="checkbox-wrapper" style="border:none; background:none; padding:0; box-shadow:none;">
                        <input type="checkbox" id="ai_script" name="ai_script">
                        <label for="ai_script" style="margin:0;">ENABLE GEMINI AI SCRIPTING</label>
                    </div>
                    <div id="ai_settings" class="hidden" style="margin-top:10px;">
                        <div class="input-group" style="margin-bottom:0;">
                            <label style="font-size:1em;">API KEY</label>
                            <input type="password" name="gemini_api_key" placeholder="Enter Gemini Key">
                        </div>
                    </div>
                </div>

                <button type="submit" class="btn" id="processBtn">INITIATE PROCESSING SEQUENCE</button>
            </form>

            <div class="status-box" id="statusSection">
                <h2 style="margin-top:0; border:none;">STATUS REPORT</h2>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
                <div style="display:flex; justify-content:space-between; font-weight:bold;">
                    <span>ACT: <span id="currentStep" style="color:var(--primary-blue);">IDLE</span></span>
                    <span>No: <span id="currentChapter">--</span></span>
                </div>
                <div class="logs" id="logs"></div>
            </div>

            <div style="margin-top: 50px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-end; border-bottom: 3px solid var(--primary-blue); margin-bottom: 20px;">
                    <h2 style="border:none; margin:0;">LIBRARY DATABASE</h2>
                    <button class="btn-small" onclick="loadChapters()" style="margin-bottom:5px;">REFRESH</button>
                </div>
                <div id="chaptersList"></div>
            </div>
        </div>
    </div>

    <script>
        let statusInterval;

        document.getElementById('ai_script').addEventListener('change', function(e) {
            document.getElementById('ai_settings').style.display = e.target.checked ? 'block' : 'none';
            localStorage.setItem('ai_script_enabled', e.target.checked);
        });

        if(localStorage.getItem('ai_script_enabled') === 'true') {
            document.getElementById('ai_script').checked = true;
            document.getElementById('ai_settings').style.display = 'block';
        }

        document.getElementById('processForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {
                mode: 'url',
                url: formData.get('url'),
                chapter_name: formData.get('chapter_name'),
                generate_pdf: formData.get('generate_pdf') === 'on',
                run_ml: formData.get('run_ml') === 'on',
                ai_script: formData.get('ai_script') === 'on',
                gemini_api_key: formData.get('gemini_api_key')
            };

            try {
                const res = await fetch('/process', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const json = await res.json();
                if(res.ok) {
                    document.getElementById('statusSection').classList.add('active');
                    document.getElementById('processBtn').disabled = true;
                    document.getElementById('processBtn').innerText = "PROCESSING...";
                    startStatusCheck();
                } else {
                    alert("ERROR: " + json.error);
                }
            } catch(err) {
                alert("CONNECTION ERROR");
            }
        });

        function startStatusCheck() {
            statusInterval = setInterval(checkStatus, 1000);
        }

        async function checkStatus() {
            try {
                const res = await fetch('/status');
                const s = await res.json();
                
                document.getElementById('progressBar').style.width = s.progress + '%';
                document.getElementById('currentStep').innerText = s.current_step.toUpperCase();
                document.getElementById('currentChapter').innerText = s.current_chapter || 'N/A';
                
                const logsDiv = document.getElementById('logs');
                logsDiv.innerHTML = '';
                s.logs.forEach(l => {
                    const row = document.createElement('div');
                    row.innerText = `[${l.timestamp}] ${l.message}`;
                    if(l.level === 'error') row.className = 'log-error';
                    if(l.level === 'success') row.className = 'log-success';
                    logsDiv.appendChild(row);
                });
                logsDiv.scrollTop = logsDiv.scrollHeight;

                if(!s.is_processing) {
                    clearInterval(statusInterval);
                    document.getElementById('processBtn').disabled = false;
                    document.getElementById('processBtn').innerText = "INITIATE PROCESSING SEQUENCE";
                    if(s.current_step === 'Complete') loadChapters();
                }
            } catch(e) { console.log(e); }
        }

        async function loadChapters() {
            const list = document.getElementById('chaptersList');
            list.innerHTML = 'LOADING DATABASE...';
            try {
                const res = await fetch('/chapters');
                const chapters = await res.json();
                list.innerHTML = '';
                if(chapters.length === 0) {
                     list.innerHTML = '<div style="text-align:center; color:#555; padding:20px;">NO RECORDS FOUND</div>';
                     return;
                }
                chapters.forEach(c => {
                    const el = document.createElement('div');
                    el.className = 'chapter-item';
                    el.innerHTML = `
                        <div class="chapter-info">
                            <h4>${c.name}</h4>
                            <p>UPDATED: ${new Date(c.modified*1000).toLocaleString()}</p>
                        </div>
                        <div style="display:flex; gap:10px;">
                             <button class="btn-small" onclick="alert('Checking PDF...')">PDF</button>
                             <button class="btn-small" style="background:var(--primary-blue); color:#fff;" onclick="alert('Opening folder...')">OPEN</button>
                        </div>
                    `;
                    list.appendChild(el);
                });
            } catch(e) {
                list.innerHTML = 'ERROR LOADING DATABASE';
            }
        }

        window.onload = loadChapters;
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    def serve_json(self, data):
        """Serve JSON response"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def serve_chapters(self):
        """Serve list of processed chapters"""
        chapters = []
        base_dir = OUTPUT_BASE  # Use a user-friendly folder in home directory
        
        for item in base_dir.iterdir():
            if (item.is_dir() and 
                not item.name.startswith('.') and 
                item.name not in ['manga_pipeline', 'venv_manga_factory', '__pycache__']):
                
                script_dir = item / 'script'
                transcripts_dir = item / '03_text' / 'transcripts'
                panels_dir = item / 'panels'
                has_any = script_dir.exists() or transcripts_dir.exists() or panels_dir.exists()
                if has_any:
                    chapters.append({
                        'name': item.name,
                        'modified': item.stat().st_mtime
                    })
        
        chapters.sort(key=lambda x: x['modified'], reverse=True)
        self.serve_json(chapters)
    
    def handle_license_activate(self):
        try:
            if LICENSE_MANAGER is None:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'License manager unavailable'}).encode('utf-8'))
                return
            content_length = int(self.headers.get('Content-Length', '0') or 0)
            raw = self.rfile.read(content_length) if content_length else b''
            try:
                payload = json.loads(raw.decode('utf-8')) if raw else {}
            except Exception:
                payload = {}
            key = (payload.get('key') or '').strip()
            if not key:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Key is required'}).encode('utf-8'))
                return
            ok, expiry, reason = LICENSE_MANAGER.validate_license_key(key)
            if ok:
                LICENSE_MANAGER.save_license(key)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'expiry': expiry.strftime('%Y-%m-%d %H:%M:%S') if expiry else None}).encode('utf-8'))
            else:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': reason}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_process(self):
        """Handle processing requests"""
        if processing_status['is_processing']:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Already processing another manga'}).encode('utf-8'))
            return
        
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            url = data.get('url', '').strip()
            chapter_name = data.get('chapter_name', '').strip()
            
            if not url:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'URL is required'}).encode('utf-8'))
                return
            
            # Generate chapter name if not provided
            if not chapter_name:
                # Try to extract meaningful name from URL
                try:
                    if 'webtoons.com' in url:
                        # For Webtoons URLs, try to extract series and episode
                        if '/episode-' in url:
                            episode_part = url.split('/episode-')[1].split('/')[0]
                            series_part = url.split('/')[-3] if len(url.split('/')) > 3 else 'webtoon'
                            chapter_name = f"{series_part}_ep{episode_part}"
                        else:
                            chapter_name = "webtoon_chapter"
                    elif 'mangadx.org' in url or 'mangadex.org' in url:
                        # For MangaDx URLs
                        chapter_name = "manga_chapter"
                    else:
                        # Generic naming
                        url_parts = [part for part in url.split('/') if part and len(part) > 2]
                        if url_parts:
                            # Use last meaningful part of URL
                            last_part = url_parts[-1]
                            if len(last_part) > 20:  # If too long, use second to last
                                last_part = url_parts[-2] if len(url_parts) > 1 else 'chapter'
                            chapter_name = last_part  # No length limit
                        else:
                            chapter_name = 'chapter'
                    
                    # Clean but don't restrict length
                    chapter_name = re.sub(r'[^\w\s-]', '_', chapter_name)
                    if len(chapter_name) < 3:
                        chapter_name = f"chapter_{int(time.time()) % 10000}"
                        
                except Exception:
                    # Fallback to simple naming
                    chapter_name = f"chapter_{int(time.time()) % 10000}"
            
            # Final cleanup of chapter name
            chapter_name = re.sub(r'[^\w\s-]', '_', chapter_name)
            chapter_name = re.sub(r'_+', '_', chapter_name).strip('_')  # Remove multiple underscores
            
            # Ensure it's not empty or too weird
            if not chapter_name or len(chapter_name) < 2:
                chapter_name = f"chapter_{int(time.time()) % 10000}"
            # Use a stable, user-accessible output location
            chapter_path = str(OUTPUT_BASE / chapter_name)
            
            options = {
                'ocr_lang': 'eng',  # Default to English
                'emotion_analysis': True,  # Enable emotion analysis by default
                'enhanced_processing': True,  # All enhanced features enabled
                'validation': True,  # Enable panel validation
                'ai_script': data.get('ai_script', False),
                'gemini_api_key': data.get('gemini_api_key', ''),
                'chapter_title': data.get('chapter_title', ''),
                'series_context': data.get('series_context', '')
            }
            
            # Start processing in background thread
            thread = threading.Thread(
                target=run_manga_pipeline,
                args=(url, chapter_path, options)
            )
            thread.daemon = True
            thread.start()
            
            self.serve_json({'message': 'Processing started', 'chapter': chapter_name})
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def _parse_query(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            return urllib.parse.parse_qs(parsed.query)
        except Exception:
            return {}

    def _safe_path(self, rel_path: str) -> Path:
        rel = rel_path.strip('/').strip()
        candidate = (OUTPUT_BASE / rel).resolve()
        base = OUTPUT_BASE.resolve()
        if str(candidate).startswith(str(base)):
            return candidate
        raise ValueError('Invalid path')

    def serve_file(self):
        try:
            qs = self._parse_query()
            rel = qs.get('path', [''])[0]
            if not rel:
                self.send_error(400, 'Missing path')
                return
            path = self._safe_path(rel)
            if not path.exists() or not path.is_file():
                self.send_error(404, 'File not found')
                return
            ctype, _ = mimetypes.guess_type(str(path))
            if not ctype:
                ctype = 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            with open(path, 'rb') as f:
                self.wfile.write(f.read())
        except Exception as e:
            self.send_error(500, f'File error: {e}')

    def serve_chapter_detail(self):
        try:
            qs = self._parse_query()
            name = qs.get('name', [''])[0]
            if not name:
                self.send_error(400, 'Missing chapter name')
                return
            base = self._safe_path(name)
            if not base.exists() or not base.is_dir():
                self.send_error(404, 'Chapter not found')
                return
            panels_dir = (base / 'panels')
            bubbles_dir = (base / 'bubbles')
            black_dir = (base / 'black')
            strips_dir = (base / 'strips')
            fragments_dir = (base / 'fragments')
            other_dir = (base / 'other')
            transcripts_dir = (base / '03_text' / 'transcripts')
            script_path = (base / 'script' / 'chapter.txt')
            ai_meta_path = (base / 'script' / 'ai_metadata.json')

            def relpaths(paths):
                out = []
                for p in paths:
                    try:
                        out.append(str(p.resolve().relative_to(OUTPUT_BASE.resolve())))
                    except Exception:
                        pass
                return out

            panels = []
            bubbles = []
            black = []
            strips = []
            fragments = []
            other = []
            transcripts = []

            if panels_dir.exists():
                panels = relpaths(sorted(panels_dir.glob('*.png')))
            if bubbles_dir.exists():
                bubbles = relpaths(sorted(bubbles_dir.glob('*.png')))
            if black_dir.exists():
                black = relpaths(sorted(black_dir.glob('*.png')))
            if strips_dir.exists():
                strips = relpaths(sorted(strips_dir.glob('*.png')))
            if fragments_dir.exists():
                fragments = relpaths(sorted(fragments_dir.glob('*.png')))
            if other_dir.exists():
                other = relpaths(sorted(other_dir.glob('*.png')))
            if transcripts_dir.exists():
                transcripts = relpaths(sorted(transcripts_dir.glob('*.txt')))

            script_rel = None
            if script_path.exists():
                try:
                    script_rel = str(script_path.resolve().relative_to(OUTPUT_BASE.resolve()))
                except Exception:
                    script_rel = None

            ai_enhanced = ai_meta_path.exists()

            payload = {
                'name': name,
                'panels': panels,
                'bubbles': bubbles,
                'black': black,
                'strips': strips,
                'fragments': fragments,
                'other': other,
                'transcripts': transcripts,
                'script': script_rel,
                'ai_enhanced': ai_enhanced
            }
            self.serve_json(payload)
        except Exception as e:
            self.send_error(500, f'Chapter error: {e}')


def _auto_set_bundled_env():
    """If running as a bundled app, prefer resources packaged with the app.
    Looks for:
      - Tesseract: resources/tesseract/bin/tesseract
      - Chromium:  resources/Chromium.app/Contents/MacOS/Chromium (or any browser binary found under resources)
      - chromedriver: resources/chromedriver (or any chromedriver in resources)
    Only sets env vars if not already set.
    """
    try:
        bases = []
        # PyInstaller onefile temp dir
        if hasattr(sys, '_MEIPASS'):
            bases.append(Path(getattr(sys, '_MEIPASS')))
        # macOS .app layout: Contents/MacOS/<exe> -> Contents/Resources
        try:
            exe = Path(sys.executable).resolve()
            if 'MacOS' in exe.parts:
                idx = exe.parts.index('MacOS')
                contents = Path(*exe.parts[:idx]) / 'Resources'
                bases.append(contents)
                # Also support MacOS/resources
                bases.append(Path(*exe.parts[:idx+1]) / 'resources')
        except Exception:
            pass
        # Fallback: current file directory
        bases.append(Path(__file__).resolve().parent)
        # Visit all bases and try to set env vars
        for base in bases:
            if not base or not base.exists():
                continue
            res = base / 'resources'
            # Support when base is already the resources folder
            if base.name == 'resources':
                res = base
            # Tesseract
            if 'TESSERACT_CMD' not in os.environ:
                cand = res / 'tesseract' / 'bin' / 'tesseract'
                if cand.exists() and os.access(str(cand), os.X_OK):
                    os.environ['TESSERACT_CMD'] = str(cand)
                    # TESSDATA_PREFIX (language data)
                    share_dir = res / 'tesseract' / 'share'
                    if share_dir.exists():
                        os.environ.setdefault('TESSDATA_PREFIX', str(share_dir))
                    # DYLD_LIBRARY_PATH/LD_LIBRARY_PATH for bundled libs
                    lib_dir = res / 'tesseract' / 'lib'
                    if lib_dir.exists():
                        dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
                        ld = os.environ.get('LD_LIBRARY_PATH', '')
                        new_dyld = f"{lib_dir}:{dyld}" if dyld else str(lib_dir)
                        new_ld = f"{lib_dir}:{ld}" if ld else str(lib_dir)
                        os.environ['DYLD_LIBRARY_PATH'] = new_dyld
                        os.environ['LD_LIBRARY_PATH'] = new_ld
                    add_log(f"Using bundled Tesseract: {cand}")
                    break
        # Chromium / Chrome
        if 'CHROME_BIN' not in os.environ:
            for base in bases:
                if not base or not base.exists():
                    continue
                res = base / 'resources' if base.name != 'resources' else base
                for rel in [
                    'Chromium.app/Contents/MacOS/Chromium',
                    'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
                    'Google Chrome.app/Contents/MacOS/Google Chrome'
                ]:
                    cand = res / rel
                    if cand.exists() and os.access(str(cand), os.X_OK):
                        os.environ['CHROME_BIN'] = str(cand)
                        add_log(f"Using bundled Chrome/Chromium: {cand}")
                        raise StopIteration
        # chromedriver
        if 'CHROMEDRIVER' not in os.environ:
            for base in bases:
                if not base or not base.exists():
                    continue
                res = base / 'resources' if base.name != 'resources' else base
                try:
                    # Find first executable named chromedriver
                    for p in res.rglob('chromedriver'):
                        if p.is_file() and os.access(str(p), os.X_OK):
                            os.environ['CHROMEDRIVER'] = str(p)
                            add_log(f"Using bundled chromedriver: {p}")
                            raise StopIteration
                except StopIteration:
                    break
    except StopIteration:
        pass
    except Exception as e:
        try:
            add_log(f"Bundled env setup error: {e}", 'error')
        except Exception:
            print(f"Bundled env setup error: {e}")


def main():
    """Main function to start the web server"""
    # Try to auto-configure bundled resources for desktop app mode
    _auto_set_bundled_env()
    server_address = ('0.0.0.0', 8080)
    
    try:
        httpd = HTTPServer(server_address, MangaFactoryHandler)
    except OSError as e:
        if "Address already in use" in str(e):
            print("❌ Port 8080 is already in use. Try:")
            print("   lsof -i :8080")
            print("   kill <PID>")
            return
        else:
            raise
    
    print(f"✅ Server running at: http://localhost:8080")
    print("🛑 Press Ctrl+C to stop")
    print("🌐 Open http://localhost:8080 in your browser")

    # Optional: Open browser automatically (can be disabled)
    try:
        if '--no-browser' not in sys.argv:
            threading.Timer(1.0, lambda: webbrowser.open("http://localhost:8080")).start()
    except Exception as e:
        print(f"Note: Could not auto-open browser: {e}")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        httpd.server_close()

if __name__ == "__main__":
    main()
