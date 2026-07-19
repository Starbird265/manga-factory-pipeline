#!/usr/bin/env python3
"""Generate compact, multipage chapter PDFs from stitched strip parts."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

try:
    import img2pdf

    IMG2PDF_AVAILABLE = True
except ImportError:
    img2pdf = None
    IMG2PDF_AVAILABLE = False

from PIL import Image


logger = logging.getLogger(__name__)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _natural_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def extract_manga_info(chapter_dir):
    """Return the series directory name and normalized chapter label."""
    chapter_path = Path(chapter_dir)
    chapter_label = chapter_path.name
    if not chapter_label.lower().startswith("chapter_"):
        chapter_label = f"Chapter_{chapter_label}"
    return chapter_path.parent.name, chapter_label


def _existing_images(image_paths: Iterable) -> List[Path]:
    paths = [Path(path) for path in image_paths]
    return [
        path for path in sorted(paths, key=lambda item: _natural_key(item.name))
        if path.exists() and path.suffix.lower() in IMAGE_SUFFIXES
    ]


def generate_pdf_from_images(
    image_paths: Sequence,
    output_pdf_path,
    manga_name: Optional[str] = None,
    chapter_num: Optional[str] = None,
):
    """Write one PDF page per image using img2pdf or the bundled Pillow fallback."""
    pages = _existing_images(image_paths)
    pdf_path = Path(output_pdf_path)
    if not pages:
        logger.error("PDF generation failed: no stitched images were found")
        return False

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = pdf_path.with_suffix(pdf_path.suffix + ".tmp")
    try:
        if IMG2PDF_AVAILABLE:
            with temporary_path.open("wb") as pdf_file:
                pdf_file.write(img2pdf.convert([str(path) for path in pages]))
            backend = "img2pdf"
        else:
            opened = []
            try:
                for path in pages:
                    image = Image.open(path)
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    opened.append(image)
                opened[0].save(
                    temporary_path,
                    "PDF",
                    save_all=True,
                    append_images=opened[1:],
                    resolution=144.0,
                )
            finally:
                for image in opened:
                    image.close()
            backend = "Pillow fallback"

        if not temporary_path.exists() or temporary_path.stat().st_size == 0:
            raise RuntimeError("PDF writer produced an empty file")
        temporary_path.replace(pdf_path)
        size_mb = pdf_path.stat().st_size / 1024 / 1024
        logger.info(
            "PDF generated: %s (%.2f MB, %d pages, %s)",
            pdf_path,
            size_mb,
            len(pages),
            backend,
        )
        if manga_name and chapter_num:
            logger.info("Series: %s | Chapter: %s", manga_name, chapter_num)
        return True
    except Exception as exc:
        logger.error("PDF generation failed for %s: %s", pdf_path, exc)
        if temporary_path.exists():
            temporary_path.unlink()
        return False


def generate_pdf_from_strip(strip_image_path, output_pdf_path, manga_name=None, chapter_num=None):
    """Backward-compatible single-strip PDF entry point."""
    return generate_pdf_from_images(
        [strip_image_path],
        output_pdf_path,
        manga_name=manga_name,
        chapter_num=chapter_num,
    )


def generate_chapter_pdf(chapter_dir, output_base_dir=None):
    """Generate a chapter PDF, preferring exact non-overlapping strip parts."""
    chapter_path = Path(chapter_dir)
    manga_series, chapter_label = extract_manga_info(chapter_path)
    stitched_dir = chapter_path / "02_stitched"
    parts_dir = stitched_dir / "parts"
    pages = _existing_images(parts_dir.glob("stitched_part_*.png"))
    if not pages:
        complete_strip = stitched_dir / "complete_manga_strip.png"
        pages = [complete_strip] if complete_strip.exists() else []
    if not pages:
        logger.error("PDF generation failed: no stitched output exists in %s", stitched_dir)
        return None

    external_output = output_base_dir is not None
    if external_output:
        output_dir = Path(output_base_dir) / manga_series
    else:
        output_dir = chapter_path
    pdf_path = output_dir / f"{chapter_label}.pdf"

    if not generate_pdf_from_images(pages, pdf_path, manga_series, chapter_label):
        return None

    if external_output:
        strip_path = stitched_dir / "complete_manga_strip.png"
        if strip_path.exists():
            try:
                shutil.copy2(strip_path, output_dir / f"{chapter_label}_strip.png")
            except Exception as exc:
                logger.warning("Could not copy the full strip beside the PDF: %s", exc)
    return str(pdf_path)


def batch_generate_pdfs(manga_series_dir, output_base_dir=None):
    """Generate PDFs for every Chapter_* directory in a series."""
    series_path = Path(manga_series_dir)
    chapter_dirs = sorted(
        [path for path in series_path.iterdir() if path.is_dir() and path.name.lower().startswith("chapter_")],
        key=lambda path: _natural_key(path.name),
    )
    results = {
        "success_count": 0,
        "failed_count": 0,
        "total_count": len(chapter_dirs),
        "pdf_paths": [],
    }
    for chapter_dir in chapter_dirs:
        pdf_path = generate_chapter_pdf(chapter_dir, output_base_dir=output_base_dir)
        if pdf_path:
            results["success_count"] += 1
            results["pdf_paths"].append(pdf_path)
        else:
            results["failed_count"] += 1
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a Manga Factory chapter PDF")
    parser.add_argument("chapter_dir")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = generate_chapter_pdf(args.chapter_dir, output_base_dir=args.output)
    raise SystemExit(0 if result else 1)
