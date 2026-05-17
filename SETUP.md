# 🛠️ Setup Guide — Manga Factory Pipeline

Complete setup instructions for running the Manga Factory Pipeline on macOS, Linux, or Windows (WSL).

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Browser Drivers](#browser-drivers)
4. [OCR Setup](#ocr-setup)
5. [Optional: AI Script Generation](#optional-ai-script-generation)
6. [Configuration](#configuration)
7. [Verifying Installation](#verifying-installation)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|:---|:---|:---|
| **Python** | 3.10 | 3.11+ |
| **RAM** | 4 GB | 8+ GB (for OCR + browser automation) |
| **Disk** | 2 GB | 10+ GB (for manga output + models) |
| **OS** | macOS 12+, Ubuntu 20.04+, Windows 10+ (WSL2) | macOS 13+ |

### Required Software

| Software | Purpose | Install Command |
|:---|:---|:---|
| **Python 3.10+** | Runtime | `brew install python@3.11` (macOS) |
| **Google Chrome** | Browser automation | [Download](https://www.google.com/chrome/) |
| **Tesseract OCR** | Text recognition | `brew install tesseract` (macOS) |
| **Git** | Version control | `brew install git` (macOS) |

---

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/Starbird265/manga-factory-pipeline.git
cd manga-factory-pipeline
```

### Step 2: Create Virtual Environment

```bash
# Create
python3 -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate
```

### Step 3: Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Install Additional Dependencies

Some packages have optional heavy dependencies. Install based on your needs:

```bash
# Core (always required)
pip install requests beautifulsoup4 Pillow opencv-python numpy

# Browser automation (required for most sites)
pip install playwright playwright-stealth undetected-chromedriver selenium webdriver-manager

# OCR (required for text extraction)
pip install pytesseract

# OCR — Enhanced (optional, more accurate but slower)
pip install easyocr

# PDF generation
pip install img2pdf

# AI features (optional)
pip install transformers peft text2emotion

# Desktop GUI (optional)
pip install PyQt6
```

### Step 5: Install Playwright Browsers

```bash
playwright install chromium
```

> **Note**: This downloads a Chromium binary (~150MB). Required for Playwright-based scraping.

---

## Browser Drivers

### Google Chrome (Required for Undetected ChromeDriver)

The `undetected-chromedriver` package requires Google Chrome installed:

- **macOS**: Install from [google.com/chrome](https://www.google.com/chrome/)
  - Expected path: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- **Linux**: `sudo apt install google-chrome-stable`

### ChromeDriver (Auto-managed)

ChromeDriver is automatically managed by `webdriver-manager`. If you need a custom path:

```bash
export CHROMEDRIVER=/path/to/chromedriver
```

### Custom Chrome Binary

If using Brave or a custom Chrome:

```bash
export CHROME_BIN="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
```

---

## OCR Setup

### Tesseract (Primary OCR Engine)

**macOS:**
```bash
brew install tesseract

# Install additional language packs
brew install tesseract-lang
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-jpn tesseract-ocr-kor
```

**Verify:**
```bash
tesseract --version
```

If Tesseract isn't in PATH, set the environment variable:
```bash
export TESSERACT_CMD=/opt/homebrew/bin/tesseract  # macOS (Apple Silicon)
export TESSERACT_CMD=/usr/bin/tesseract            # Linux
```

### EasyOCR (Optional — More Accurate)

EasyOCR provides ML-based OCR that's more accurate for manga text but significantly slower:

```bash
pip install easyocr
```

**Enable at runtime:**
```bash
export ENABLE_EASYOCR=1
```

> **Default**: EasyOCR is **disabled** (`ENABLE_EASYOCR=0`) for speed. Tesseract is used by default.

---

## Optional: AI Script Generation

### Option A: Google Gemini (Cloud)

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/)
2. Set the environment variable:

```bash
export GEMINI_API_KEY="your-api-key-here"
```

Or provide the key in the Web UI's Advanced Settings.

### Option B: Ollama (Local, Private)

1. Install Ollama: [ollama.com](https://ollama.com/)
2. Pull a model:

```bash
ollama pull llama3.1:8b
# Or for the best results:
ollama pull gpt-oss:120b
```

3. Launch with the Ollama script:

```bash
./launch_with_ollama.sh
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root (optional):

```env
# AI (optional)
GEMINI_API_KEY=your-key-here

# OCR
TESSERACT_CMD=/opt/homebrew/bin/tesseract
ENABLE_EASYOCR=0

# Browser
CHROME_BIN=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
CHROMEDRIVER=/path/to/chromedriver
```

### Pipeline Configuration

The pipeline uses sensible defaults that can be overridden via a config file:

```ini
[OCR]
language = eng
confidence_threshold = 60
preprocessing = true
use_easyocr = false

[PROCESSING]
auto_format_detection = true
advanced_stitching = true
panel_validation = true
duplicate_threshold = 0.95
chunk_stitched_by_panels = true
chunk_min_panels_per_part = 5
chunk_max_panels_per_part = 10

[LOGGING]
level = INFO
detailed_errors = true
```

### Output Directory

By default, processed manga is saved to:
- **CLI mode**: Specified via `--output` flag (default: `manga_output/`)
- **Web UI mode**: `~/MangaFactory/`

---

## Verifying Installation

### Quick Verification

```bash
# Activate your virtual environment
source venv/bin/activate

# Verify Python version
python --version  # Should be 3.10+

# Verify core imports
python -c "
import cv2; print(f'OpenCV: {cv2.__version__}')
import numpy; print(f'NumPy: {numpy.__version__}')
from PIL import Image; print('Pillow: OK')
import requests; print('Requests: OK')
from bs4 import BeautifulSoup; print('BeautifulSoup: OK')
print('✅ Core dependencies OK')
"

# Verify browser automation
python -c "
from playwright.sync_api import sync_playwright; print('Playwright: OK')
import undetected_chromedriver as uc; print('UC: OK')
from selenium import webdriver; print('Selenium: OK')
print('✅ Browser automation OK')
"

# Verify OCR
python -c "
import pytesseract
from PIL import Image
result = pytesseract.image_to_string(Image.new('RGB', (100, 100), 'white'))
print('✅ Tesseract OCR OK')
"

# Verify ML modules
python manga_pipeline/verify_ml.py
```

### Full Integration Test

```bash
python manga_pipeline/comprehensive_test.py
```

---

## Troubleshooting

### Common Issues

#### 1. `playwright install` fails

```bash
# Try with sudo on Linux
sudo playwright install chromium

# Or install system dependencies first
sudo playwright install-deps chromium
```

#### 2. Tesseract not found

```bash
# macOS — check Homebrew path
which tesseract
# Expected: /opt/homebrew/bin/tesseract (Apple Silicon)
#           /usr/local/bin/tesseract (Intel)

# Set explicitly
export TESSERACT_CMD=$(which tesseract)
```

#### 3. Chrome/ChromeDriver version mismatch

```bash
# The webdriver-manager package handles this automatically.
# If issues persist, update:
pip install --upgrade webdriver-manager undetected-chromedriver
```

#### 4. `ModuleNotFoundError` for pipeline modules

Make sure you're running from the project root:

```bash
cd manga-factory-pipeline
python run_app.py "..."

# Or for web_app:
cd manga-factory-pipeline
python -m manga_pipeline.web_app
```

#### 5. EasyOCR downloading models on first run

EasyOCR downloads detection models (~100MB) on first use. This is normal and happens once.

#### 6. `img2pdf` fails with JPEG images

Some sites serve JPEG images with non-standard EXIF data:

```bash
pip install --upgrade img2pdf Pillow
```

#### 7. Cloudflare bypass not working

- Ensure Google Chrome is installed (not just Chromium)
- UC requires a **headful** browser for CF sites — the pipeline handles this automatically
- Check that no firewall/VPN is interfering

#### 8. Memory issues with large chapters

For chapters with 100+ pages:

```bash
# Increase Python's memory limit (if applicable)
ulimit -v unlimited

# Or process in batches via the orchestrator
```

---

## Updating

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Update Playwright browser
playwright install chromium
```

---

## Uninstalling

```bash
# Deactivate virtual environment
deactivate

# Remove virtual environment
rm -rf venv/

# Remove downloaded manga data (optional)
rm -rf ~/MangaFactory/

# Remove cookie cache (optional)
rm -rf ~/.manga_cookies/
```

---

## Need Help?

- Check the [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md) for deep system documentation
- Run `python manga_pipeline/verify_ml.py` to diagnose module issues
- Check logs in `manga_factory_enhanced.log` for detailed error traces
