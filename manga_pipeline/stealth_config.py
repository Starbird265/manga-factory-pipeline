#!/usr/bin/env python3
"""
Stealth Config — injects JavaScript anti-detection patches into Playwright pages.
Also provides human-behavior simulation utilities.
"""

import random
import time
import logging

logger = logging.getLogger(__name__)

# JS to hide Playwright/Selenium automation signals
_STEALTH_JS = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Spoof plugins to look like real Chrome
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Spoof languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Spoof platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'MacIntel',
});

// Spoof hardwareConcurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});

// Fake window.chrome object (absent in headless by default)
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {},
};

// Override permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""


class StealthConfig:
    """
    Utility class to inject stealth patches into browser automation contexts.
    """

    @staticmethod
    def inject_stealth_scripts(page, mobile: bool = False):
        """
        Inject JS stealth patches into a Playwright page.
        Call this right after page creation, before any navigation.
        """
        try:
            page.add_init_script(_STEALTH_JS)
            if mobile:
                # Additional mobile-specific patches
                page.add_init_script("""
                    Object.defineProperty(navigator, 'platform', { get: () => 'iPhone' });
                    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
                """)
            logger.debug("[Stealth] Scripts injected successfully")
        except Exception as e:
            logger.warning(f"[Stealth] Could not inject scripts: {e}")

    @staticmethod
    def inject_stealth_selenium(driver):
        """
        Inject JS stealth patches into a Selenium WebDriver.
        """
        try:
            driver.execute_script(_STEALTH_JS)
            logger.debug("[Stealth] Selenium stealth injected")
        except Exception as e:
            logger.warning(f"[Stealth] Selenium stealth injection failed: {e}")

    @staticmethod
    def simulate_human_behavior(page):
        """
        Simulate human-like mouse movement on a Playwright page.
        Move to a few random positions with slight pauses.
        """
        try:
            width = page.viewport_size.get("width", 1280) if page.viewport_size else 1280
            height = page.viewport_size.get("height", 720) if page.viewport_size else 720

            # Move mouse to 2-4 random positions
            moves = random.randint(2, 4)
            for _ in range(moves):
                x = random.randint(100, width - 100)
                y = random.randint(100, height - 100)
                page.mouse.move(x, y)
                time.sleep(random.uniform(0.05, 0.2))

            logger.debug("[Stealth] Human mouse simulation complete")
        except Exception as e:
            logger.debug(f"[Stealth] Mouse simulation skipped: {e}")

    @staticmethod
    def get_random_viewport() -> dict:
        """Return a realistic random desktop viewport size."""
        viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1440, "height": 900},
            {"width": 1366, "height": 768},
            {"width": 1280, "height": 800},
            {"width": 1536, "height": 864},
        ]
        return random.choice(viewports)

    @staticmethod
    def get_desktop_user_agent() -> str:
        """Return a realistic desktop Chrome user agent."""
        agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        ]
        return random.choice(agents)
