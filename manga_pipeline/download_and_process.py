#!/usr/bin/env python3
"""
Complete pipeline: Download chapter using UC + Process with manga_factory_enhanced
"""
import sys
import os
import time
import random
import requests
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from website_database import WebsiteDatabase

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import popup closer for handling intrusive ads
from popup_closer import PopupCloser

# Import human behavior for natural interactions
try:
    from human_behavior import HumanBehavior
    HUMAN_BEHAVIOR_AVAILABLE = True
except ImportError:
    HUMAN_BEHAVIOR_AVAILABLE = False
    HumanBehavior = None

def download_chapter_with_uc(manga_name, chapter_num, chapter_url, output_dir):
    """Download chapter images using UC"""
    print(f"🚀 Starting UC download for {manga_name} Chapter {chapter_num}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize UC
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = uc.Chrome(options=options, use_subprocess=True)
    
    try:
        # Navigate
        print(f"📍 Navigating to: {chapter_url}")
        driver.get(chapter_url)
        
        # Wait for Cloudflare
        print("⏳ Waiting 60 seconds for Cloudflare...")
        time.sleep(60)
        
        # CLOSE POPUPS AND AD OVERLAYS
        print("🚫 Closing popups and ad overlays...")
        popup_closer = PopupCloser(max_attempts=5, wait_seconds=2.0)
        popup_stats = popup_closer.close_all_popups_selenium(driver, chapter_url)
        
        if popup_stats['popups_closed'] > 0 or popup_stats['overlays_closed'] > 0:
            print(f"🎯 Closed {popup_stats['popups_closed']} popups + {popup_stats['overlays_closed']} overlays")
        
        # HUMAN-LIKE SCROLLING to load lazy images
        print("📜 Scrolling like a human to load all images...")
        
        if HUMAN_BEHAVIOR_AVAILABLE:
            # Initialize human behavior
            human = HumanBehavior(
                min_delay=0.2,
                max_delay=0.8,
                movement_speed='medium'
            )
            
            # Natural page viewing pattern
            print("  👀 Viewing page naturally...")
            
            # Initial pause (human looking at page)
            human.read_pause(1.0, 2.5)
            
            # Scroll down slowly (human reading/scanning)
            for _ in range(random.randint(3, 5)):
                human.human_scroll(driver, 'down', 
                                 amount=random.randint(200, 600), 
                                 smooth=True)
                # Random pause (reading content)
                human.read_pause(0.5, 1.5)
            
            # Scroll back up a bit (checking something)
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
            
            # Final scroll to bottom to ensure everything loaded
            human.human_scroll(driver, 'down', 
                             amount=random.randint(1500, 3000), 
                             smooth=True)
            
            # Final pause (human satisfied, ready to proceed)
            human.read_pause(1.0, 2.0)
            
            print("  ✅ Natural scrolling complete")
        else:
            # Fallback to less robotic scrolling
            print("  ⚠️ Human behavior not available, using basic scrolling")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(random.uniform(4, 6))
            driver.execute_script("window.scrollTo(0, 0)")
            time.sleep(random.uniform(1.5, 2.5))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(random.uniform(4, 6))
        
        # Extract images (site-aware using WebsiteDatabase)
        print("🖼️ Extracting images...")
        site_db = WebsiteDatabase()
        site_config = site_db.get_site_config(chapter_url)
        selectors = site_config.get("image_selectors", [])
        lazy_attr = site_config.get("lazy_attr", None)
        cdn_hint = site_config.get("cdn")

        image_elements = []
        if selectors:
            for selector in selectors:
                try:
                    found = driver.find_elements(By.CSS_SELECTOR, selector)
                    if found:
                        image_elements.extend(found)
                except Exception:
                    continue
        else:
            image_elements = driver.find_elements(By.TAG_NAME, "img")

        # De-duplicate elements
        seen_ids = set()
        unique_images = []
        for el in image_elements:
            el_id = id(el)
            if el_id not in seen_ids:
                seen_ids.add(el_id)
                unique_images.append(el)

        # First pass: collect all candidate URLs (unfiltered)
        all_image_urls = []
        for img in unique_images:
            src = None
            if lazy_attr:
                src = img.get_attribute(lazy_attr)
            if not src:
                src = (img.get_attribute("data-src")
                       or img.get_attribute("data-lazy-src")
                       or img.get_attribute("data-original")
                       or img.get_attribute("data-full-url")
                       or img.get_attribute("src"))

            if not src or not src.startswith("http"):
                continue

            all_image_urls.append(src)

        # Optional CDN/domain hint filtering (keeps panels, drops most ads)
        image_urls = []
        if cdn_hint:
            image_urls = [u for u in all_image_urls if cdn_hint in u]
            # If filtering removed everything, fall back to unfiltered candidates
            if not image_urls:
                print("⚠️ CDN hint filter returned 0 images, falling back to all candidates")
                image_urls = list(all_image_urls)
        else:
            image_urls = list(all_image_urls)
        
        print(f"✅ Found {len(image_urls)} manga panel images")
        
        # Download images
        print(f"⬇️  Downloading images to {output_dir}...")
        downloaded_files = []
        
        for i, url in enumerate(image_urls, 1):
            try:
                filename = f"page_{i:03d}.jpg"
                filepath = os.path.join(output_dir, filename)
                
                print(f"  [{i}/{len(image_urls)}] {filename}")
                
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                downloaded_files.append(filepath)
                time.sleep(0.5)  # Be polite
                
            except Exception as e:
                print(f"  ⚠️  Failed to download {url}: {e}")
        
        print(f"\n✅ Downloaded {len(downloaded_files)} images!")
        return downloaded_files
        
    finally:
        driver.quit()

def run_manga_pipeline(chapter_path, manga_name, chapter_num):
    """Run the full manga_factory_enhanced pipeline"""
    print(f"\n{'='*70}")
    print("RUNNING FULL MANGA FACTORY PIPELINE")
    print(f"{'='*70}\n")
    
    # Build the command
    cmd = [
        sys.executable,
        'manga_pipeline/manga_factory_enhanced.py',
        '--chapter-path', chapter_path,
        '--manga-name', manga_name,
        '--chapter-number', str(chapter_num),
        '--detect-panels',
        '--generate-script',
        '--stitch-panels'
    ]
    
    print(f"Running: {' '.join(cmd)}\n")
    
    import subprocess
    result = subprocess.run(cmd, cwd='/Users/gauravsingh/Desktop/manga_factory_project')
    
    return result.returncode == 0

def main():
    # Configuration
    manga_name = "The Hammer"
    chapter_num = 1
    chapter_url = "https://www.topmanhua.fan/manhua/the-hammer/chapter-1"
    
    # Create output directory
    base_dir = Path('/Users/gauravsingh/Desktop/manga_factory_project/MangaFactory')
    chapter_dir = base_dir / manga_name / f"Chapter_{chapter_num}"
    raw_images_dir = chapter_dir / "01_raw_images"
    
    print(f"📁 Output directory: {chapter_dir}")
    
    # Step 1: Download images
    downloaded_files = download_chapter_with_uc(
        manga_name, 
        chapter_num, 
        chapter_url, 
        str(raw_images_dir)
    )
    
    if not downloaded_files:
        print("❌ No images downloaded!")
        return False
    
    # Step 2: Run full pipeline
    success = run_manga_pipeline(str(chapter_dir), manga_name, chapter_num)
    
    if success:
        print(f"\n{'='*70}")
        print("✅ COMPLETE SUCCESS!")
        print(f"{'='*70}")
        print(f"\n📁 Check results in: {chapter_dir}")
        print(f"\nProcessed outputs:")
        print(f"  • 02_panels/        - Detected panels")
        print(f"  • 03_stitched/      - Stitched long strip")
        print(f"  • 04_output/script/ - Generated script")
    else:
        print("\n⚠️  Pipeline completed with warnings - check output above")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
