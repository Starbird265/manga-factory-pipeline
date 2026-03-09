#!/usr/bin/env python3
"""
Enhanced Smart Manga Downloader with Multi-Layer Cloudflare Bypass
Supports:
1. Playwright with stealth (primary, fast)
2. Undetected ChromeDriver (fallback for stubborn sites)
3. Automatic challenge detection and handling
"""

import time
import random
import logging
import os
from typing import Dict, List, Optional
from pathlib import Path
import re
import requests
from urllib.parse import urljoin, urlparse

# BeautifulSoup (optional — used only for HTML scraper helper)
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None

from website_database import WebsiteDatabase
from html_scraper import HTMLScraper
from cloudflare_handler import CloudflareHandler
from stealth_config import StealthConfig
from cookie_manager import CookieManager

# Ad blocker (optional — may not exist in all installs)
try:
    from ad_blocker import AdBlocker
    AD_BLOCKER_AVAILABLE = True
except ImportError:
    AdBlocker = None
    AD_BLOCKER_AVAILABLE = False

# Playwright imports
try:
    from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None

# Playwright Stealth (optional enhancement)
try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None

# Undetected ChromeDriver + Selenium (optional — heavy dependency)
try:
    import undetected_chromedriver as uc
    # Lazy-import selenium sub-modules only when UC is available
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        By = None
        WebDriverWait = None
        EC = None
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    uc = None
    By = None
    WebDriverWait = None
    EC = None

logger = logging.getLogger(__name__)


