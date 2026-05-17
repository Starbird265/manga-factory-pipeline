#!/usr/bin/env python3
"""
PDF Generator for Manga Factory
Converts complete stitched manga strips to PDF format
"""

import os
import logging
from pathlib import Path
try:
    import img2pdf
    IMG2PDF_AVAILABLE = True
except ImportError:
    img2pdf = None
    IMG2PDF_AVAILABLE = False

logger = logging.getLogger(__name__)


def extract_manga_info(chapter_dir):
    """
    Extract manga series name and chapter number from chapter directory path.
    
    Args:
        chapter_dir: Path to chapter directory (e.g., 'MangaFactory/tutorial-tower/001')
    
    Returns:
        tuple: (manga_series_name, chapter_number)
    """
    try:
        chapter_path = Path(chapter_dir)
        chapter_number = chapter_path.name  # e.g., '001'
        manga_series = chapter_path.parent.name  # e.g., 'the-tutorial-tower-of-the-advanced-player'
        return manga_series, chapter_number
    except Exception as e:
        logger.error(f"Error extracting manga info from path {chapter_dir}: {e}")
        return None, None


def generate_pdf_from_strip(strip_image_path, output_pdf_path, manga_name=None, chapter_num=None):
    """
    Convert a complete stitched manga strip (PNG) to PDF format.
    
    Args:
        strip_image_path: Path to the complete_manga_strip.png file
        output_pdf_path: Path where PDF should be saved
        manga_name: Optional manga series name for logging
        chapter_num: Optional chapter number for logging
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not IMG2PDF_AVAILABLE:
            logger.error("img2pdf not installed. Install with: pip install img2pdf")
            return False

        strip_path = Path(strip_image_path)
        pdf_path = Path(output_pdf_path)
        
        # Verify input file exists
        if not strip_path.exists():
            logger.error(f"Stitched strip not found: {strip_path}")
            return False
        
        # Create output directory if needed
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert image to PDF using img2pdf
        # img2pdf preserves image quality and creates efficient PDFs
        with open(pdf_path, "wb") as pdf_file:
            pdf_file.write(img2pdf.convert(str(strip_path)))
        
        # Verify PDF was created
        if pdf_path.exists():
            pdf_size = pdf_path.stat().st_size
            logger.info(f"✓ PDF generated: {pdf_path.name} ({pdf_size / 1024 / 1024:.2f} MB)")
            if manga_name and chapter_num:
                logger.info(f"  Series: {manga_name} | Chapter: {chapter_num}")
            return True
        else:
            logger.error(f"PDF generation failed - file not created: {pdf_path}")
            return False
            
    except Exception as e:
        logger.error(f"Error generating PDF from {strip_image_path}: {e}")
        return False


def generate_chapter_pdf(chapter_dir, output_base_dir="manga_pdfs"):
    """
    Generate PDF for a specific chapter from its stitched strip.
    Also copies the complete manga strip image to the output directory.
    
    Args:
        chapter_dir: Path to chapter directory containing 02_stitched/complete_manga_strip.png
        output_base_dir: Base directory for PDF outputs (default: 'manga_pdfs')
    
    Returns:
        str: Path to generated PDF if successful, None otherwise
    """
    try:
        import shutil
        
        chapter_path = Path(chapter_dir)
        
        # Extract manga info
        manga_series, chapter_num = extract_manga_info(chapter_dir)
        if not manga_series or not chapter_num:
            logger.error(f"Could not extract manga info from: {chapter_dir}")
            return None
        
        # Locate the complete stitched strip
        strip_path = chapter_path / "02_stitched" / "complete_manga_strip.png"
        if not strip_path.exists():
            logger.warning(f"No complete strip found for chapter {chapter_num} at {strip_path}")
            return None
        
        # Determine output paths
        # Structure: manga_pdfs/<series-name>/Chapter_<num>.pdf and Chapter_<num>_strip.png
        pdf_output_dir = Path(output_base_dir) / manga_series
        pdf_filename = f"Chapter_{chapter_num}.pdf"
        strip_filename = f"Chapter_{chapter_num}_strip.png"
        pdf_path = pdf_output_dir / pdf_filename
        strip_output_path = pdf_output_dir / strip_filename
        
        # Generate the PDF
        success = generate_pdf_from_strip(strip_path, pdf_path, manga_series, chapter_num)
        
        if success:
            # Also copy the complete manga strip to the output directory
            try:
                shutil.copy2(strip_path, strip_output_path)
                strip_size = strip_output_path.stat().st_size
                logger.info(f"✓ Strip image copied: {strip_output_path.name} ({strip_size / 1024 / 1024:.2f} MB)")
            except Exception as e:
                logger.warning(f"Failed to copy strip image (non-critical): {e}")
            
            return str(pdf_path)
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error in generate_chapter_pdf for {chapter_dir}: {e}")
        return None


def batch_generate_pdfs(manga_series_dir, output_base_dir="manga_pdfs"):
    """
    Generate PDFs for all chapters in a manga series directory.
    
    Args:
        manga_series_dir: Path to manga series directory (e.g., 'MangaFactory/tutorial-tower/')
        output_base_dir: Base directory for PDF outputs
    
    Returns:
        dict: Statistics including success_count, failed_count, total_count, pdf_paths
    """
    try:
        series_path = Path(manga_series_dir)
        manga_series_name = series_path.name
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Batch PDF Generation: {manga_series_name}")
        logger.info(f"{'='*60}")
        
        results = {
            'success_count': 0,
            'failed_count': 0,
            'total_count': 0,
            'pdf_paths': []
        }
        
        # Find all chapter directories (numeric folders)
        chapter_dirs = sorted([d for d in series_path.iterdir() 
                              if d.is_dir() and d.name.isdigit()])
        
        results['total_count'] = len(chapter_dirs)
        
        if not chapter_dirs:
            logger.warning(f"No chapter directories found in {manga_series_dir}")
            return results
        
        logger.info(f"Found {len(chapter_dirs)} chapters to process\n")
        
        # Process each chapter
        for chapter_dir in chapter_dirs:
            pdf_path = generate_chapter_pdf(chapter_dir, output_base_dir)
            if pdf_path:
                results['success_count'] += 1
                results['pdf_paths'].append(pdf_path)
            else:
                results['failed_count'] += 1
        
        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"PDF Generation Complete")
        logger.info(f"  Success: {results['success_count']} / {results['total_count']}")
        logger.info(f"  Failed:  {results['failed_count']}")
        logger.info(f"  Output:  {output_base_dir}/{manga_series_name}/")
        logger.info(f"{'='*60}\n")
        
        return results
        
    except Exception as e:
        logger.error(f"Error in batch_generate_pdfs for {manga_series_dir}: {e}")
        return {'success_count': 0, 'failed_count': 0, 'total_count': 0, 'pdf_paths': []}


if __name__ == "__main__":
    # Setup basic logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s"
    )
    
    # Example usage
    print("PDF Generator Module")
    print("Import this module to use PDF generation functions:")
    print("  - generate_chapter_pdf(chapter_dir)")
    print("  - batch_generate_pdfs(manga_series_dir)")
    print("  - generate_pdf_from_strip(strip_path, output_path)")
