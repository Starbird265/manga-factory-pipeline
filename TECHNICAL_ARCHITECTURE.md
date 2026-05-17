# Manga Factory: Technical Architecture & Pipeline Documentation

This document provides a comprehensive technical breakdown of the **Manga Factory** project, an automated, multi-layered pipeline designed for high-performance manga/manhua content extraction, processing, and intelligence-driven site analysis.

---

## 1. System Overview

The Manga Factory is architected as a modular, fault-tolerant pipeline. It decouples browser automation from business logic, allowing for seamless transitions between different scraping strategies (from fast HTML requests to heavy-duty browser emulation).

### Core Philosophy:
- **Speed First:** Always attempt the fastest method (Requests) before escalating to slower ones (Playwright/UC).
- **Intelligence-Driven:** Use heuristics and past performance to predict the best scraper for a domain.
- **Human-Centric Bypass:** Emulate real user behavior to bypass modern anti-bot protections like Cloudflare and Datadome.
- **Modular Processing:** Standardized directories (`00_raw`, `01_clean`, `02_stitched`) ensure a predictable flow from raw pixels to translated scripts and PDFs.

---

## 2. Multi-Layer Scraping Strategy

The system employs a 4-layer escalation strategy to ensure content is retrieved regardless of site protection levels.

| Layer | Component | Technical Reasoning |
| :--- | :--- | :--- |
| **L0: Heuristic** | `MLSiteLearner` | Analyzes raw DOM for image clusters without needing site-specific selectors. Fast & efficient. |
| **L1: Static** | `HTMLScraper` | Uses `requests` + `BeautifulSoup`. No JavaScript overhead. Best for SSR sites. |
| **L2: Stealth** | `Playwright` | Headless Chromium with `playwright-stealth`. Injects JS patches to hide automation signals. |
| **L3: Ultimate** | `Undetected ChromeDriver` | Modified Selenium driver that bypasses Cloudflare Turnstile and other TLS/Fingerprint checks. |

---

## 3. Intelligent Processing Components

### `SmartPipelineManager`
This acts as the "Brain" of the pipeline. It records the success/failure and duration of every scraping attempt per domain.
- **Logic:** If `requests` fails but `Playwright` succeeds, it flags the domain to start at `Playwright` next time.
- **Optimization:** It also learns "Processing Heuristics." If a site's images are consistently high quality, it flags `clean_images` to save CPU during the cleaning phase.

### `MLSiteLearner`
A heuristic DOM analyzer that identifies manga pages on unknown websites.
- **Scoring Engine:** Ranks images based on:
    - **Class Names:** Keywords like `chapter-img`, `reader`, `wp-manga`.
    - **Data Attributes:** Prioritizes `data-src` or `data-lazy-src` (common in manga readers).
    - **DOM Hierarchy:** Manga pages are usually siblings in a deep container.
    - **Clustering:** It identifies the "main cluster" of images and ignores logos/ads.

### `MLProxyManager`
Implements a **Multi-Armed Bandit (UCB)** algorithm for proxy selection.
- **Exploration vs. Exploitation:** It tries new proxies (exploration) but prioritizes those with low latency and high success rates (exploitation).
- **Auto-Banning:** Aggressively bans proxies that trigger Cloudflare challenges or return 403s.

---

## 4. Key Classes & Methods

### `EnhancedMangaFactory` (`manga_factory_enhanced.py`)
The primary orchestrator.
- `download_chapter(url)`: The entry point. Consults `SmartPipelineManager` for the best strategy and executes the download loop.
- `clean_pages_enhanced()`: Uses OpenCV for adaptive thresholding, denoising, and border removal.
- `process_stitching_enhanced()`: Merges individual pages into vertical webtoon-style strips or structured PNGs.
- `extract_panels_enhanced()`: Uses contour detection to isolate individual panels from large strips.
- `process_ocr_enhanced()`: Integrates Tesseract/EasyOCR with adaptive preprocessing for maximum accuracy.

