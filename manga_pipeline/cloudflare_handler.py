#!/usr/bin/env python3
"""
Cloudflare Handler — detects Cloudflare challenge pages and waits for resolution.
Supports both Playwright pages and Selenium WebDriver instances.
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Phrases that indicate an active Cloudflare challenge page
_CF_TITLE_PHRASES = [
    "just a moment",
    "checking your browser",
    "please wait",
    "ddos-guard",
    "attention required",
    "cloudflare",
    "ray id",
    "security check",
    "one more step",
]

_CF_BODY_PHRASES = [
    "cf-browser-verification",
    "cf_clearance",
    "challenge-platform",
    "__cf_bm",
    "cloudflare ray id",
    "enable javascript",
    "checking if the site connection is secure",
    "this process is automatic",
]


class CloudflareHandler:
    """
    Static utility class for detecting and waiting out Cloudflare challenges.
    """

    # ------------------------------------------------------------------ Playwright
    @staticmethod
    def is_challenge_page_playwright(page) -> bool:
        """Return True if the current Playwright page is a Cloudflare challenge."""
        try:
            title = (page.title() or "").lower()
            body = page.content().lower()
            return (
                any(phrase in title for phrase in _CF_TITLE_PHRASES)
                or any(phrase in body for phrase in _CF_BODY_PHRASES)
            )
        except Exception as e:
            logger.debug(f"[CF] Could not check Playwright page: {e}")
            return False

    @staticmethod
    def wait_for_challenge_resolution_playwright(page, timeout: int = 60) -> bool:
        """
        Poll the Playwright page until the Cloudflare challenge resolves or timeout.
        Returns True on success, False on timeout.
        """
        logger.info(f"[CF] Waiting up to {timeout}s for Cloudflare to resolve...")
        end_time = time.time() + timeout
        while time.time() < end_time:
            time.sleep(2)
            try:
                if not CloudflareHandler.is_challenge_page_playwright(page):
                    logger.info("[CF] ✅ Cloudflare challenge resolved!")
                    return True
                elapsed = int(time.time() - (end_time - timeout))
                logger.debug(f"[CF] Still on challenge page... {elapsed}s elapsed")
            except Exception:
                break
        logger.warning("[CF] ⏰ Cloudflare challenge timed out")
        return False

    # ------------------------------------------------------------------ Selenium
    @staticmethod
    def is_challenge_page_selenium(driver) -> bool:
        """Return True if the Selenium driver is on a Cloudflare challenge page."""
        try:
            title = (driver.title or "").lower()
            # Page source check is expensive — only do it if title looks suspicious
            if any(phrase in title for phrase in _CF_TITLE_PHRASES):
                return True
            # Quick JS check for CF cookie present
            try:
                has_cf = driver.execute_script(
                    "return document.cookie.includes('cf_clearance') || "
                    "document.body.innerText.toLowerCase().includes('checking your browser');"
                )
                if has_cf:
                    # Check more carefully
                    body = driver.page_source.lower()
                    return any(phrase in body for phrase in _CF_BODY_PHRASES)
            except Exception:
                pass
            return False
        except Exception as e:
            logger.debug(f"[CF] Could not check Selenium page: {e}")
            return False

    @staticmethod
    def wait_for_challenge_resolution_selenium(driver, timeout: int = 90) -> bool:
        """
        Poll the Selenium driver until the Cloudflare challenge resolves or timeout.
        Returns True on success, False on timeout.
        """
        logger.info(f"[CF] Waiting up to {timeout}s for Cloudflare to resolve (Selenium)...")
        end_time = time.time() + timeout
        while time.time() < end_time:
            time.sleep(2)
            try:
                if not CloudflareHandler.is_challenge_page_selenium(driver):
                    logger.info("[CF] ✅ Cloudflare challenge resolved (Selenium)!")
                    return True
            except Exception:
                break
        logger.warning("[CF] ⏰ Cloudflare challenge timed out (Selenium)")
        return False

    # ------------------------------------------------------------------ Generic helpers
    @staticmethod
    def get_diagnostic_info_playwright(page) -> dict:
        """Return diagnostic info for a Cloudflare-blocked page."""
        try:
            return {
                "url": page.url,
                "title": page.title(),
                "status": None,  # Playwright doesn't expose status easily post-navigation
            }
        except Exception:
            return {}

    @staticmethod
    def get_diagnostic_info_selenium(driver) -> dict:
        """Return diagnostic info for a Cloudflare-blocked page."""
        try:
            return {
                "url": driver.current_url,
                "title": driver.title,
            }
        except Exception:
            return {}
