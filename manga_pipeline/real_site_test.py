#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path

# Ensure we can import from the current directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_real_site():
    from manga_factory_enhanced import EnhancedMangaFactory
    
    # URL from user log
    url = "https://manhwaclan.com/manga/how-to-live-as-an-illegal-healer/chapter-1/"
    
    # Use a temporary output directory
    output_dir = "real_test_output"
    if os.path.exists(output_dir):
        import shutil
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info(f"--- Starting real site test on: {url} ---")
    
    try:
        # Initialize factory
        # We pass the output dir and some dummy values for name/num as it will be inferred or set
        factory = EnhancedMangaFactory(output_dir)
        
        # Correct signature: download_chapter(url, source_hint=None)
        result = factory.download_chapter(
            url=url,
            source_hint="manhwaclan"
        )
        
        if result:
            logger.info("✅ SUCCESS: Chapter downloaded successfully!")
            logger.info(f"   Images found: {factory.stats['downloaded_images']}")
            logger.info(f"   Output directory: {factory.chapter_dir}")
        else:
            logger.error("❌ FAILED: Chapter download failed.")
            
        factory.cleanup()
        
    except Exception as e:
        logger.error(f"❌ ERROR: Test crashed with: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_real_site()