### `EnhancedSmartDownloader` (`smart_downloader_enhanced.py`)
The engine behind the multi-layer strategy.
- `download_manga_automated(url)`: Orchestrates the escalation from Layer 1 to Layer 3.
- `_resolve_cloudflare()`: Uses `CloudflareHandler` to poll the page title/body for challenge completion.

### `WebsiteDatabase` (`website_database.py`)
A centralized registry for domain-specific knowledge.
- Stores CSS selectors, Cloudflare status, and special JS requirements.
- Provides `GENERIC_IMAGE_SELECTORS` as a safety net for unknown domains.

---

## 5. Site-Specific Adapters

While the system prioritizes generic scraping, certain high-traffic domains require specialized logic to handle unique DOM structures or aggressive anti-bot measures.

### Webtoons (`_download_webtoon_html_fallback`)
- **Strategy:** Uses specific regex patterns to extract `webtoon-phinf` URLs directly from scripts if DOM selection fails.
- **Validation:** Implements strict image validation to filter out thumbnails (`type=a92`, `type=f218`) and only keep high-res episode images.

### ManhuaUS (`_download_manhuaus`)
- **Strategy:** Multithreaded download with domain-specific referer headers.
- **Normalization:** Automatically fixes relative URLs and protocol-less (`//`) links.
- **Escalation:** If 403s occur, it automatically escalates to the `cloudscraper` or `Playwright` layer.

### ManhwaClan (`_download_manhwaclan`)
- **Strategy:** Exclusively uses **Visible Undetected ChromeDriver** for maximum reliability.
- **Behavior:** Injects randomized "Human-like" scrolling and pauses to mimic a real reader, which is necessary to trigger their specific lazy-load implementation.
- **Automation:** Uses a parallel `PopupCloser` thread to kill intrusive ad overlays that block the view.

### WP-Manga Theme Sites (`_download_wpmanga`)
- **Strategy:** Generic adapter for sites using the "Madara" or "WP-Manga" WordPress theme (e.g., ZinManga, MangaTX).
- **Selector Chain:** Targets `.reading-content img.wp-manga-chapter-img` and automatically resolves `data-src` lazy-loading.

---

## 6. Bypass & Resilience Mechanisms

### Human Behavior Emulation (`human_behavior.py`)
When using browser layers, the system mimics human interaction to avoid detection:
- **Bezier Mouse Movement:** Non-linear cursor movement with random overshoot and correction.
- **Momentum Scrolling:** Natural, eased scrolling patterns that trigger lazy loaders.
- **Human Typing:** Variable speed typing with occasional backspacing.

### Stealth Injection (`stealth_config.py`)
Injects JavaScript patches at the driver level to:
- Override `navigator.webdriver`.
- Spoof `navigator.plugins`, `languages`, and `platform`.
- Fake `window.chrome` objects that are absent in headless environments.

### Fault-Tolerant Retry Logic
- **Exponential Backoff:** If a request fails, the system waits (1s, 2s, 4s...) with random jitter.
- **Cookie Persistence:** `CookieManager` saves Cloudflare-solved sessions to `~/.manga_cookies/`, allowing the pipeline to skip the challenge on subsequent chapters.

---

## 6. Pipeline Workflow

1. **Discovery:** `SmartPipelineManager` checks domain history.
2. **Ingestion:** `SmartDownloader` retrieves images into `00_raw`.
3. **Refinement:** `OpenCV` cleans noise and fixes alignment in `01_clean`.
4. **Integration:** `Stitcher` creates the master strip in `02_stitched`.
5. **Extraction:** Contour analysis splits the strip into individual panels.
6. **Intelligence:** OCR extracts text; Gemini/Transformers generate a narrative script.
7. **Delivery:** `PDFGenerator` creates the final reading file.

---

## 7. Configuration & Environment

- **Tesseract Path:** Must be set in `TESSERACT_CMD` if not in PATH.
- **Chrome Bin:** Path to Chrome/Brave for UC (`CHROME_BIN`).
- **OCR Logic:** Toggleable between Tesseract (Standard) and EasyOCR (ML-Heavy) via `ENABLE_EASYOCR`.
