#!/usr/bin/env python3
"""
Website Database — tracks known site configs (CSS selectors, Cloudflare status, etc.)
and provides a safe default for unknown/new sites.
"""

import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Known site configurations
# Keys: domain fragments (lowercase)  Values: site config dict
# ------------------------------------------------------------------
_KNOWN_SITES: Dict[str, Dict[str, Any]] = {
    "topmanhua.fan": {
        "name": "TopManhua",
        "image_selectors": [
            ".reading-content img.wp-manga-chapter-img",
            ".reading-content img",
            ".page-break img",
            ".text-left img",
        ],
        "cloudflare": False,
        "requires_js": True,
        "scroll_needed": True,
        "lazy_attr": "data-src",
        "cdn": "cdn.zinmanga1.com",
        "notes": "WP-manga theme. Images lazy-loaded via data-src. No Cloudflare.",
    },
    # Generic WP-manga theme sites (same selectors as topmanhua)
    "zinmanga": {
        "name": "ZinManga",
        "image_selectors": [
            ".reading-content img.wp-manga-chapter-img",
            ".reading-content img",
            ".page-break img",
        ],
        "cloudflare": False,
        "requires_js": True,
        "scroll_needed": True,
        "lazy_attr": "data-src",
    },
    "mangatx.org": {
        "name": "MangaTX",
        "image_selectors": [
            ".reading-content img",
            ".page-break img",
            "img.wp-manga-chapter-img",
        ],
        "cloudflare": True,
        "requires_js": True,
        "scroll_needed": True,
        "lazy_attr": "data-src",
    },
    "webtoon.com": {
        "name": "Webtoon (generic)",
        "image_selectors": [
            "._images img",
            ".viewer_img img",
            ".viewer_lst img",
        ],
        "cloudflare": False,
        "requires_js": True,
        "scroll_needed": True,
    },
    "webtoons.com": {

        "name": "Webtoons",
        "image_selectors": [
            "._images img",
            ".viewer_img img",
            ".viewer_lst img",
            "img[data-url]",
        ],
        "cloudflare": False,
        "requires_js": True,
        "scroll_needed": True,
        "notes": "Official Webtoons — Selenium required",
    },
    "manhuaus.com": {
        "name": "ManhuaUS",
        "image_selectors": [
            "div.reading-content img",
            ".text-left img",
            ".page-break img",
        ],
        "cloudflare": True,
        "requires_js": True,
        "scroll_needed": True,
        "notes": "Cloudflare protected — multi-layer fallback",
    },
    "mangaread.org": {
        "name": "MangaRead",
        "image_selectors": [
            "div.page-content img",
            "div.read-container img",
            ".reading-content img",
        ],
        "cloudflare": False,
        "requires_js": False,
        "scroll_needed": False,
        "notes": "Simple requests-based scraper works",
    },
    "manhwaclan.com": {
        "name": "ManhwaClan",
        "image_selectors": [
            ".reading-content img",
            ".page-break img",
        ],
        "cloudflare": True,
        "requires_js": True,
        "scroll_needed": True,
        "notes": "Needs undetected_chromedriver",
    },
    "mangakakalot.com": {
        "name": "Mangakakalot",
        "image_selectors": [
            ".container-chapter-reader img",
            "#vungdoc img",
        ],
        "cloudflare": False,
        "requires_js": False,
        "scroll_needed": False,
    },
    "mangadex.org": {
        "name": "MangaDex",
        "image_selectors": [
            ".reader-img",
            "img.cursor-pointer",
        ],
        "cloudflare": False,
        "requires_js": True,
        "scroll_needed": True,
    },
}

# Generic fallback selectors tried for unknown sites (ranked by specificity)
GENERIC_IMAGE_SELECTORS = [
    # Manga/webtoon-specific
    ".reading-content img",
    ".read-container img",
    ".chapter-content img",
    ".chapter-images img",
    "#chapter-content img",
    ".page-break img",
    ".manga-page img",
    ".viewer img",
    ".comic-page img",
    "div[class*='read'] img",
    "div[class*='chapter'] img",
    "div[class*='page'] img",
    "div[id*='chapter'] img",
    # Lazy-loaded
    "img[data-src]",
    "img[data-lazy-src]",
    "img[data-original]",
    "img[data-full-url]",
    # Generic fallback
    "article img",
    "main img",
    "img",
]


class WebsiteDatabase:
    """
    Provides site configuration for known manga sites, and
    safe defaults for unknown/new sites.
    """

    def __init__(self):
        self._db = _KNOWN_SITES

    def get_site_config(self, url: str) -> Dict[str, Any]:
        """
        Return config for the given URL.
        Falls back to a generic 'unknown site' config if the domain is not in the DB.
        """
        domain = self._extract_domain(url)
        for key, config in self._db.items():
            if key in domain:
                logger.debug(f"Known site found: {config['name']} ({domain})")
                return config

        logger.info(f"Unknown site: {domain} — using generic fallback config")
        return self._generic_config(domain)

    def is_known_site(self, url: str) -> bool:
        domain = self._extract_domain(url)
        return any(key in domain for key in self._db)

    def has_cloudflare(self, url: str) -> bool:
        config = self.get_site_config(url)
        return config.get("cloudflare", False)

    def requires_js(self, url: str) -> bool:
        config = self.get_site_config(url)
        return config.get("requires_js", False)

    def get_selectors(self, url: str):
        config = self.get_site_config(url)
        return config.get("image_selectors", GENERIC_IMAGE_SELECTORS)

    def register_site(self, domain: str, config: Dict[str, Any]):
        """Dynamically register a new site at runtime."""
        self._db[domain] = config
        logger.info(f"Registered new site: {domain}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            return (parsed.netloc or url).lower().replace("www.", "")
        except Exception:
            return url.lower()

    @staticmethod
    def _generic_config(domain: str) -> Dict[str, Any]:
        return {
            "name": domain,
            "image_selectors": GENERIC_IMAGE_SELECTORS,
            "cloudflare": False,   # unknown — we try anyway
            "requires_js": True,   # assume JS needed for safety
            "scroll_needed": True,
            "notes": "Auto-detected generic config",
            "is_unknown": True,
        }