class EnhancedSmartDownloader:
    """
    Smart manga downloader with multi-layer Cloudflare bypass.
    
    Strategy:
    1. Try Playwright with stealth (fast, works for most sites)
    2. If Cloudflare detected, wait for auto-resolution
    3. If still blocked, fall back to Undetected ChromeDriver
    4. If all fails, return error with helpful message
    """
    
    def __init__(self, db: Optional[WebsiteDatabase] = None,
                 headless: bool = True,
                 min_delay: float = 1.0,
                 max_delay: float = 3.0):
        """
        Initialize enhanced smart downloader.
        
        Args:
            db: WebsiteDatabase instance
            headless: Run browser in headless mode
            min_delay: Minimum delay between actions (seconds)
            max_delay: Maximum delay between actions (seconds)
        """
        self.db = db if db else WebsiteDatabase()
        self.scraper = HTMLScraper(self.db)
        self.headless = headless
        self.min_delay = min_delay
        self.max_delay = max_delay
        
        # Playwright resources
        self.playwright = None
        self.browser = None
        self.page = None
        
        # Selenium resources
        self.uc_driver = None
        
        # Ad blocker for handling intrusive popups and overlays
        self.ad_blocker = AdBlocker(max_iterations=5, wait_between_iterations=2.0)
        
        # Stealth and cookie management
        self.cookie_manager = CookieManager()
        self.use_cookies = True
        
        # Mobile user agents (better for bypassing Cloudflare)
        self.mobile_user_agents = [
            'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        ]
        
        # Desktop user agents (fallback)
        self.desktop_user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
        # Use desktop by default for better compatibility on macOS
        self.use_mobile = False
        
        # Request interception for image capture
        self.intercepted_images = []
        self.use_request_interception = True
        
        # Stats
        self.stats = {
            'playwright_success': 0,
            'uc_fallback_success': 0,
            'cloudflare_challenges': 0,
            'total_attempts': 0
        }
    
    def human_delay(self, custom_min: Optional[float] = None, 
                   custom_max: Optional[float] = None):
        """Add human-like delay between actions."""
        min_d = custom_min if custom_min is not None else self.min_delay
        max_d = custom_max if custom_max is not None else self.max_delay
        delay = random.uniform(min_d, max_d)
        time.sleep(delay)
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent (mobile preferred)."""
        agents = self.mobile_user_agents if self.use_mobile else self.desktop_user_agents
        return random.choice(agents)
    
    def setup_playwright_browser(self) -> bool:
        """
        Setup Playwright browser with mobile emulation and stealth mode.
        
        Returns:
            True if successful, False if Playwright unavailable
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available. Install with: pip install playwright playwright-stealth && playwright install chromium")
            return False
        
        try:
            self.playwright = sync_playwright().start()
            
            # Launch with anti-detection arguments
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-notifications',
                    '--disable-extensions',
                    '--window-position=0,0'
                ]
            )
            
            # Mobile device emulation (better for Cloudflare bypass)
            if self.use_mobile:
                # iPhone 13 Pro viewport
                viewport = {
                    'width': 390,
                    'height': 844
                }
                device_scale_factor = 3
                is_mobile = True
                has_touch = True
                logger.info("📱 Using mobile device emulation (iPhone 13 Pro)")
            else:
                # Desktop viewport
                viewport = {
                    'width': random.randint(1280, 1920),
                    'height': random.randint(720, 1080)
                }
                device_scale_factor = 1
                is_mobile = False
                has_touch = False
                logger.info("💻 Using desktop browser")
            
            # Create page with device emulation
            self.page = self.browser.new_page(
                user_agent=self._get_random_user_agent(),
                viewport=viewport,
                device_scale_factor=device_scale_factor,
                is_mobile=is_mobile,
                has_touch=has_touch
            )
            
            # Apply stealth patches
            if stealth_sync:
                stealth_sync(self.page)
                logger.info("✅ Playwright browser initialized with stealth mode (playwright-stealth)")
            else:
                logger.info("⚠️  playwright-stealth not available, using custom stealth")
            
            # Apply custom stealth configuration
            StealthConfig.inject_stealth_scripts(self.page, mobile=self.use_mobile)
            logger.info("✅ Custom stealth scripts injected")
            
            # Setup request interception for image capture
            if self.use_request_interception:
                self._setup_request_interception()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Playwright browser: {e}")
            return False
    
    def setup_uc_browser(self) -> bool:
        """
        Setup Undetected ChromeDriver as fallback.
        
        Returns:
            True if successful, False if UC unavailable
        """
        if not UC_AVAILABLE:
            logger.warning("Undetected ChromeDriver not available. Install with: pip install undetected-chromedriver")
            return False
        
        try:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(f'--user-agent={self._get_random_user_agent()}')
            
            self.uc_driver = uc.Chrome(options=options, use_subprocess=True)
            logger.info("✅ Undetected ChromeDriver initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Undetected ChromeDriver: {e}")
            return False
    
    def download_manga_automated(self, manga_name: str, chapter: int, 
                                website: Optional[str] = None,
                                chapter_url: Optional[str] = None) -> Dict:
        """
        Automated download flow with multi-layer Cloudflare bypass.
        
        Args:
            manga_name: Name of the manga
            chapter: Chapter number
            website: Website domain (optional)
            chapter_url: Direct URL to chapter (bypasses search)
        
        Returns:
            Download result dictionary
        """
        self.stats['total_attempts'] += 1
        
        result = {
            'success': False,
            'chapter_url': chapter_url,
            'image_urls': [],
            'method': 'unknown',
            'cloudflare_encountered': False
        }
        
        # Try Playwright first (Layer 1)
        logger.info("🚀 Attempting download with Playwright + Stealth...")
        playwright_result = self._try_playwright_download(
            manga_name, chapter, website, chapter_url
        )
        
        if playwright_result['success']:
            self.stats['playwright_success'] += 1
            return playwright_result
        
        # If Cloudflare was encountered, try UC fallback (Layer 2)
        if playwright_result.get('cloudflare_encountered'):
            logger.warning("⚠️ Cloudflare challenge detected, trying Undetected ChromeDriver fallback...")
            self.stats['cloudflare_challenges'] += 1
            
            uc_result = self._try_uc_download(
                manga_name, chapter, website, chapter_url
            )
            
            if uc_result['success']:
                self.stats['uc_fallback_success'] += 1
                return uc_result
        
        # All methods failed
        logger.error("❌ All download methods failed")
        return result
    
    def _try_playwright_download(self, manga_name: str, chapter: int,
                                 website: Optional[str],
                                 chapter_url: Optional[str]) -> Dict:
        """Try download using Playwright with stealth."""
        result = {
            'success': False,
            'chapter_url': chapter_url,
            'image_urls': [],
            'method': 'playwright',
            'cloudflare_encountered': False
        }
        
        if not self.page:
            if not self.setup_playwright_browser():
                return result
        
        try:
            # Try loading cookies first
            if chapter_url and self.use_cookies:
                cookies_loaded = self.cookie_manager.load_cookies_playwright(self.page, chapter_url)
                if cookies_loaded:
                    logger.info("🍪 Loaded saved Cloudflare cookies")
            
            # Navigate to chapter URL
            if chapter_url:
                logger.info(f"Navigating to: {chapter_url}")
                self.page.goto(chapter_url, timeout=60000, wait_until='domcontentloaded')
            else:
                # Search and navigate logic (simplified for now)
                logger.warning("Search functionality not yet implemented, need direct URL")
                return result
            
            # Simulate human behavior
            StealthConfig.simulate_human_behavior(self.page)
            self.human_delay()
            
            # Check for Cloudflare challenge
            if CloudflareHandler.is_challenge_page_playwright(self.page):
                logger.warning("🛡️ Cloudflare challenge detected!")
                result['cloudflare_encountered'] = True
                
                # Wait for auto-resolution with longer timeout
                if CloudflareHandler.wait_for_challenge_resolution_playwright(self.page, timeout=60):
                    logger.info("✅ Cloudflare challenge resolved!")
                    
                    # Save cookies for future use
                    if chapter_url and self.use_cookies:
                        self.cookie_manager.save_cookies_playwright(self.page, chapter_url)
                    
                    # Wait longer for page to fully load after Cloudflare
                    logger.info("⏳ Waiting for page to fully load after Cloudflare...")
                    self.page.wait_for_timeout(8000)
                else:
                    logger.warning("⚠️ Cloudflare challenge not resolved, will try fallback")
                    return result
            
            # HANDLE ADS AND POPUPS - This is crucial for sites with intrusive ads!
            logger.info("🚫 Checking for and handling ads/popups...")
            try:
                initial_url = self.page.url
                self.ad_blocker.handle_ads_playwright(self.page, initial_url)
                ad_stats = self.ad_blocker.get_stats()
                if ad_stats['ads_closed'] > 0 or ad_stats['popups_closed'] > 0:
                    logger.info(f"🎯 Ad blocking complete: {ad_stats}")
                # Reset stats for next download
                self.ad_blocker.reset_stats()
            except Exception as e:
                logger.warning(f"Ad blocking encountered an error (continuing anyway): {e}")
            
            # Scroll to load lazy images
            logger.info("📜 Scrolling to load all images...")
            try:
                self._scroll_page_playwright()
            except Exception as e:
                logger.warning(f"Scroll failed (may be normal if window closing): {e}")
            
            # Extract image URLs - prioritize intercepted images
            logger.info("🖼️ Extracting image URLs...")
            
            # Combine intercepted images and DOM extraction
            image_urls = []
            if self.intercepted_images:
                image_urls.extend(self.intercepted_images)
            
            # Always try DOM extraction as well to be sure
            image_urls.extend(self._extract_images_playwright())
            
            if image_urls:
                # Store only valid images and filter duplicates
                seen = set()
                valid_urls = []
                for url in image_urls:
                    if url not in seen and self._is_valid_image_url(url):
                        valid_urls.append(url)
                        seen.add(url)
                
                result['success'] = len(valid_urls) > 0
                result['image_urls'] = valid_urls
                result['chapter_url'] = self.page.url
                logger.info(f"✅ Found {len(valid_urls)} valid images via Playwright")
            else:
                logger.warning("⚠️ No images found")
                # Take diagnostic screenshot
                try:
                    self.page.screenshot(path='error_playwright.png')
                    logger.info("📸 Diagnostic screenshot saved as error_playwright.png")
                except:
                    pass
            
        except Exception as e:
            logger.error(f"Playwright download error: {e}")
        
        return result
    
    def _try_uc_download(self, manga_name: str, chapter: int,
                        website: Optional[str],
                        chapter_url: Optional[str]) -> Dict:
        """Try download using Undetected ChromeDriver."""
        result = {
            'success': False,
            'chapter_url': chapter_url,
            'image_urls': [],
            'method': 'undetected_chrome',
            'cloudflare_encountered': False
        }
        
        if not self.uc_driver:
            if not self.setup_uc_browser():
                return result
        
        try:
            # Try loading cookies first
            if chapter_url and self.use_cookies:
                cookies_loaded = self.cookie_manager.load_cookies_selenium(self.uc_driver, chapter_url)
                if cookies_loaded:
                    logger.info("🍪 Loaded saved Cloudflare cookies (UC)")
                    # Refresh page with cookies
                    self.uc_driver.refresh()
                    time.sleep(2)
            
            # Navigate to chapter URL
            if not self.cookie_manager.load_cookies_selenium(self.uc_driver, chapter_url):
                # Only do initial navigation if we didn't load cookies
                if chapter_url:
                    logger.info(f"UC: Navigating to: {chapter_url}")
                    self.uc_driver.get(chapter_url)
                else:
                    logger.warning("Search functionality not yet implemented, need direct URL")
                    return result
            
            time.sleep(3)
            
            # Check for Cloudflare challenge
            if CloudflareHandler.is_challenge_page_selenium(self.uc_driver):
                logger.warning("🛡️ Cloudflare challenge detected (UC)!")
                result['cloudflare_encountered'] = True
                
                # Wait for auto-resolution (UC is better at this)
                if CloudflareHandler.wait_for_challenge_resolution_selenium(self.uc_driver, timeout=90):
                    logger.info("✅ Cloudflare challenge resolved (UC)!")
                    
                    # Save cookies for future use
                    if chapter_url and self.use_cookies:
                        self.cookie_manager.save_cookies_selenium(self.uc_driver, chapter_url)
                    
                    # IMPORTANT: Wait for page to fully load after Cloudflare
                    logger.info("⏳ Waiting for page to fully load...")
                    time.sleep(15)  # Give page time to load content (increased from 5s)
                else:
                    logger.error("❌ Cloudflare challenge not resolved even with UC")
                    return result
            else:
                # No Cloudflare, but still wait a bit for page load
                time.sleep(2)
            
            # HANDLE ADS AND POPUPS - This is crucial for sites with intrusive ads!
            logger.info("🚫 Checking for and handling ads/popups (UC)...")
            try:
                initial_url = self.uc_driver.current_url
                self.ad_blocker.handle_ads_selenium(self.uc_driver, initial_url)
                ad_stats = self.ad_blocker.get_stats()
                if ad_stats['ads_closed'] > 0 or ad_stats['popups_closed'] > 0:
                    logger.info(f"🎯 Ad blocking complete: {ad_stats}")
                # Reset stats for next download
                self.ad_blocker.reset_stats()
            except Exception as e:
                logger.warning(f"Ad blocking encountered an error (continuing anyway): {e}")
            
            # Scroll to load lazy images
            logger.info("📜 Scrolling to load all images (UC)...")
            self._scroll_page_selenium()
            
            # Extract image URLs
            logger.info("🖼️ Extracting image URLs (UC)...")
            image_urls = self._extract_images_selenium()
            
            if image_urls:
                result['success'] = True
                result['image_urls'] = image_urls
                result['chapter_url'] = self.uc_driver.current_url
                logger.info(f"✅ Found {len(image_urls)} images via UC")
            else:
                logger.warning("⚠️ No images found (UC)")
            
        except Exception as e:
            logger.error(f"UC download error: {e}")
        
        return result
    
    def _setup_request_interception(self):
        """Setup request interception to capture image URLs during page load."""
        try:
            def handle_request(request):
                url = request.url
                # Check if it's an image request
                if self._is_valid_image_url(url):
                    if url not in self.intercepted_images:
                        self.intercepted_images.append(url)
                        logger.debug(f"📸 Intercepted image: {url}")
            
            self.page.on('request', handle_request)
            logger.info("✅ Request interception enabled")
        except Exception as e:
            logger.warning(f"Failed to setup request interception: {e}")
    
    def _scroll_page_playwright(self):
        """Scroll page to trigger lazy loading with human-like behavior (Playwright)."""
        try:
            # Natural scrolling with randomization
            self.page.evaluate(f"""
                async () => {{
                    await new Promise((resolve) => {{
                        let totalHeight = 0;
                        const scrollHeight = document.body.scrollHeight;
                        const viewport = window.innerHeight;
                        
                        const scroll = () => {{
                            // Random scroll distance (more human-like)
                            const distance = {random.randint(150, 300)};
                            const randomDelay = {random.randint(80, 150)};
                            
                            window.scrollBy({{
                                top: distance,
                                behavior: '{random.choice(['smooth', 'auto'])}'
                            }});
                            
                            totalHeight += distance;
                            
                            if (totalHeight >= scrollHeight - viewport) {{
                                resolve();
                            }} else {{
                                setTimeout(scroll, randomDelay + Math.random() * 50);
                            }}
                        }};
                        
                        scroll();
                    }});
                }}
            """)
            
            # Random pause after scrolling down
            self.page.wait_for_timeout(random.randint(1500, 2500))
            
            # Sometimes scroll back up a bit (human checking something)
            if random.random() > 0.6:
                self.page.evaluate(f"""
                    window.scrollBy({{
                        top: -{random.randint(100, 400)},
                        behavior: 'smooth'
                    }})
                """)
                self.page.wait_for_timeout(random.randint(300, 800))
            
            # Scroll back to top with smooth behavior
            self.page.evaluate("""
                window.scrollTo({top: 0, behavior: 'smooth'})
            """)
            self.page.wait_for_timeout(random.randint(400, 800))
            
            # Final scroll to bottom
            self.page.evaluate("""
                window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})
            """)
            self.page.wait_for_timeout(random.randint(1500, 2500))
            
        except Exception as e:
            logger.warning(f"Scroll error: {e}")
    
    def _scroll_page_selenium(self):
        """Scroll page to trigger lazy loading with human-like behavior (Selenium)."""
        try:
            # Get total height
            total_height = self.uc_driver.execute_script("return document.body.scrollHeight")
            
            # Scroll down in irregular chunks (more human-like)
            current_position = 0
            while current_position < total_height:
                # Random scroll distance
                scroll_amount = random.randint(150, 350)
                current_position += scroll_amount
                
                # Smooth scroll with random behavior choice
                if random.random() > 0.5:
                    self.uc_driver.execute_script(f"""
                        window.scrollTo({{
                            top: {min(current_position, total_height)},
                            behavior: 'smooth'
                        }})
                    """)
                else:
                    self.uc_driver.execute_script(f"window.scrollTo(0, {min(current_position, total_height)})")
                
                # Random pause (human reading/looking)
                time.sleep(random.uniform(0.08, 0.18))
            
            # Pause at bottom (human looking at content)
            time.sleep(random.uniform(1.5, 2.5))
            
            # Sometimes scroll back up a bit (human checking something)
            if random.random() > 0.5:
                scroll_back = random.randint(100, 500)
                self.uc_driver.execute_script(f"""
                    window.scrollBy({{
                        top: -{scroll_back},
                        behavior: 'smooth'
                    }})
                """)
                time.sleep(random.uniform(0.4, 0.9))
            
            # Scroll back to top
            self.uc_driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")
            time.sleep(random.uniform(0.6, 1.2))
            
            # Final scroll to bottom
            self.uc_driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
            time.sleep(random.uniform(1.8, 2.8))
            
        except Exception as e:
            logger.warning(f"Scroll error (Selenium): {e}")
    
    def _extract_images_playwright(self) -> List[str]:
        """Extract image URLs from page (Playwright)."""
        image_urls = []
        
        try:
            # Try multiple selectors
            selectors = [
                'img[src*="chapter"]',
                'img[src*="page"]',
                'img[src*="manga"]',
                'img.wp-manga-chapter-img',
                '.reading-content img',
                '#chapter-content img',
                '.chapter-images img',
                'img[data-src]',
                'img'
            ]
            
            for selector in selectors:
                try:
                    images = self.page.locator(selector).all()
                    logger.info(f"Selector '{selector}' found {len(images)} potential images")
                    for img in images:
                        # Prioritize data-src for lazy-loaded images
                        src = (img.get_attribute('data-src') or 
                              img.get_attribute('data-lazy-src') or 
                              img.get_attribute('data-full-url') or 
                              img.get_attribute('src'))
                        
                        if src and self._is_valid_image_url(src):
                            if not src.startswith('http'):
                                src = urljoin(self.page.url, src)
                            if src not in image_urls:
                                image_urls.append(src)
                        elif src:
                            logger.debug(f"Filtered out URL: {src}")
                except Exception as e:
                    logger.debug(f"Error with selector '{selector}': {e}")
                    continue
                
                if image_urls:
                    logger.info(f"Successfully found images using selector: {selector}")
                    break
            
        except Exception as e:
            logger.error(f"Image extraction error: {e}")
        
        return image_urls
    
    def _extract_images_selenium(self) -> List[str]:
        """Extract image URLs from page (Selenium)."""
        image_urls = []
        
        try:
            # Find all images
            images = self.uc_driver.find_elements(By.TAG_NAME, 'img')
            
            for img in images:
                # Prioritize data-src for lazy-loaded images
                src = (img.get_attribute('data-src') or 
                      img.get_attribute('data-lazy-src') or 
                      img.get_attribute('data-full-url') or 
                      img.get_attribute('src'))
                
                if src and self._is_valid_image_url(src):
                    if not src.startswith('http'):
                        src = urljoin(self.uc_driver.current_url, src)
                    if src not in image_urls:
                        image_urls.append(src)
            
        except Exception as e:
            logger.error(f"Image extraction error (Selenium): {e}")
        
        return image_urls
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL is likely a manga page image."""
        if not url:
            return False
        
        url_lower = url.lower()
        
        # Exclude common non-manga images
        exclude_keywords = [
            'logo', 'avatar', 'icon', 'banner', 'ad', 'button', 'background',
            'zeropixel', 'pixel', 'tracking', 'spacer', 'transparent'
        ]
        if any(keyword in url_lower for keyword in exclude_keywords):
            return False
        
        # Must be an image format
        if not any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
            # Check if it's a data URL or has image-like path
            if not url.startswith('data:image') and 'image' not in url_lower:
                return False
        
        return True
    
    def close_browser(self):
        """Close all browser instances."""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            if self.uc_driver:
                self.uc_driver.quit()
            logger.info("Browser closed")
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")
    
    def close(self):
        """Close all resources."""
        self.close_browser()
        if self.scraper:
            self.scraper.close()
    
    def get_stats(self) -> Dict:
        """Get download statistics."""
        return {
            **self.stats,
            'success_rate': f"{(self.stats['playwright_success'] + self.stats['uc_fallback_success']) / max(1, self.stats['total_attempts']) * 100:.1f}%",
            'cloudflare_rate': f"{self.stats['cloudflare_challenges'] / max(1, self.stats['total_attempts']) * 100:.1f}%"
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Convenience function
def download_manga(manga_name: str, chapter: int, 
                  website: Optional[str] = None,
                  headless: bool = True,
                  chapter_url: Optional[str] = None) -> Dict:
    """
    Quick manga download function with Cloudflare bypass.
    
    Args:
        manga_name: Name of the manga
        chapter: Chapter number
        website: Website domain (optional)
        headless: Run browser in headless mode
        chapter_url: Direct URL to the chapter (bypasses search)
    
    Returns:
        Download result dictionary
    """
    with EnhancedSmartDownloader(headless=headless) as downloader:
        result = downloader.download_manga_automated(manga_name, chapter, website, chapter_url)
        stats = downloader.get_stats()
        logger.info(f"📊 Download stats: {stats}")
        return result


if __name__ == "__main__":
    # Test enhanced downloader
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("🚀 Testing Enhanced Smart Downloader with Cloudflare Bypass...")
    print(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")
    print(f"Undetected Chrome available: {UC_AVAILABLE}\n")
    
    if not PLAYWRIGHT_AVAILABLE and not UC_AVAILABLE:
        print("⚠️  No browser automation available!")
        print("Install with: pip install playwright playwright-stealth undetected-chromedriver")
        print("Then run: playwright install chromium")
    else:
        # Test with a chapter URL (replace with actual URL)
        test_url = input("Enter chapter URL to test (or press Enter to skip): ").strip()
        
        if test_url:
            result = download_manga(
                manga_name="Test Manga",
                chapter=1,
                chapter_url=test_url,
                headless=False  # Show browser for testing
            )
            
            print(f"\n📊 Download Result:")
            print(f"  Success: {result['success']}")
            print(f"  Method: {result['method']}")
            print(f"  Cloudflare encountered: {result.get('cloudflare_encountered', False)}")
            print(f"  Images found: {len(result.get('image_urls', []))}")
            
            if result['success'] and result.get('image_urls'):
                print(f"\n🖼️ First 3 image URLs:")
                for url in result['image_urls'][:3]:
                    print(f"    {url}")
        else:
            print("Skipping test (no URL provided)")
    
    print("\n✅ Test completed!")
