# How To Use Manga Factory

This guide is for the local desktop application in this folder. Run every command from the project root:

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
```

## 1. One-time setup on macOS

Install system tools first:

```bash
brew install python@3.11 tesseract tesseract-lang
```

Create and activate the project environment:

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install PyQt6 img2pdf
python -m playwright install chromium
```

Confirm the important pieces are available:

```bash
python -c "import cv2, img2pdf, PyQt6, pytesseract; print('Python packages ready')"
tesseract --version
```

Use `source venv/bin/activate` at the start of each new Terminal session before running the app.

## 2. Start the desktop GUI

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -B manga_pipeline/manga_factory_gui.py
```

In the GUI:

1. Paste one reader URL per line into **Chapter Queue**. You can also use **Import URL List** to add a `.txt` or `.csv` file. Empty lines and lines starting with `#` are ignored.
2. Set a **Series output name**. This is the permanent series memory folder, so use the same name for every chapter of one manga.
3. Choose an **Output folder**. A good default is `/Users/gauravsingh/Desktop/MangaOutput`.
4. Click **Preview Queue**. The queue shows each generated chapter folder before anything downloads.
5. With one reader URL, use **Chapters** to select the count, then click **Resolve Chapters**. Manga Factory reads the site's own chapter navigation and fills the queue with real URLs, including sites whose chapter IDs are not sequential. `{chapter}` templates and pasted chapter lists still work. Set **Parallel** to `1` for a single chapter, or `2` or `3` for concurrent chapters. Set **Retries** to `1` or `2` for unstable sites. Do not exceed `3` when using visible browsers.
6. The default **Studio Powers** switches run capture, cleanup, full-strip stitching, scene cutting, OCR, dialogue and character context, scripts, emotion tags, source learning, and PDF generation. Leave **Force redownload** off unless you want to replace raw pages.
7. Click **Run Queue**. The queue reports every chapter as queued, active, complete, failed, or stopped; the lower terminal shows the real worker log.
8. Inkbit's pixel stage mirrors the real worker phase, including fetching, cleanup, strip stitching, scene cuts, dialogue/context work, scripts, PDF binding, errors, and completion.
9. When the run finishes, use **Open Full Strip**, **Open Scenes**, **Open Panels**, **Open PDF**, **Open Script**, or **Open Characters** to inspect the generated work.

For the supplied RoliaScan chapter, use this URL:

```text
https://roliascan.com/read/legendary-hero-is-an-academy-honors-student/ch1-32984/
```

## 3. Recommended GUI settings

| Goal | Settings |
| --- | --- |
| One new chapter | Parallel `1`; keep all processing controls enabled |
| Three chapters at once | Paste three exact chapter URLs on separate lines, click Preview Queue, set Parallel `3`, retain Headful account browsers |
| Re-download a chapter | Enable **Force redownload**; leave Stitch strips and Cut panels enabled |
| Make video scenes | Enable **Stitch strips** and **Cut panels from full strip** |
| Create a PDF only | Enable **Generate PDF**; PDF uses stitched parts and falls back to Pillow if `img2pdf` is unavailable |
| Continue series memory | Reuse the exact same Series output name for later chapters |
| Retry an unstable site | Set Retries to `1` or `2`; each failed download is retried before its job is marked failed |

## 4. Run one chapter from Terminal

This is the full pipeline: download, cleanup, stitch, scene extraction, OCR, character context, script, and PDF.

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -B manga_pipeline/manga_factory_enhanced.py \
  --url "https://roliascan.com/read/legendary-hero-is-an-academy-honors-student/ch1-32984/" \
  --chapter-dir "/Users/gauravsingh/Desktop/MangaOutput/Legendary Hero Is An Academy Honors Student/Chapter_1" \
  --mode webtoon \
  --stitch-extract-panels \
  --learn-characters \
  --analyze-scenes \
  --emotion
```

Use `--mode manga` for page-by-page manga. Use `--mode webtoon` for long vertical strips such as RoliaScan chapters.

## 5. Run up to three chapters in parallel from Terminal

Use multiple `--url` entries. Each chapter receives its own output folder under the base directory.

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -B manga_pipeline/manga_factory_enhanced.py \
  --url "https://example.com/chapter-1" \
  --url "https://example.com/chapter-2" \
  --url "https://example.com/chapter-3" \
  --chapter-dir "/Users/gauravsingh/Desktop/MangaOutput/My Series" \
  --mode webtoon \
  --concurrent 3 \
  --stitch-extract-panels \
  --learn-characters \
  --analyze-scenes
```

Replace all three example URLs before running. Keep the concurrency at `3` or below for reliable browser use.

## 6. Rebuild scenes from an existing full strip

Use this when the chapter has already been downloaded and stitched, and you only want improved scene extraction. It preserves each detected scene slice in the video frame, using blurred fill instead of cutting people or faces.

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -B -c "from pathlib import Path; import sys; sys.path.insert(0, 'manga_pipeline'); from advanced_stitcher import AdvancedStitcher; result = AdvancedStitcher(Path('/Users/gauravsingh/Desktop/MangaOutput/Legendary Hero Is An Academy Honors Student/Chapter_1')).extract_video_scenes_from_complete_strip(); print(result)"
```

Open the new scene folder:

```bash
open "/Users/gauravsingh/Desktop/MangaOutput/Legendary Hero Is An Academy Honors Student/Chapter_1/02_stitched/video_scenes"
```

The scene metadata is here:

```bash
open "/Users/gauravsingh/Desktop/MangaOutput/Legendary Hero Is An Academy Honors Student/Chapter_1/02_stitched/video_scenes/video_scene_manifest.json"
```

## 7. Find the generated files

For a chapter output folder named `Chapter_1`:

```text
Chapter_1/
  02_stitched/complete_manga_strip.png        full stitched webtoon strip
  02_stitched/parts/                          PDF-safe strip parts
  02_stitched/panels/                         full-strip archival panel cuts
  02_stitched/video_scenes/                   video-ready scene images
  02_stitched/video_scenes/video_scene_manifest.json
  panels/                                     final filtered panels used for OCR
  03_text/                                    OCR text and dialogue details
  script/chapter.txt                          readable chapter script
  script/characters.json                      current character profiles
  Chapter_1.pdf                               generated PDF
  manga_factory_enhanced.log                  full processing log
```

Series memory is separate from chapters and grows over time:

```text
<series folder>/series_context/character_profiles.json
```

## 8. Fix common problems

### `img2pdf not installed`

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -m pip install img2pdf
```

The pipeline will still create a PDF through Pillow when this package is missing, but `img2pdf` is recommended.

### `tesseract is not installed`

```bash
brew install tesseract tesseract-lang
```

Then launch the GUI from a freshly activated terminal.

### Browser or RoliaScan download fails

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -m playwright install chromium
```

Run the GUI with **Headful account browsers** enabled. A visible Chrome window may require you to complete a site challenge yourself.

### Scene images cut a character

Run the scene rebuild command in section 6. The updated renderer retains the full detected scene range; scene boundaries may still split two distinct shots, but no additional internal zoom crop is applied.

### GUI does not start

```bash
cd /Users/gauravsingh/Desktop/manga-factory-pipeline
source venv/bin/activate
python -m pip install PyQt6
python -B manga_pipeline/manga_factory_gui.py
```

## 9. Stop the GUI

Close the Manga Factory window normally. In the Terminal that launched it, press `Control-C` if the window is no longer visible but the process remains active.
