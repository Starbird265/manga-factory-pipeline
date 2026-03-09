#!/usr/bin/env python3
"""
HTML Scraper — fast, requests-based image extraction.
Used as Layer 1 (no browser) in the generic download fallback.
"""

import logging
import requests
from typing import List, Optional
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from website_database import WebsiteDatabase, GENERIC_IMAGE_SELECTORS

logger = logging.getLogger(__name__)

# Image extensions we consider valid manga pages
VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

# Excluded URL fragments that are never manga pages
EXCLUDED_KEYWORDS = [
    "logo", "avatar", "icon", "banner", "thumb", "button",
    "background", "advertising", "pixel", "tracking", "spacer",
    "transparent", "gravatar", "captcha", "ad.", "/ads/",
]

# Browser-like headers for requests
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class HTMLScraper:
    """
    Fast, browser-free HTML scraper.
    Works best on static or SSR manga sites.
    """

    def __init__(self, db: Optional[WebsiteDatabase] = None):
        self.db = db or WebsiteDatabase()
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

    def extract_image_urls(self, url: str, timeout: int = 30) -> List[str]:
        """
        Fetch the page at `url` and extract all manga image URLs.
        Returns list of absolute image URLs. Empty list means failure.
        """
        if not BS4_AVAILABLE:
            logger.warning("BeautifulSoup4 not installed — HTML scraper unavailable")
            return []

        try:
            logger.info(f"[HTML Scraper] Fetching: {url}")
            resp = self.session.get(url, timeout=timeout, allow_redirects=True)

            # Check for Cloudflare / bot protection by status
            if resp.status_code == 403:
                logger.warning(f"[HTML Scraper] 403 Forbidden — site may block scrapers: {url}")
                return []
            if resp.status_code == 503:
                logger.warning(f"[HTML Scraper] 503 Service Unavailable — possible Cloudflare: {url}")
                return []

            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            selectors = self.db.get_selectors(url)

            image_urls: List[str] = []
            seen = set()

            # Try selectors in order (most-specific first)
            for selector in selectors:
                try:
                    imgs = soup.select(selector)
                    for img in imgs:
                        src = self._pick_src(img)
                        if not src:
                            continue
                        abs_src = urljoin(url, src)
                        if abs_src in seen:
                            continue
                        if self._is_valid_manga_image(abs_src):
                            image_urls.append(abs_src)
                            seen.add(abs_src)
                except Exception as e:
                    logger.debug(f"[HTML Scraper] Selector '{selector}' failed: {e}")
                    continue

                if image_urls:
                    logger.info(f"[HTML Scraper] Found {len(image_urls)} images with selector '{selector}'")
                    break

            if not image_urls:
                logger.warning(
                    f"[HTML Scraper] No images found on {url}. "
                    f"Page title: '{soup.title.string if soup.title else 'N/A'}'"
                )
            return image_urls

        except requests.ConnectionError:
            logger.error(f"[HTML Scraper] Cannot connect to {url} — site may be down or blocked")
            return []
        except requests.Timeout:
            logger.error(f"[HTML Scraper] Timeout connecting to {url}")
            return []
        except Exception as e:
            logger.error(f"[HTML Scraper] Unexpected error scraping {url}: {e}")
            return []

    def close(self):
        if self.session:
            self.session.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_src(img_tag) -> Optional[str]:
        """Extract the best src from an img tag, preferring lazy-load attrs."""
        for attr in ("data-src", "data-lazy-src", "data-original", "data-full-url", "data-url", "src"):
            val = img_tag.get(attr)
            if val and val.strip() and not val.strip().startswith("data:image/gif"):
                return val.strip()
        # Try srcset — take the last (highest-res) entry
        srcset = img_tag.get("srcset")
        if srcset:
            parts = [p.strip() for p in srcset.split(",") if p.strip()]
            if parts:
                return parts[-1].split(" ")[0]
        return None

    @staticmethod
    def _is_valid_manga_image(url: str) -> bool:
        """Return True if the URL looks like a legit manga page image."""
        if not url:
            return False
        url_lower = url.lower()
        if any(kw in url_lower for kw in EXCLUDED_KEYWORDS):
            return False
        # Must have a known image extension or look like an image CDN path
        parsed = urlparse(url_lower)
        path = parsed.path
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        if f".{ext}" in VALID_IMAGE_EXTS:
            return True
        # Some CDNs serve images without extension (e.g. ?format=webp)
        if "image" in url_lower or "img" in parsed.path:
            return True
        return False
