#!/usr/bin/env python3
"""
Cookie Manager — persists browser cookies per domain to disk.
Used to pass Cloudflare challenges on subsequent visits without re-solving.
Cookies auto-expire after 7 days.
"""

import json
import re
import time
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

logger = logging.getLogger(__name__)

COOKIE_DIR = Path.home() / ".manga_cookies"
COOKIE_MAX_AGE_DAYS = 7


class CookieManager:
    """
    Save and load cookies for Playwright and Selenium per domain.
    Cookies are stored as JSON files in ~/.manga_cookies/.
    """

    def __init__(self, cookie_dir: Optional[Path] = None, profile: str = "default"):
        self.profile = self._safe_profile(profile)
        base_dir = Path(cookie_dir) if cookie_dir else COOKIE_DIR
        self.cookie_dir = base_dir if self.profile == "default" else base_dir / self.profile
        self.cookie_dir.mkdir(parents=True, exist_ok=True)
        self.browser_profile_dir = Path.home() / ".manga_browser_profiles" / self.profile
        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ Playwright
    def save_cookies_playwright(self, page, url: str) -> bool:
        """Persist cookies from a Playwright page to disk."""
        try:
            domain = self._domain(url)
            cookies = page.context.cookies()
            self._write(domain, cookies)
            logger.info(f"[Cookies:{self.profile}] Saved {len(cookies)} cookies for {domain}")
            return True
        except Exception as e:
            logger.warning(f"[Cookies] Failed to save Playwright cookies: {e}")
            return False

    def load_cookies_playwright(self, page, url: str) -> bool:
        """Load saved cookies into a Playwright page. Returns True if cookies were loaded."""
        try:
            domain = self._domain(url)
            cookies = self._read(domain)
            if not cookies:
                return False
            page.context.add_cookies(cookies)
            logger.info(f"[Cookies:{self.profile}] Loaded {len(cookies)} cookies for {domain}")
            return True
        except Exception as e:
            logger.warning(f"[Cookies] Failed to load Playwright cookies: {e}")
            return False

    # ------------------------------------------------------------------ Selenium
    def save_cookies_selenium(self, driver, url: str) -> bool:
        """Persist cookies from a Selenium driver to disk."""
        try:
            domain = self._domain(url)
            cookies = driver.get_cookies()
            self._write(domain, cookies)
            logger.info(f"[Cookies:{self.profile}] Saved {len(cookies)} Selenium cookies for {domain}")
            return True
        except Exception as e:
            logger.warning(f"[Cookies] Failed to save Selenium cookies: {e}")
            return False

    def load_cookies_selenium(self, driver, url: str) -> bool:
        """Load saved cookies into a Selenium driver. Returns True if any loaded."""
        try:
            domain = self._domain(url)
            cookies = self._read(domain)
            if not cookies:
                return False
            # Must navigate to domain first before setting cookies
            current = driver.current_url
            if domain not in current:
                logger.debug("[Cookies] Skipping Selenium cookie load — wrong domain")
                return False
            for c in cookies:
                # Selenium only accepts name/value/domain/path/expiry/secure/httpOnly
                clean = {k: v for k, v in c.items() if k in (
                    "name", "value", "domain", "path", "expiry", "secure", "httpOnly"
                )}
                try:
                    driver.add_cookie(clean)
                except Exception:
                    pass
            logger.info(f"[Cookies:{self.profile}] Loaded {len(cookies)} Selenium cookies for {domain}")
            return True
        except Exception as e:
            logger.warning(f"[Cookies] Failed to load Selenium cookies: {e}")
            return False

    # ------------------------------------------------------------------ Housekeeping
    def clear_cookies(self, url: str):
        """Delete saved cookies for a domain."""
        path = self._path(self._domain(url))
        if path.exists():
            path.unlink()
            logger.info(f"[Cookies] Cleared cookies for {self._domain(url)}")

    def clear_all(self):
        """Delete all saved cookie files."""
        for f in self.cookie_dir.glob("*.json"):
            f.unlink()
        logger.info("[Cookies] All cookies cleared")

    # ------------------------------------------------------------------ Private
    def _path(self, domain: str) -> Path:
        safe_name = domain.replace(".", "_").replace("/", "_")
        return self.cookie_dir / f"{safe_name}.json"

    @staticmethod
    def _safe_profile(profile: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(profile or "default")).strip("._")
        return value or "default"

    def _domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return "unknown"

    def _write(self, domain: str, cookies: list):
        data = {
            "saved_at": time.time(),
            "domain": domain,
            "cookies": cookies,
        }
        with open(self._path(domain), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _read(self, domain: str) -> list:
        path = self._path(domain)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Check age
            age_days = (time.time() - data.get("saved_at", 0)) / 86400
            if age_days > COOKIE_MAX_AGE_DAYS:
                logger.info(f"[Cookies] Expired cookies for {domain} ({age_days:.1f} days old) — clearing")
                path.unlink()
                return []
            return data.get("cookies", [])
        except Exception as e:
            logger.warning(f"[Cookies] Failed to read cookies for {domain}: {e}")
            return []
