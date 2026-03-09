#!/usr/bin/env python3
"""
Advanced Ad Blocker and Popup Handler for Manga Downloading
Handles multiple layers of intrusive ads with close buttons and redirects.
"""

import time
import logging
from typing import List, Optional, Tuple
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutError, NoSuchElementException, ElementClickInterceptedException

try:
    from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)


class AdBlocker:
    """
    Advanced ad blocker that handles multiple layers of intrusive ads.
    
    Features:
    - Detects and closes ad overlays with close buttons
    - Handles small close buttons in various positions
    - Manages redirect loops (clicking close -> redirect -> close again)
    - Closes popup windows and tabs
    - Retries multiple times to handle stubborn ads
    """
    
    # Common selectors for close buttons on ad overlays
    CLOSE_BUTTON_SELECTORS = [
        # X buttons (most common)
        'button.close', 'a.close', 'div.close', 'span.close',
        '[class*="close"]', '[id*="close"]',
        '[class*="Close"]', '[id*="Close"]',
        
        # X symbols and icons
        '[aria-label*="close" i]', '[aria-label*="Close" i]',
        '[title*="close" i]', '[title*="Close" i]',
        'button[class*="dismiss"]', 'a[class*="dismiss"]',
        
        # Common ad network close buttons
        '.fancybox-close', '.mfp-close', '.modal-close',
        '.popup-close', '.overlay-close', '.lightbox-close',
        
        # Ad-specific patterns
        '[onclick*="close"]', '[onclick*="Close"]',
        'div[style*="cursor: pointer"][style*="position: absolute"][style*="right"]',
        'a[href="#close"]', 'a[href="javascript:void(0)"]',
        
        # Generic patterns for X buttons in upper right
        'div[style*="z-index"][style*="position"][style*="top: 0"]',
        'button[style*="position: absolute"][style*="right"]',
        'span[style*="position: absolute"][style*="right"]',
        
        # Text-based close buttons
        'button:has-text("✕")', 'button:has-text("×")', 'button:has-text("✖")',
        'a:has-text("✕")', 'a:has-text("×")', 'a:has-text("✖")',
        'span:has-text("✕")', 'span:has-text("×")', 'span:has-text("✖")',
    ]
    
    # Selectors for ad overlays/containers
    AD_OVERLAY_SELECTORS = [
        'div[class*="overlay"]', 'div[class*="popup"]', 'div[class*="modal"]',
        'div[class*="ad-container"]', 'div[class*="advertisement"]',
        'div[id*="overlay"]', 'div[id*="popup"]', 'div[id*="modal"]',
        'div[style*="z-index: 999"]', 'div[style*="z-index: 9999"]',
        'div[style*="position: fixed"]',
        'iframe[src*="ad"]', 'iframe[id*="ad"]', 'iframe[class*="ad"]',
    ]
    
    def __init__(self, max_iterations: int = 5, wait_between_iterations: float = 2.0):
        """
        Initialize ad blocker.
        
        Args:
            max_iterations: Maximum number of times to try closing ads
            wait_between_iterations: Seconds to wait between close attempts
        """
        self.max_iterations = max_iterations
        self.wait_between_iterations = wait_between_iterations
        self.stats = {
            'ads_closed': 0,
            'popups_closed': 0,
            'iterations': 0
        }
    
    def handle_ads_playwright(self, page: Page, initial_url: str) -> bool:
        """
        Handle ads and popups on a Playwright page.
        
        Args:
            page: Playwright page instance
            initial_url: The URL we want to stay on (to detect redirects)
        
        Returns:
            True if ads were successfully handled, False otherwise
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available")
            return False
        
        logger.info("🚫 Starting ad blocking process...")
        
        for iteration in range(self.max_iterations):
            self.stats['iterations'] = iteration + 1
            logger.info(f"🔄 Ad blocking iteration {iteration + 1}/{self.max_iterations}")
            
            try:
                # Close any popup windows/tabs first
                closed_popups = self._close_popups_playwright(page)
                if closed_popups > 0:
                    logger.info(f"✅ Closed {closed_popups} popup windows/tabs")
                    self.stats['popups_closed'] += closed_popups
                
                # Wait a moment for page to settle
                page.wait_for_timeout(500)
                
                # Try to find and click close buttons
                closed_ads = self._close_ad_overlays_playwright(page)
                
                if closed_ads > 0:
                    logger.info(f"✅ Closed {closed_ads} ad overlays in iteration {iteration + 1}")
                    self.stats['ads_closed'] += closed_ads
                    
                    # Wait to see if page redirects or new ads appear
                    page.wait_for_timeout(int(self.wait_between_iterations * 1000))
                    
                    # Check if we got redirected back
                    current_url = page.url
                    if current_url != initial_url and not self._is_same_page(current_url, initial_url):
                        logger.warning(f"⚠️ Redirected to: {current_url}")
                        # Try to go back
                        try:
                            page.goto(initial_url, wait_until='domcontentloaded', timeout=10000)
                            logger.info("↩️ Navigated back to original page")
                        except Exception as e:
                            logger.warning(f"Could not navigate back: {e}")
                else:
                    # No more ads found, we're done
                    if iteration > 0:
                        logger.info(f"✅ No more ads detected after {iteration + 1} iterations")
                    break
                    
            except Exception as e:
                logger.error(f"Error in ad blocking iteration {iteration + 1}: {e}")
                break
        
        total_closed = self.stats['ads_closed'] + self.stats['popups_closed']
        if total_closed > 0:
            logger.info(f"🎯 Ad blocking complete: {self.stats['ads_closed']} overlays + {self.stats['popups_closed']} popups closed")
        else:
            logger.info("✅ No ads detected on page")
        
        return True
    
    def _close_ad_overlays_playwright(self, page: Page) -> int:
        """
        Find and close ad overlays by clicking their close buttons.
        
        Returns:
            Number of ads closed
        """
        closed_count = 0
        
        # Try each close button selector
        for selector in self.CLOSE_BUTTON_SELECTORS:
            try:
                # Find all matching elements
                close_buttons = page.locator(selector).all()
                
                for button in close_buttons:
                    try:
                        # Check if element is visible and clickable
                        if button.is_visible(timeout=500):
                            # Get position to see if it's in top-right area (common for X buttons)
                            box = button.bounding_box()
                            if box:
                                logger.debug(f"Found close button at position: {box}")
                            
                            # Scroll to element if needed
                            button.scroll_into_view_if_needed(timeout=1000)
                            
                            # Try to click
                            button.click(timeout=2000, force=True)
                            closed_count += 1
                            logger.info(f"🎯 Clicked close button: {selector}")
                            
                            # Wait a moment after clicking
                            page.wait_for_timeout(500)
                            
                    except Exception as e:
                        logger.debug(f"Could not click button with selector '{selector}': {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"No elements found for selector '{selector}': {e}")
                continue
        
        # Also try to remove overlay divs directly if close buttons don't work
        if closed_count == 0:
            closed_count += self._remove_overlays_directly_playwright(page)
        
        return closed_count
    
    def _remove_overlays_directly_playwright(self, page: Page) -> int:
        """
        Remove ad overlays by directly manipulating the DOM.
        
        Returns:
            Number of overlays removed
        """
        removed_count = 0
        
        try:
            # JavaScript to remove overlays
            removed = page.evaluate("""
                () => {
                    let count = 0;
                    
                    // Remove high z-index overlays
                    const overlays = document.querySelectorAll('div[style*="z-index"], div[class*="overlay"], div[class*="popup"], div[class*="modal"]');
                    overlays.forEach(el => {
                        const style = window.getComputedStyle(el);
                        const zIndex = parseInt(style.zIndex);
                        const position = style.position;
                        
                        // Remove if it has high z-index and covers the page
                        if ((zIndex > 100 && (position === 'fixed' || position === 'absolute')) ||
                            el.className.includes('overlay') ||
                            el.className.includes('popup') ||
                            el.className.includes('modal')) {
                            el.remove();
                            count++;
                        }
                    });
                    
                    // Remove body overflow hidden (often set by popups)
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                    
                    return count;
                }
            """)
            
            if removed > 0:
                removed_count = removed
                logger.info(f"🗑️ Removed {removed} overlays directly from DOM")
                
        except Exception as e:
            logger.debug(f"Could not remove overlays directly: {e}")
        
        return removed_count
    
    def _close_popups_playwright(self, page: Page) -> int:
        """
        Close popup windows and tabs.
        
        Returns:
            Number of popups closed
        """
        closed_count = 0
        
        try:
            context = page.context
            pages = context.pages
            
            # Close all pages except the main one
            for p in pages:
                if p != page:
                    try:
                        p.close()
                        closed_count += 1
                        logger.debug(f"Closed popup page: {p.url}")
                    except Exception as e:
                        logger.debug(f"Could not close page: {e}")
                        
        except Exception as e:
            logger.debug(f"Error closing popups: {e}")
        
        return closed_count
    
    def handle_ads_selenium(self, driver, initial_url: str) -> bool:
        """
        Handle ads and popups on a Selenium WebDriver.
        
        Args:
            driver: Selenium WebDriver instance
            initial_url: The URL we want to stay on (to detect redirects)
        
        Returns:
            True if ads were successfully handled, False otherwise
        """
        logger.info("🚫 Starting ad blocking process (Selenium)...")
        
        for iteration in range(self.max_iterations):
            self.stats['iterations'] = iteration + 1
            logger.info(f"🔄 Ad blocking iteration {iteration + 1}/{self.max_iterations}")
            
            try:
                # Close any popup windows/tabs first
                closed_popups = self._close_popups_selenium(driver)
                if closed_popups > 0:
                    logger.info(f"✅ Closed {closed_popups} popup windows/tabs")
                    self.stats['popups_closed'] += closed_popups
                
                # Wait a moment for page to settle
                time.sleep(0.5)
                
                # Try to find and click close buttons
                closed_ads = self._close_ad_overlays_selenium(driver)
                
                if closed_ads > 0:
                    logger.info(f"✅ Closed {closed_ads} ad overlays in iteration {iteration + 1}")
                    self.stats['ads_closed'] += closed_ads
                    
                    # Wait to see if page redirects or new ads appear
                    time.sleep(self.wait_between_iterations)
                    
                    # Check if we got redirected back
                    current_url = driver.current_url
                    if current_url != initial_url and not self._is_same_page(current_url, initial_url):
                        logger.warning(f"⚠️ Redirected to: {current_url}")
                        # Try to go back
                        try:
                            driver.get(initial_url)
                            time.sleep(2)
                            logger.info("↩️ Navigated back to original page")
                        except Exception as e:
                            logger.warning(f"Could not navigate back: {e}")
                else:
                    # No more ads found, we're done
                    if iteration > 0:
                        logger.info(f"✅ No more ads detected after {iteration + 1} iterations")
                    break
                    
            except Exception as e:
                logger.error(f"Error in ad blocking iteration {iteration + 1}: {e}")
                break
        
        total_closed = self.stats['ads_closed'] + self.stats['popups_closed']
        if total_closed > 0:
            logger.info(f"🎯 Ad blocking complete: {self.stats['ads_closed']} overlays + {self.stats['popups_closed']} popups closed")
        else:
            logger.info("✅ No ads detected on page")
        
        return True
    
    def _close_ad_overlays_selenium(self, driver) -> int:
        """
        Find and close ad overlays by clicking their close buttons (Selenium).
        
        Returns:
            Number of ads closed
        """
        closed_count = 0
        
        # Convert Playwright selectors to Selenium compatible ones
        selenium_selectors = [
            (By.CSS_SELECTOR, 'button.close'),
            (By.CSS_SELECTOR, 'a.close'),
            (By.CSS_SELECTOR, 'div.close'),
            (By.CSS_SELECTOR, 'span.close'),
            (By.CSS_SELECTOR, '[class*="close"]'),
            (By.CSS_SELECTOR, '[id*="close"]'),
            (By.CSS_SELECTOR, '[class*="Close"]'),
            (By.CSS_SELECTOR, '[id*="Close"]'),
            (By.CSS_SELECTOR, '[aria-label*="close"]'),
            (By.CSS_SELECTOR, '[title*="close"]'),
            (By.CSS_SELECTOR, 'button[class*="dismiss"]'),
            (By.CSS_SELECTOR, '.fancybox-close'),
            (By.CSS_SELECTOR, '.mfp-close'),
            (By.CSS_SELECTOR, '.modal-close'),
            (By.CSS_SELECTOR, '.popup-close'),
            (By.CSS_SELECTOR, '.overlay-close'),
            (By.XPATH, '//*[contains(text(), "✕")]'),
            (By.XPATH, '//*[contains(text(), "×")]'),
            (By.XPATH, '//*[contains(text(), "✖")]'),
        ]
        
        for by, selector in selenium_selectors:
            try:
                elements = driver.find_elements(by, selector)
                
                for element in elements:
                    try:
                        if element.is_displayed() and element.is_enabled():
                            # Try to click
                            element.click()
                            closed_count += 1
                            logger.info(f"🎯 Clicked close button: {selector}")
                            time.sleep(0.5)
                            
                    except (NoSuchElementException, ElementClickInterceptedException) as e:
                        logger.debug(f"Could not click element: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"No elements found for selector '{selector}': {e}")
                continue
        
        # Also try to remove overlays directly
        if closed_count == 0:
            closed_count += self._remove_overlays_directly_selenium(driver)
        
        return closed_count
    
    def _remove_overlays_directly_selenium(self, driver) -> int:
        """
        Remove ad overlays by directly manipulating the DOM (Selenium).
        
        Returns:
            Number of overlays removed
        """
        removed_count = 0
        
        try:
            removed = driver.execute_script("""
                let count = 0;
                
                // Remove high z-index overlays
                const overlays = document.querySelectorAll('div[style*="z-index"], div[class*="overlay"], div[class*="popup"], div[class*="modal"]');
                overlays.forEach(el => {
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex);
                    const position = style.position;
                    
                    // Remove if it has high z-index and covers the page
                    if ((zIndex > 100 && (position === 'fixed' || position === 'absolute')) ||
                        el.className.includes('overlay') ||
                        el.className.includes('popup') ||
                        el.className.includes('modal')) {
                        el.remove();
                        count++;
                    }
                });
                
                // Remove body overflow hidden
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
                
                return count;
            """)
            
            if removed > 0:
                removed_count = removed
                logger.info(f"🗑️ Removed {removed} overlays directly from DOM")
                
        except Exception as e:
            logger.debug(f"Could not remove overlays directly: {e}")
        
        return removed_count
    
    def _close_popups_selenium(self, driver) -> int:
        """
        Close popup windows and tabs (Selenium).
        
        Returns:
            Number of popups closed
        """
        closed_count = 0
        
        try:
            main_window = driver.current_window_handle
            all_windows = driver.window_handles
            
            # Close all windows except the main one
            for window in all_windows:
                if window != main_window:
                    try:
                        driver.switch_to.window(window)
                        driver.close()
                        closed_count += 1
                        logger.debug(f"Closed popup window")
                    except Exception as e:
                        logger.debug(f"Could not close window: {e}")
            
            # Switch back to main window
            driver.switch_to.window(main_window)
                        
        except Exception as e:
            logger.debug(f"Error closing popups: {e}")
        
        return closed_count
    
    def _is_same_page(self, url1: str, url2: str) -> bool:
        """
        Check if two URLs represent the same page (ignoring fragments and query params).
        """
        from urllib.parse import urlparse
        
        parsed1 = urlparse(url1)
        parsed2 = urlparse(url2)
        
        return (parsed1.scheme == parsed2.scheme and
                parsed1.netloc == parsed2.netloc and
                parsed1.path == parsed2.path)
    
    def get_stats(self) -> dict:
        """Get ad blocking statistics."""
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            'ads_closed': 0,
            'popups_closed': 0,
            'iterations': 0
        }


if __name__ == "__main__":
    # Test ad blocker
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("🚫 Ad Blocker Test")
    print("This module provides advanced ad blocking for manga downloaders")
    print("\nFeatures:")
    print("- Handles multiple layers of ad overlays")
    print("- Clicks small close buttons (especially in upper right)")
    print("- Manages redirect loops")
    print("- Closes popup windows/tabs")
    print("- Retries automatically for stubborn ads")
