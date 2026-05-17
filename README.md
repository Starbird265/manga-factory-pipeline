# 🏭 Manga Factory Pipeline

> **Private & Proprietary** — An autonomous, intelligence-driven manga/manhua/manhwa scraping, processing, and publishing pipeline.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](#license)

---

## 📖 Overview

**Manga Factory** is a modular, fault-tolerant pipeline that automates the entire workflow from content discovery to final output generation. It combines multi-layer browser automation, ML-powered site analysis, intelligent proxy management, and advanced image processing into a single cohesive system.

### Core Philosophy

| Principle | Description |
|:---|:---|
| **Speed First** | Always attempt the fastest method (`requests`) before escalating to heavier browser-based scrapers |
| **Intelligence-Driven** | Uses heuristics and historical performance data to predict the best approach per domain |
| **Human-Centric Bypass** | Emulates real user behavior (mouse movement, scrolling, typing) to evade modern anti-bot systems |
| **Modular Processing** | Standardized directory structure (`00_raw` → `01_clean` → `02_stitched`) ensures predictable flow |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MANGA FACTORY PIPELINE                       │
├─────────────┬───────────────┬──────────────┬───────────────────┤
│  Discovery  │   Ingestion   │  Processing  │     Delivery      │
│             │               │              │                   │
│ WebsiteDB   │ UnifiedBypass │ OpenCV Clean │ PDF Generator     │
│ SmartPipe   │   Engine      │ Stitcher     │ Script Generator  │
│ MLSiteLrn   │               │ Panel Detect │ Web UI            │
│             │ ┌───────────┐ │ OCR Engine   │                   │
│             │ │ L0: Heur  │ │              │                   │
│             │ │ L1: HTTP  │ │              │                   │
│             │ │ L2: PW    │ │              │                   │
│             │ │ L3: UC    │ │              │                   │
│             │ └───────────┘ │              │                   │
└─────────────┴───────────────┴──────────────┴───────────────────┘
```

### Multi-Layer Scraping Strategy

| Layer | Component | When Used |
|:---:|:---|:---|
| **L0** | `MLSiteLearner` — Heuristic DOM analysis | Unknown sites; scores images by class, depth, siblings |
| **L1** | `requests` + `BeautifulSoup` | Unprotected / SSR sites (fastest) |
| **L2** | `Playwright` + stealth patches | JS-rendered sites, lazy-loaded content |
| **L3** | `Undetected ChromeDriver` (headful) | Cloudflare Turnstile, aggressive anti-bot |

The **Unified Bypass Engine** orchestrates the escalation automatically — each method is tried exactly once, with proxy rotation between failures.

---

## 📁 Project Structure

```
manga_factory_project/
├── run_app.py                          # CLI entry point
├── launch_with_ollama.sh               # Launch with local AI (Ollama)
├── requirements.txt                    # Python dependencies
├── SETUP.md                            # Detailed setup guide
├── TECHNICAL_ARCHITECTURE.md           # Deep technical documentation
│
├── manga_pipeline/                     # ═══ CORE PIPELINE ═══
│   ├── manga_factory_enhanced.py       # Primary orchestrator (~6000 LOC)
│   ├── unified_bypass_engine.py        # Auto-escalating download engine
│   ├── smart_downloader_enhanced.py    # Multi-layer download strategies
│   ├── website_database.py             # Known site configs & selectors
│   ├── pipeline_orchestrator.py        # Concurrent chapter processing
│   │
│   ├── smart_pipeline_manager.py       # ML — learns best scraper per domain
│   ├── ml_proxy_manager.py             # ML — UCB bandit proxy rotation
│   ├── ml_site_learner.py              # ML — heuristic DOM image detection
│   │
│   ├── human_behavior.py               # Bezier mouse, momentum scroll
│   ├── stealth_config.py               # JS injection for anti-detection
│   ├── cloudflare_handler.py           # CF challenge detection & resolution
│   ├── cookie_manager.py               # Session persistence across runs
│   ├── ad_blocker.py                   # Overlay/popup ad removal
│   ├── popup_closer.py                 # Parallel ad popup thread
│   ├── html_scraper.py                 # Static HTML image extraction
│   │
│   ├── pdf_generator.py                # Chapter → PDF conversion
│   ├── ai_script_generator.py          # Gemini/Ollama narrative scripts
│   ├── comprehensive_test.py           # Integration test suite
│   ├── real_site_test.py               # Live site validation
│   ├── verify_ml.py                    # ML module verification
│   ├── web_app.py                      # Built-in web UI (HTTP server)
│   ├── manga_factory_gui.py            # PyQt6 desktop GUI
│   │
│   ├── core/
│   │   └── ai_analysis.py              # AI content analysis
│   ├── ui/
│   │   ├── server.py                   # UI server backend
│   │   ├── client.py                   # UI client interface
│   │   └── templates/                  # HTML templates
│   ├── utils/
│   │   └── image_ops.py                # Image processing utilities
│   └── data_pipeline/
│       ├── augmentation.py             # Training data augmentation
│       ├── coco_converter.py           # COCO format conversion
│       ├── dataset_splitter.py         # Train/val/test splitting
│       └── yolo_converter.py           # YOLO format conversion
│
└── manga_pipeline/assets/              # Static assets for UI
```

---

## 🧠 Intelligence Modules

### SmartPipelineManager

The "brain" of the pipeline. Records success/failure and duration of every scraping attempt per domain.

- If `requests` fails but `Playwright` succeeds → flags domain to start at Playwright next time
- Learns processing heuristics (e.g., skip denoising for high-quality sites)
- Persists to `pipeline_stats.json`

### MLSiteLearner

Heuristic DOM analyzer for **unknown** websites. Scores each `<img>` tag based on:

- CSS class names (`chapter-img`, `wp-manga`, `reader`)
- Data attributes (`data-src`, `data-lazy-src`)
- DOM depth and parent container context
- Position clustering (manga pages appear as siblings)

### MLProxyManager

Implements **Upper Confidence Bound (UCB)** multi-armed bandit for proxy selection:

- **Exploration**: Tries untested proxies to discover fast ones
- **Exploitation**: Prioritizes low-latency, high-success-rate proxies
- **Auto-ban**: Aggressively bans proxies that trigger CF or return 403s
- Auto-fetches free public proxies as fallback

---

## ⚡ Key Features

### Scraping & Bypass
- 🛡️ **Cloudflare Turnstile bypass** with human-like click behavior
- 🔄 **Auto-escalation** from fast HTTP to headful browser
- 🧑‍💻 **Human behavior emulation** (Bezier curves, momentum scrolling, typed input)
- 🍪 **Cookie persistence** for session reuse across chapters
- 🚫 **Ad/popup blocking** with parallel monitoring thread

### Image Processing
- 🖼️ **Intelligent stitching** with overlap detection and de-duplication
- ✂️ **Scene-aware chunking** — splits strips at panel boundaries (not arbitrary heights)
- 🎯 **Panel extraction** using OpenCV contour detection
- 🧹 **Adaptive cleaning** — denoising, border removal, alignment correction

### Text & Script
- 📝 **Dual OCR** — Tesseract (fast) + EasyOCR (accurate, optional)
- 🤖 **AI script generation** via Gemini API or local Ollama
- 😊 **Emotion analysis** using text2emotion for scene tone detection

### Output
- 📄 **PDF generation** from stitched strips (via img2pdf)
- 🌐 **Built-in web UI** — retro pixelated interface with live progress
- 🖥️ **Desktop GUI** via PyQt6
- 📊 **Processing statistics** and ML intelligence persistence

---

## 🔧 Supported Sites

| Site | Cloudflare | Method | Notes |
|:---|:---:|:---|:---|
| TopManhua | ❌ | Playwright | WP-manga theme, lazy-loaded |
| ManhwaClan | ✅ | UC (headful) | Requires visible browser + human scroll |
| ManhuaUS | ✅ | UC (headful) | Multi-layer fallback |
| MangaTX | ✅ | UC (headful) | WP-manga with CF |
| Webtoons | ❌ | Playwright | Official platform |
| MangaDex | ❌ | Playwright | API + reader |
| Mangakakalot | ❌ | Requests | Simple SSR |
| MangaRead | ❌ | Requests | Basic HTML |
| ZinManga | ❌ | Playwright | WP-manga theme |
| **Unknown sites** | Auto-detect | Auto-escalate | MLSiteLearner + generic selectors |

---

## 🚀 Quick Start

```bash
# 1. Clone (private repo)
git clone https://github.com/Starbird265/manga-factory-pipeline.git
cd manga-factory-pipeline

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install browser drivers
playwright install chromium

# 5. Run via CLI
python run_app.py "https://example-manga-site.com/chapter/1"

# 6. Or launch the web UI
python -m manga_pipeline.web_app
```

> For detailed setup instructions, see **[SETUP.md](SETUP.md)**.

---

## 🖥️ Usage

### CLI Mode

```bash
# Basic usage
python run_app.py "<chapter-url>"

# With custom output directory
python run_app.py "<chapter-url>" --output ./my_output

# Webtoon mode (optimized for long vertical strips)
python run_app.py "<chapter-url>" --mode webtoon
```

### Web UI Mode

```bash
# Start the web server (opens in browser)
python -m manga_pipeline.web_app
```

The web interface provides:
- URL input with auto-detection
- Real-time processing progress
- Chapter library browser
- Configuration toggles (PDF, AI scripting, ML processing)

### With Local AI (Ollama)

```bash
# Launch with local Ollama model for AI script generation
./launch_with_ollama.sh
```

---

## 🔐 Environment Variables

| Variable | Required | Description |
|:---|:---:|:---|
| `GEMINI_API_KEY` | Optional | Google Gemini API key for AI script generation |
| `TESSERACT_CMD` | Optional | Path to Tesseract binary (auto-detected) |
| `CHROME_BIN` | Optional | Path to Chrome/Brave for Undetected ChromeDriver |
| `CHROMEDRIVER` | Optional | Path to ChromeDriver binary |
| `ENABLE_EASYOCR` | Optional | Set to `1` to enable EasyOCR (default: `0` for speed) |

---

## 📂 Output Structure

Each processed chapter creates a standardized directory:

```
MangaFactory/<series-name>/<chapter-number>/
├── 00_raw/              # Original downloaded images
├── 01_clean/            # Cleaned and processed images
├── 02_stitched/
│   ├── complete_manga_strip.png    # Full vertical strip
│   ├── stitched_part_001.png       # Scene-chunked segments
│   ├── stitched_part_002.png
│   └── panels/                     # Individual extracted panels
├── 03_text/
│   └── transcripts/     # OCR text output per panel
├── panels/              # Validated panels
├── script/              # Generated narrative scripts
└── manga_factory_enhanced.log
```

---

## 🧪 Testing

```bash
# Verify ML modules are loaded correctly
python manga_pipeline/verify_ml.py

# Run comprehensive integration tests
python manga_pipeline/comprehensive_test.py

# Test against a live site
python manga_pipeline/real_site_test.py
```

---

## 📋 Pipeline Workflow

```
1. Discovery     → SmartPipelineManager checks domain history
2. Ingestion     → UnifiedBypassEngine retrieves images → 00_raw/
3. Refinement    → OpenCV cleaning & normalization → 01_clean/
4. Integration   → Intelligent stitching with overlap detection → 02_stitched/
5. Extraction    → Contour-based panel detection → panels/
6. Intelligence  → OCR text extraction + AI script generation → script/
7. Delivery      → PDF generation → manga_pdfs/
```

---

## 🛠️ Development

### Adding a New Site

1. Add a site config to `website_database.py`:

```python
"newsite.com": {
    "name": "NewSite",
    "image_selectors": [".reading-content img"],
    "cloudflare": True,
    "requires_js": True,
    "scroll_needed": True,
    "best_method": "undetected_chrome",
}
```

2. The `UnifiedBypassEngine` will automatically use this config for routing.

3. For sites needing custom logic, add a method in `manga_factory_enhanced.py`.

### Adding a New Bypass Method

1. Add the method name to `UnifiedBypassEngine.ESCALATION_CHAIN`
2. Implement `_try_<method_name>()` in `unified_bypass_engine.py`
3. Register it in the `_try_method()` dispatch table

---

## ⚠️ Disclaimer

This project is for **personal and educational use only**. Respect the terms of service of any website you interact with. The authors are not responsible for misuse.

---

## 📜 License

**Proprietary** — All rights reserved. This is personal intellectual property and is not licensed for redistribution, modification, or commercial use without explicit written permission.

© 2024-2026 Gaurav Singh. All rights reserved.
