#!/usr/bin/env python3
"""
Popup and Ad Overlay Closer for Manga Downloads
Automatically closes intrusive popups and ad overlays without blocking ads from loading.

This module does NOT block ads - it lets them load normally (to keep the website working),
but automatically closes popup windows and clicks X buttons on overlays that block content.
"""

import time
import logging
from typing import Optional

# Import human behavior simulator for natural interactions
try:
    from human_behavior import HumanBehavior
    HUMAN_BEHAVIOR_AVAILABLE = True
except ImportError:
    HUMAN_BEHAVIOR_AVAILABLE = False

logger = logging.getLogger(__name__)


class PopupCloser:
    """
    Handles closing intrusive popups and ad overlays during manga downloads.
    
    This does NOT block ads from loading - ads still load normally.
    It only closes popup windows and overlay elements that block the manga content.
    """
    
    # Comprehensive selectors for close buttons on overlays
    CLOSE_SELECTORS = [
        # Common close button classes
        'button.close', 'a.close', 'span.close', 'div.close',
        '[class*="close"]', '[class*="Close"]',
        '[id*="close"]', '[id*="Close"]',
        
        # ARIA labels
        '[aria-label*="close" i]', '[aria-label*="dismiss" i]',
        '[title*="close" i]', '[title*="Close" i]',
        
        # Common patterns
        'button[class*="dismiss"]', '.modal-close', '.popup-close',
        '.overlay-close', '.fancybox-close', '.mfp-close',
        
        # Position-based (small X buttons in corners)
        'button[style*="position: absolute"][style*="right"]',
        'span[style*="position: absolute"][style*="right"]',
        'div[style*="cursor: pointer"][style*="top"][style*="right"]',
    ]
    
    def __init__(self, max_attempts: int = 5, wait_seconds: float = 2.0):
        """
        Initialize popup closer.
        
        Args:
            max_attempts: Maximum number of times to try closing overlays
            wait_seconds: Seconds to wait between close attempts
        """
        self.max_attempts = max_attempts
        self.wait_seconds = wait_seconds
        self.stats = {'popups_closed': 0, 'overlays_closed': 0, 'attempts': 0}
        
        if HUMAN_BEHAVIOR_AVAILABLE:
            self.human = HumanBehavior(
                min_delay=0.1,
                max_delay=0.5,
                movement_speed='medium'
            )
            logger.debug("Human behavior simulator initialized")
        else:
            self.human = None
            logger.debug("Human behavior simulator not available")
            
        # Threading control
        self._stop_event = None
        self._monitor_thread = None

    
    def close_all_popups_selenium(self, driver, original_url: str) -> dict:
        """
        Close all popup windows and ad overlays using Selenium.
        
        Args:
            driver: Selenium WebDriver instance
            original_url: The original page URL to return to if redirected
        
        Returns:
            Statistics dictionary
        """
        logger.info("🚫 Starting popup/overlay closer...")
        self.stats = {'popups_closed': 0, 'overlays_closed': 0, 'attempts': 0}
        
        for attempt in range(self.max_attempts):
            self.stats['attempts'] = attempt + 1
            logger.info(f"🔄 Attempt {attempt + 1}/{self.max_attempts}")
            
            # Step 1: Close popup windows/tabs
            popups = self._close_popup_windows_selenium(driver)
            self.stats['popups_closed'] += popups
            
            if popups > 0:
                logger.info(f"✅ Closed {popups} popup window(s)")
            
            time.sleep(0.5)
            
            # Step 2: Click close buttons on overlays
            overlays = self._click_close_buttons_selenium(driver)
            self.stats['overlays_closed'] += overlays
            
            if overlays > 0:
                logger.info(f"✅ Closed {overlays} overlay(s)")
            
            # Step 3: Check for redirect and navigate back
            current_url = driver.current_url
            if current_url != original_url and not self._same_page(current_url, original_url):
                logger.warning(f"⚠️ Redirected to: {current_url}")
                logger.info("↩️ Navigating back to original page...")
                try:
                    driver.get(original_url)
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Failed to navigate back: {e}")
                    break
            
            # If nothing was closed this iteration, we're done
            if popups == 0 and overlays == 0:
                if attempt > 0:
                    logger.info(f"✅ No more popups/overlays after {attempt + 1} attempts")
                break
            
            # Wait before next attempt
            if attempt < self.max_attempts - 1:
                time.sleep(self.wait_seconds)
        
        total = self.stats['popups_closed'] + self.stats['overlays_closed']
        if total > 0:
            logger.info(f"🎯 Closed {self.stats['popups_closed']} popups + {self.stats['overlays_closed']} overlays")
        else:
            logger.info("✅ No popups/overlays detected")
        
        return self.stats
    
    def _close_popup_windows_selenium(self, driver) -> int:
        """Close all popup windows except the main one."""
        closed = 0
        try:
            main_window = driver.current_window_handle
            all_windows = driver.window_handles
            
            for window in all_windows:
                if window != main_window:
                    try:
                        driver.switch_to.window(window)
                        driver.close()
                        closed += 1
                    except Exception as e:
                        logger.debug(f"Could not close window: {e}")
            
            # Switch back to main window
            driver.switch_to.window(main_window)
        except Exception as e:
            logger.debug(f"Error closing popup windows: {e}")
        
        return closed
    
    def _click_close_buttons_selenium(self, driver) -> int:
        """Find and click close buttons on overlays."""
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
        
        closed = 0
        
        # Convert to Selenium-compatible selectors
        selenium_selectors = [
            (By.CSS_SELECTOR, sel) for sel in [
                'button.close', 'a.close', 'span.close', 'div.close',
                '[class*="close"]', '[class*="Close"]',
                '[id*="close"]', '[aria-label*="close"]',
                'button[class*="dismiss"]', '.modal-close', '.popup-close',
            ]
        ] + [
            # XPath for X symbols
            (By.XPATH, '//*[contains(text(), "✕")]'),
            (By.XPATH, '//*[contains(text(), "×")]'),
            (By.XPATH, '//*[contains(text(), "✖")]'),
        ]
        
        for by, selector in selenium_selectors:
            try:
                elements = driver.find_elements(by, selector)
                for elem in elements:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            # Use human-like click if available, otherwise direct click
                            if self.human:
                                self.human.human_click(driver, elem)
                                closed += 1
                                logger.debug(f"Human-clicked: {selector}")
                            else:
                                elem.click()
                                closed += 1
                                logger.debug(f"Clicked: {selector}")
                                time.sleep(0.3)
                    except (NoSuchElementException, ElementClickInterceptedException):
                        continue
            except Exception:
                continue
        
        # Fallback: Remove overlays via JavaScript
        if closed == 0:
            closed += self._remove_overlays_js_selenium(driver)
        
        return closed
    
    def _remove_overlays_js_selenium(self, driver) -> int:
        """Remove overlay elements directly via JavaScript."""
        try:
            removed = driver.execute_script("""
                let count = 0;
                const overlays = document.querySelectorAll(
                    'div[style*="z-index"], div[class*="overlay"], ' +
                    'div[class*="popup"], div[class*="modal"]'
                );
                
                overlays.forEach(el => {
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex) || 0;
                    const position = style.position;
                    
                    if ((zIndex > 100 && (position === 'fixed' || position === 'absolute')) ||
                        el.className.toLowerCase().includes('overlay') ||
                        el.className.toLowerCase().includes('popup') ||
                        el.className.toLowerCase().includes('modal')) {
                        el.remove();
                        count++;
                    }
                });
                
                // Re-enable scrolling (often disabled by popups)
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
                
                return count;
            """)
            
            if removed > 0:
                logger.debug(f"Removed {removed} overlays via JavaScript")
            return removed
        except Exception as e:
            logger.debug(f"JavaScript overlay removal failed: {e}")
            return 0
    
    def _same_page(self, url1: str, url2: str) -> bool:
        """Check if two URLs are the same page (ignoring fragments/params)."""
        from urllib.parse import urlparse
        p1, p2 = urlparse(url1), urlparse(url2)
        return p1.scheme == p2.scheme and p1.netloc == p2.netloc and p1.path == p2.path
    
    def get_stats(self) -> dict:
        """Get statistics."""
        return self.stats.copy()
    
    def start_monitoring(self, driver, lock, interval=2.0) -> None:
        """
        Start a background thread to close popup windows periodically.
        
        Args:
            driver: Selenium WebDriver instance
            lock: Threading lock to synchronize driver access
            interval: Check interval in seconds
        """
        import threading
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Popup monitor already running")
            return

        self._stop_event = threading.Event()
        
        def _monitor_loop():
            logger.info("🛡️ Background popup monitor started")
            while not self._stop_event.is_set():
                try:
                    # Try to acquire lock without blocking for too long
                    if lock.acquire(timeout=1.0):
                        try:
                            # Quick check for popup windows only (fastest check)
                            self._close_popup_windows_selenium(driver)
                        finally:
                            lock.release()
                    
                    # Wait for next interval
                    time.sleep(interval)
                except Exception as e:
                    logger.debug(f"Monitor thread error: {e}")
                    # Don't crash the thread, just wait and retry
                    time.sleep(interval)
            logger.info("🛡️ Background popup monitor stopped")

        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        # Also inject the JS monitor immediately
        self.inject_js_monitor(driver)

    def stop_monitoring(self) -> None:
        """Stop the background monitoring thread."""
        if self._stop_event:
            self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3.0)
            self._monitor_thread = None
            
    def inject_js_monitor(self, driver) -> bool:
        """
        Inject a robust JavaScript interval that constantly removes proper overlays.
        This runs in parallel within the browser engine itself.
        """
        try:
            js_code = """
            if (window.mangaPopupCloserInterval) {
                clearInterval(window.mangaPopupCloserInterval);
            }
            
            window.mangaPopupCloserInterval = setInterval(() => {
                // 1. Existing overlay removal
                const overlays = document.querySelectorAll(
                    'div[style*="z-index"], div[class*="overlay"], ' +
                    'div[class*="popup"], div[class*="modal"], ' +
                    'iframe[style*="position: fixed"], ' +
                    'div[id*="google"], iframe[id*="google"]' 
                );
                
                overlays.forEach(el => {
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex) || 0;
                    const position = style.position;
                    const opacity = style.opacity;
                    
                    // aggressive heuristic for "bad" overlays
                    if ((zIndex > 50 && (position === 'fixed' || position === 'absolute') && opacity > 0) ||
                        el.id.toLowerCase().includes('pop') ||
                        el.className.toLowerCase().includes('popup') ||
                        el.className.toLowerCase().includes('overlay') ||
                        el.id.includes('vignette') ||
                        el.id.includes('interstitial')) {
                        
                        // Protect navigation elements
                        if (el.tagName === 'HEADER' || el.tagName === 'NAV' || 
                            el.id.includes('header') || el.className.includes('header')) {
                            return;
                        }
                        
                        el.remove();
                    }
                });
                
                // 2. Target specific "Top Right Corner" ads (blind check)
                try {
                    // Check top-right corner (margin for scrollbar)
                    const x = window.innerWidth - 30;
                    const y = 30;
                    const topElem = document.elementFromPoint(x, y);
                    
                    if (topElem && topElem !== document.body && topElem !== document.documentElement) {
                        const style = window.getComputedStyle(topElem);
                        // If it's a fixed/absolute element on top, click it (might be close button) or remove it
                        if (style.position === 'fixed' || style.position === 'absolute') {
                            if (style.zIndex > 50 || topElem.tagName === 'IFRAME') {
                                // Try clicking first if it looks like a button
                                if (topElem.tagName === 'BUTTON' || topElem.tagName === 'A' || 
                                    topElem.onclick || style.cursor === 'pointer') {
                                    topElem.click();
                                } else {
                                    // Otherwise remove potential overlay
                                    topElem.remove();
                                }
                            }
                        }
                    }
                } catch (e) {}

                // 3. Keep scrolling enabled
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            }, 500); // Check every 500ms
            """
            driver.execute_script(js_code)
            logger.info("💉 Injected parallel JS overlay killer")
            return True
        except Exception as e:
            logger.warning(f"Failed to inject JS monitor: {e}")
            return False

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {'popups_closed': 0, 'overlays_closed': 0, 'attempts': 0}


# Convenience function for quick use
def close_popups(driver, url: str, max_attempts: int = 5) -> dict:
    """
    Quick function to close popups and overlays on a page.
    
    Args:
        driver: Selenium WebDriver instance
        url: Current page URL
        max_attempts: Maximum close attempts
    
    Returns:
        Statistics dictionary
    """
    closer = PopupCloser(max_attempts=max_attempts)
    return closer.close_all_popups_selenium(driver, url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    print("=" * 70)
    print("POPUP CLOSER MODULE")
    print("=" * 70)
    print("\nThis module closes intrusive popups and ad overlays.")
    print("It does NOT block ads - ads still load normally.")
    print("It only closes popup windows and overlay elements that block content.")
    print("\nFeatures:")
    print("  • Closes popup windows/tabs automatically")
    print("  • Clicks X buttons on ad overlays")
    print("  • Handles redirect loops")
    print("  • Removes stubborn overlays via JavaScript")
    print("  • Multiple attempts for persistent popups")
    print("\nUsage:")
    print("  from popup_closer import close_popups")
    print("  close_popups(driver, current_url)")
