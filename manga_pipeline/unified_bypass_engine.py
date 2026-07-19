#!/usr/bin/env python3
"""
Unified Bypass Engine — Orchestrates multi-method, multi-IP scraping.

Strategy:
  Each method is tried EXACTLY ONCE. Between failures, the proxy IP is
  rotated via MLProxyManager. The escalation order is:

  1. requests (fast, no browser)         — new proxy
  2. Playwright + stealth                — new proxy
  3. Undetected ChromeDriver             — new proxy
  4. Playwright mobile emulation         — new proxy
  5. GIVE UP

  SmartPipelineManager memory is consulted to skip methods already known
  to fail for a given domain, and results are recorded back so the system
  learns over time.
"""

import time
import random
import logging
from typing import Dict, List, Optional, Callable, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Optional imports (graceful degradation if unavailable)
try:
    from ml_proxy_manager import MLProxyManager
except ImportError:
    MLProxyManager = None

try:
    from smart_pipeline_manager import SmartPipelineManager
except ImportError:
    SmartPipelineManager = None

try:
    from cookie_manager import CookieManager
except ImportError:
    CookieManager = None

try:
    from website_database import WebsiteDatabase
except ImportError:
    WebsiteDatabase = None

try:
    from cloudflare_handler import CloudflareHandler
except ImportError:
    CloudflareHandler = None

try:
    from stealth_config import StealthConfig
except ImportError:
    StealthConfig = None

try:
    from ad_blocker import AdBlocker
except ImportError:
    AdBlocker = None

try:
    from html_scraper import HTMLScraper
except ImportError:
    HTMLScraper = None

try:
    from ml_site_learner import MLSiteLearner
except ImportError:
    MLSiteLearner = None

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None

try:
    from playwright_stealth import stealth_sync
except ImportError:
    stealth_sync = None

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    uc = None
    By = None

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class UnifiedBypassEngine:
    """
    Auto-escalating download engine.

    Each bypass method is tried EXACTLY ONCE. Between failures, the
    proxy IP is rotated. The SmartPipelineManager is consulted to skip
    methods known to fail for a domain and results are recorded back.
    """

    # Ordered escalation chain — each entry is (method_name, function_key)
    ESCALATION_CHAIN = [
        'requests',
        'playwright',
        'undetected_chrome',
        'playwright_mobile',
    ]

    # Desktop user agents
    DESKTOP_UAS = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    # Mobile user agents
    MOBILE_UAS = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    ]

    def __init__(
        self,
        proxy_manager: Optional[Any] = None,
        pipeline_manager: Optional[Any] = None,
        website_db: Optional[Any] = None,
        cookie_manager: Optional[Any] = None,
        headless: bool = True,
        enable_ad_blocker: bool = True,
        enable_human_behavior: bool = True,
        profile_name: str = "default",
        force_headful: bool = False,
        browser_only: bool = False,
    ):
        self.proxy_mgr = proxy_manager
        self.pipeline_mgr = pipeline_manager
        self.website_db = website_db or (WebsiteDatabase() if WebsiteDatabase else None)
        self.profile_name = profile_name or "default"
        self.cookie_mgr = cookie_manager or (
            CookieManager(profile=self.profile_name) if CookieManager else None
        )
        self.force_headful = bool(force_headful)
        self.browser_only = bool(browser_only)
        self.headless = False if self.force_headful else headless
        self.enable_human_behavior = enable_human_behavior
        self.ad_blocker = AdBlocker(max_iterations=5) if (enable_ad_blocker and AdBlocker) else None

    # ─── Public API ──────────────────────────────────────────────────

    def download(self, url: str) -> Dict:
        """
        Smart download with site-aware method selection.

        Strategy:
        1. Check website_database for known best_method + cloudflare status
        2. Check SmartPipelineManager for learned history
        3. Build a smart chain: skip methods known to fail (e.g. requests on CF sites)
        4. Use the ML-selected proxy for every retrieval when a proxy pool exists
        5. Fall back to direct only when the proxy pool is unavailable
        6. Each scraper method is attempted once, and its result trains the
           site-memory and proxy UCB models
        """
        domain = self._get_domain(url)
        logger.info(f"🚀 [UnifiedBypass] Starting smart chain for {domain}")

        # ── Step 1: Gather site intelligence ─────────────────────────
        site_config = {}
        has_cloudflare = False
        requires_js = False
        db_best_method = None

        if self.website_db:
            try:
                site_config = self.website_db.get_site_config(url)
                has_cloudflare = site_config.get('cloudflare', False)
                requires_js = site_config.get('requires_js', False)
                db_best_method = site_config.get('best_method')
                site_name = site_config.get('name', domain)
                logger.info(
                    f"  📋 Site DB: {site_name} | CF={has_cloudflare} "
                    f"| JS={requires_js} | best={db_best_method}"
                )
            except Exception:
                pass

        # ── Step 2: Check pipeline memory (learned from past runs) ───
        pipeline_best = None
        if self.pipeline_mgr:
            try:
                strategy = self.pipeline_mgr.get_strategy(url)
                pipeline_best = strategy.get('best_scraper')
                delay = strategy.get('delay_needed', 0.5)
                if delay > 0.5:
                    time.sleep(delay)
                if pipeline_best:
                    logger.info(f"  🧠 Pipeline memory: best_scraper={pipeline_best}")
            except Exception:
                pass

        # ── Step 3: Build smart chain ────────────────────────────────
        # Priority: pipeline memory > database hint > default escalation
        preferred = pipeline_best or db_best_method

        chain = list(self.ESCALATION_CHAIN)
        if self.browser_only:
            chain = ['undetected_chrome', 'playwright']
            logger.info(
                f"  Browser account mode: profile={self.profile_name}, headful={not self.headless}"
            )

        # Skip methods known to fail for this site type
        skip_reasons = {}
        if has_cloudflare:
            skip_reasons['requests'] = 'Cloudflare protected (would get 403)'
            skip_reasons['playwright'] = 'Cloudflare blocks headless browsers'
            skip_reasons['playwright_mobile'] = 'Cloudflare blocks headless browsers'
        if requires_js and not has_cloudflare:
            skip_reasons['requests'] = 'Requires JavaScript rendering'

        # Remove skipped methods
        for method in list(chain):
            if method in skip_reasons:
                chain.remove(method)
                logger.info(f"  ⏭️  Skipping {method}: {skip_reasons[method]}")

        # Put preferred method first
        if preferred and preferred in chain:
            chain.remove(preferred)
            chain.insert(0, preferred)
            logger.info(f"  ⭐ Preferred method '{preferred}' moved to front")

        if not chain:
            chain = ['undetected_chrome']  # last resort

        logger.info(f"  📝 Final chain: {chain}")

        # ── Step 4: Execute chain (ML proxy first, direct only as a failsafe) ─
        result = {
            'success': False,
            'image_urls': [],
            'method': 'none',
            'attempts': [],
        }

        for method_name in chain:
            # Public proxies fail frequently. The UCB model scores each result,
            # then supplies a different candidate for the next proxy-only retry.
            # No direct attempt is made while a proxy pool exists.
            proxy_attempt_limit = 3 if self.proxy_mgr else 1
            attempted_proxies = set()
            attempt_result = {'success': False, 'image_urls': [], 'cloudflare': False}

            for proxy_attempt in range(proxy_attempt_limit):
                proxy = None
                if self.proxy_mgr:
                    try:
                        proxy = self.proxy_mgr.get_best_proxy()
                    except Exception as exc:
                        logger.debug(f"  ML proxy selection failed: {exc}")

                if proxy and proxy in attempted_proxies:
                    logger.warning("  ML proxy selector repeated a failed proxy; moving to next scraper.")
                    break
                if proxy:
                    attempted_proxies.add(proxy)
                    logger.info(
                        f"  ▶ [{method_name}] ML proxy {proxy} "
                        f"({proxy_attempt + 1}/{proxy_attempt_limit})..."
                    )
                else:
                    logger.warning(
                        f"  ▶ [{method_name}] No usable proxy is available; using a direct fallback."
                    )

                t0 = time.time()
                attempt_result = self._try_method(method_name, url, proxy=proxy)
                duration = time.time() - t0
                self._record_attempt(result, method_name, proxy, attempt_result, duration, url)

                if attempt_result['success'] and attempt_result.get('image_urls'):
                    result['success'] = True
                    result['image_urls'] = attempt_result['image_urls']
                    result['method'] = method_name
                    logger.info(
                        f"  ✅ SUCCESS with {method_name} "
                        f"({'proxy' if proxy else 'direct fallback'}) — "
                        f"{len(result['image_urls'])} images found"
                    )
                    return result

                if not proxy:
                    break

            # A free proxy pool can be entirely stale. Keep the proxy-first
            # policy, but do not abandon a readable chapter after several ML
            # candidates have demonstrably failed.
            if method_name == 'requests' and attempted_proxies:
                logger.warning(
                    "  All selected proxies failed for requests; trying one direct emergency fallback."
                )
                t0 = time.time()
                attempt_result = self._try_method(method_name, url, proxy=None)
                duration = time.time() - t0
                self._record_attempt(result, method_name, None, attempt_result, duration, url)
                if attempt_result['success'] and attempt_result.get('image_urls'):
                    result['success'] = True
                    result['image_urls'] = attempt_result['image_urls']
                    result['method'] = method_name
                    logger.info(
                        f"  ✅ SUCCESS with {method_name} (direct emergency fallback) — "
                        f"{len(result['image_urls'])} images found"
                    )
                    return result

            logger.warning(f"  ❌ {method_name} failed (CF={attempt_result.get('cloudflare', False)})")
            time.sleep(random.uniform(0.5, 1.5))

        logger.error("  💀 [UnifiedBypass] ALL methods exhausted — download failed")
        return result

    def _record_attempt(self, result, method_name, proxy, attempt_result, duration, url):
        """Record attempt to result dict and report to managers."""
        attempt_info = {
            'method': method_name,
            'proxy': proxy,
            'success': attempt_result['success'],
            'image_count': len(attempt_result.get('image_urls', [])),
            'duration': round(duration, 2),
        }
        result['attempts'].append(attempt_info)

        # Report to pipeline manager
        if self.pipeline_mgr:
            try:
                self.pipeline_mgr.record_scraper_result(
                    url=url,
                    scraper_name=method_name,
                    success=attempt_result['success'],
                    duration=duration,
                    is_cloudflare=attempt_result.get('cloudflare', False),
                )
            except Exception:
                pass

        # Report to proxy manager
        if self.proxy_mgr and proxy:
            try:
                self.proxy_mgr.report_result(
                    proxy,
                    success=attempt_result['success'],
                    latency=duration,
                    cloudflare_blocked=attempt_result.get('cloudflare', False),
                )
            except Exception:
                pass

    # ─── Method Dispatcher ───────────────────────────────────────────

    def _try_method(self, method_name: str, url: str, proxy: Optional[str]) -> Dict:
        """Dispatch to the correct bypass method."""
        dispatch = {
            'requests': self._try_requests,
            'playwright': self._try_playwright,
            'undetected_chrome': self._try_uc,
            'playwright_mobile': self._try_playwright_mobile,
        }
        fn = dispatch.get(method_name)
        if fn is None:
            return {'success': False, 'image_urls': [], 'cloudflare': False}
        try:
            return fn(url, proxy)
        except Exception as e:
            logger.error(f"  💥 {method_name} crashed: {e}")
            return {'success': False, 'image_urls': [], 'cloudflare': False}

    # ─── Method 1: Raw Requests (fastest, no browser) ────────────────

    def _try_requests(self, url: str, proxy: Optional[str]) -> Dict:
        """Try simple HTTP GET. Works on unprotected / SSR sites."""
        result = {'success': False, 'image_urls': [], 'cloudflare': False}
        if not REQUESTS_AVAILABLE:
            return result

        try:
            # Site-aware HTML extraction is both more accurate and cheaper
            # than launching a browser. It uses the same selected proxy.
            if HTMLScraper and self.website_db:
                proxy_map = {'http': proxy, 'https': proxy} if proxy else None
                scraper = HTMLScraper(self.website_db, proxies=proxy_map)
                try:
                    images = scraper.extract_image_urls(url, timeout=10)
                finally:
                    scraper.close()
                if len(images) >= 3:
                    result['success'] = True
                    result['image_urls'] = images
                    return result

            session = _requests.Session()
            session.headers.update({
                'User-Agent': random.choice(self.DESKTOP_UAS),
                'Accept': 'text/html,application/xhtml+xml,*/*',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            if proxy:
                session.proxies = {'http': proxy, 'https': proxy}

            resp = session.get(url, timeout=10, allow_redirects=True)
            if resp.status_code in (403, 503):
                result['cloudflare'] = True
                return result
            resp.raise_for_status()

            # Fallback to ML Site Learner for unknown/static DOMs.
            if MLSiteLearner:
                images = MLSiteLearner.analyze_dom_for_manga_images(resp.text, url)
                if len(images) >= 3:
                    result['success'] = True
                    result['image_urls'] = images
                    return result

        except Exception as e:
            logger.debug(f"    requests method error: {e}")

        return result

    # ─── Method 2: Playwright + Stealth ──────────────────────────────

    def _try_playwright(self, url: str, proxy: Optional[str]) -> Dict:
        """Full browser with stealth patches and desktop viewport."""
        return self._playwright_core(url, proxy, mobile=False)

    # ─── Method 4: Playwright Mobile ─────────────────────────────────

    def _try_playwright_mobile(self, url: str, proxy: Optional[str]) -> Dict:
        """Playwright with mobile device emulation (better for some CF)."""
        return self._playwright_core(url, proxy, mobile=True)

    def _playwright_core(self, url: str, proxy: Optional[str], mobile: bool) -> Dict:
        """Shared Playwright logic for desktop and mobile modes."""
        result = {'success': False, 'image_urls': [], 'cloudflare': False}
        if not PLAYWRIGHT_AVAILABLE:
            return result

        pw = None
        browser = None
        context = None
        try:
            pw = sync_playwright().start()

            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-notifications',
            ]

            browser_kwargs = {
                'headless': self.headless,
                'args': launch_args,
            }
            if proxy:
                browser_kwargs['proxy'] = {'server': proxy}

            # Context setup
            if mobile:
                ua = random.choice(self.MOBILE_UAS)
                context_kwargs = dict(
                    user_agent=ua,
                    viewport={'width': 390, 'height': 844},
                    device_scale_factor=3,
                    is_mobile=True,
                    has_touch=True,
                )
            else:
                ua = random.choice(self.DESKTOP_UAS)
                context_kwargs = dict(
                    user_agent=ua,
                    viewport={
                        'width': random.randint(1280, 1920),
                        'height': random.randint(720, 1080),
                    },
                )

            if self.profile_name != "default" and self.cookie_mgr:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(self.cookie_mgr.browser_profile_dir),
                    **browser_kwargs,
                    **context_kwargs,
                )
                page = context.pages[0] if context.pages else context.new_page()
            else:
                browser = pw.chromium.launch(**browser_kwargs)
                context = browser.new_context(**context_kwargs)
                page = context.new_page()

            # Apply stealth
            if stealth_sync:
                stealth_sync(page)
            if StealthConfig:
                StealthConfig.inject_stealth_scripts(page, mobile=mobile)

            # Load cookies
            if self.cookie_mgr:
                try:
                    self.cookie_mgr.load_cookies_playwright(page, url)
                except Exception:
                    pass

            # Navigate
            page.goto(url, timeout=60000, wait_until='domcontentloaded')

            # Simulate human behavior
            if StealthConfig and self.enable_human_behavior:
                StealthConfig.simulate_human_behavior(page)
            time.sleep(random.uniform(1.0, 2.0))

            # Check for Cloudflare
            if CloudflareHandler and CloudflareHandler.is_challenge_page_playwright(page):
                result['cloudflare'] = True
                logger.info("    🛡️ Cloudflare challenge detected, waiting...")
                if CloudflareHandler.wait_for_challenge_resolution_playwright(page, timeout=60):
                    logger.info("    ✅ Cloudflare resolved!")
                    if self.cookie_mgr:
                        try:
                            self.cookie_mgr.save_cookies_playwright(page, url)
                        except Exception:
                            pass
                    page.wait_for_timeout(5000)
                else:
                    return result

            # Handle ads
            if self.ad_blocker:
                try:
                    self.ad_blocker.handle_ads_playwright(page, url)
                    self.ad_blocker.reset_stats()
                except Exception:
                    pass

            # Scroll to trigger lazy loading
            self._scroll_page_playwright(page)

            # Extract images
            images = self._extract_images_playwright(page, url)

            # If selectors didn't find enough, try ML site learner
            if len(images) < 3 and MLSiteLearner:
                try:
                    html = page.content()
                    ml_images = MLSiteLearner.analyze_dom_for_manga_images(html, page.url)
                    if len(ml_images) > len(images):
                        images = ml_images
                except Exception:
                    pass

            if images:
                result['success'] = True
                result['image_urls'] = images

        except Exception as e:
            logger.debug(f"    Playwright {'mobile' if mobile else 'desktop'} error: {e}")
        finally:
            try:
                if context:
                    context.close()
                if browser:
                    browser.close()
                if pw:
                    pw.stop()
            except Exception:
                pass

        return result

    # ─── CF Turnstile Human Click ──────────────────────────────────────

    def _human_click_cf_turnstile(self, driver):
        """
        Click the Cloudflare turnstile checkbox with human-like behavior.

        Strategy:
        1. Find the turnstile iframe on the page
        2. Move mouse to it with natural random offset (not dead-center)
        3. Small pause (like a human hesitating)
        4. Click with a natural delay
        5. Handle any ad popup that opens from the click
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        try:
            # Store current window handle
            main_window = driver.current_window_handle

            # Find turnstile iframe
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            turnstile_iframe = None
            for iframe in iframes:
                try:
                    src = iframe.get_attribute('src') or ''
                    title = iframe.get_attribute('title') or ''
                    if any(kw in src.lower() for kw in ['challenges.cloudflare', 'turnstile', 'cf-chl']) \
                       or 'cloudflare' in title.lower():
                        turnstile_iframe = iframe
                        logger.info(f"    🎯 Found turnstile iframe: {src[:60]}...")
                        break
                except Exception:
                    continue

            if not turnstile_iframe:
                # No iframe found — try clicking the page body (some CF pages
                # use an interstitial that resolves on any click)
                logger.info("    🖱️ No turnstile iframe — clicking page body...")
                time.sleep(random.uniform(1.0, 2.0))
                ActionChains(driver) \
                    .move_by_offset(random.randint(100, 400), random.randint(200, 400)) \
                    .pause(random.uniform(0.1, 0.3)) \
                    .click() \
                    .perform()
                time.sleep(random.uniform(2.0, 4.0))
                return

            # ── Human-like click on turnstile ──
            # Move to iframe with random offset (not dead-center — bots click center)
            iframe_size = turnstile_iframe.size
            x_offset = random.randint(-15, 15)
            y_offset = random.randint(-5, 5)

            logger.info(f"    🖱️ Moving to turnstile (offset: {x_offset},{y_offset})...")

            # Small random pause before moving (like reading the page)
            time.sleep(random.uniform(0.5, 1.5))

            # Move and click with natural timing
            actions = ActionChains(driver)
            actions.move_to_element_with_offset(turnstile_iframe, x_offset, y_offset)
            actions.pause(random.uniform(0.2, 0.6))  # Hesitation before click
            actions.click()
            actions.perform()

            logger.info("    ✅ Clicked turnstile checkbox")

            # Wait a moment for the click to register
            time.sleep(random.uniform(2.0, 4.0))

            # Handle ad popup that opens from the click
            try:
                all_windows = driver.window_handles
                if len(all_windows) > 1:
                    for w in all_windows:
                        if w != main_window:
                            logger.info("    🚫 Closing ad popup window...")
                            driver.switch_to.window(w)
                            driver.close()
                    driver.switch_to.window(main_window)
                    time.sleep(random.uniform(1.0, 2.0))
            except Exception:
                try:
                    driver.switch_to.window(main_window)
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"    Turnstile click error: {e}")

    # ─── Method 3: Undetected ChromeDriver ───────────────────────────

    def _try_uc(self, url: str, proxy: Optional[str]) -> Dict:
        """
        Undetected ChromeDriver — best against aggressive Cloudflare.

        KEY INSIGHT: CF sites CANNOT be bypassed headless. For CF sites this
        method forces headful mode, waits for actual page content to appear
        (not CF challenge resolution), handles popup ads, and does human-like
        scrolling — matching the proven legacy manhwaclan flow.
        """
        result = {'success': False, 'image_urls': [], 'cloudflare': False}
        if not UC_AVAILABLE:
            return result

        # Check if this is a CF-protected site
        site_has_cf = False
        site_selectors = None
        if self.website_db:
            try:
                config = self.website_db.get_site_config(url)
                site_has_cf = config.get('cloudflare', False)
                site_selectors = config.get('image_selectors')
            except Exception:
                pass

        # For CF sites, MUST run headful — headless always fails
        use_headless = self.headless and not site_has_cf and not self.force_headful
        if site_has_cf and self.headless:
            logger.info("    🖥️ CF site detected — forcing headful (visible) mode")

        driver = None
        popup_closer_inst = None
        try:
            import threading

            options = uc.ChromeOptions()
            if use_headless:
                options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            if self.cookie_mgr and self.profile_name != "default":
                options.add_argument(f'--user-data-dir={self.cookie_mgr.browser_profile_dir}')
                options.add_argument('--profile-directory=Default')

            if site_has_cf:
                # CF sites: DON'T set custom user-agent — UC's whole point is
                # using the real browser UA. Custom UA makes it detectable.
                # Also DON'T set tight page_load_timeout (CF challenge needs time).
                pass
            else:
                options.add_argument('--disable-notifications')
                options.add_argument(f'--user-agent={random.choice(self.DESKTOP_UAS)}')
                options.add_argument(f'--window-size={random.randint(1280,1920)},{random.randint(720,1080)}')

            if proxy:
                options.add_argument(f'--proxy-server={proxy}')

            driver = uc.Chrome(options=options, use_subprocess=True)

            if not site_has_cf:
                driver.set_page_load_timeout(60)

            # Load cookies
            if self.cookie_mgr:
                try:
                    self.cookie_mgr.load_cookies_selenium(driver, url)
                except Exception:
                    pass

            # Navigate
            logger.info(f"    📍 Navigating to: {url}")
            driver.get(url)

            if site_has_cf:
                # ── CF SITE FLOW ──
                # Strategy from user feedback:
                # 1. Wait ~10s for CF to auto-resolve (sometimes it does)
                # 2. If CF page still showing, click the turnstile with human behavior
                # 3. Wait for actual page content to appear
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.common.action_chains import ActionChains

                # Phase 1: Give CF 10s to auto-resolve
                logger.info("    ⏳ Waiting 10s for CF auto-resolve...")
                content_selectors = '.reading-content img, .page-break img, .chapter-content img'
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, content_selectors))
                    )
                    logger.info("    ✅ CF auto-resolved! Content loaded.")
                    result['cloudflare'] = True
                except Exception:
                    # Phase 2: CF didn't auto-resolve — click the turnstile naturally
                    logger.info("    🖱️ CF still active — attempting human-like turnstile click...")
                    if self.enable_human_behavior:
                        self._human_click_cf_turnstile(driver)

                    # Phase 3: Wait for content after clicking
                    logger.info("    ⏳ Waiting for page content (up to 35s)...")
                    try:
                        WebDriverWait(driver, 35).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, content_selectors))
                        )
                        logger.info("    ✅ Page content loaded after turnstile click!")
                        result['cloudflare'] = True
                    except Exception:
                        logger.warning("    ⚠️ Timed out waiting for content — continuing anyway")
                        time.sleep(5)

                # Save CF bypass cookies for future use
                if self.cookie_mgr:
                    try:
                        self.cookie_mgr.save_cookies_selenium(driver, url)
                    except Exception:
                        pass

                # Start parallel popup closer (handles ad popups from clicking)
                driver_lock = threading.Lock()
                try:
                    from popup_closer import PopupCloser as PC
                    popup_closer_inst = PC(max_attempts=5, wait_seconds=2.0)
                    popup_closer_inst.start_monitoring(driver, driver_lock, interval=2.0)
                    logger.info("    🛡️ Popup closer active")
                except Exception:
                    driver_lock = None

                # ── Click page body to trigger the ad popup, then close it ──
                # manhwaclan (and similar sites) open an ad popup on first click.
                # We need to trigger it, close it, then continue normally.
                try:
                    main_window = driver.current_window_handle
                    logger.info("    🖱️ Clicking page body to trigger ad popup...")
                    time.sleep(random.uniform(0.5, 1.0))

                    if self.enable_human_behavior and driver_lock:
                        with driver_lock:
                            ActionChains(driver) \
                                .move_by_offset(random.randint(200, 500), random.randint(300, 500)) \
                                .pause(random.uniform(0.1, 0.3)) \
                                .click() \
                                .perform()
                    elif self.enable_human_behavior:
                        ActionChains(driver) \
                            .move_by_offset(random.randint(200, 500), random.randint(300, 500)) \
                            .pause(random.uniform(0.1, 0.3)) \
                            .click() \
                            .perform()

                    time.sleep(random.uniform(1.5, 3.0))

                    # Close any ad popup windows that opened
                    all_windows = driver.window_handles
                    if len(all_windows) > 1:
                        for w in all_windows:
                            if w != main_window:
                                logger.info("    🚫 Closing ad popup window...")
                                driver.switch_to.window(w)
                                driver.close()
                        driver.switch_to.window(main_window)
                        logger.info("    ✅ Ad popup closed — resuming normally")
                        time.sleep(random.uniform(0.5, 1.0))
                    else:
                        logger.info("    ✅ No ad popup triggered — continuing")
                except Exception as e:
                    logger.debug(f"    Ad trigger click error: {e}")
                    try:
                        driver.switch_to.window(driver.window_handles[0])
                    except Exception:
                        pass

                # Human-like scrolling to trigger lazy loading
                try:
                    from human_behavior import HumanBehavior
                    if self.enable_human_behavior:
                        human = HumanBehavior(min_delay=0.2, max_delay=0.8, movement_speed='medium')
                        logger.info("    📜 Human-like scrolling...")

                        human.read_pause(1.0, 2.5)
                        for _ in range(random.randint(3, 5)):
                            if driver_lock:
                                with driver_lock:
                                    human.human_scroll(driver, 'down',
                                                       amount=random.randint(200, 600), smooth=True)
                            else:
                                human.human_scroll(driver, 'down',
                                                   amount=random.randint(200, 600), smooth=True)
                            time.sleep(random.uniform(0.5, 1.5))

                        human.human_scroll(driver, 'down',
                                           amount=random.randint(1500, 3000), smooth=True)
                        human.read_pause(1.0, 2.0)
                        driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")
                        time.sleep(random.uniform(1.0, 2.0))
                        human.human_scroll(driver, 'down',
                                           amount=random.randint(1500, 3000), smooth=True)
                        logger.info("    ✅ Scrolling complete")
                    else:
                        logger.info("    📜 Human behavior disabled — using basic scrolling")
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, 0)")
                        time.sleep(1)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(2)
                except ImportError:
                    # Fallback basic scrolling
                    logger.info("    📜 Basic scrolling...")
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(4)
                    driver.execute_script("window.scrollTo(0, 0)")
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(4)

                # Force lazy images to load
                logger.info("    🔄 Forcing lazy images...")
                driver.execute_script("""
                    document.querySelectorAll('img[data-src]').forEach(img => {
                        if (img.getAttribute('data-src')) {
                            img.src = img.getAttribute('data-src');
                        }
                    });
                    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
                        img.loading = 'eager';
                    });
                """)
                time.sleep(2)

            else:
                # ── NON-CF FLOW: Standard approach ──
                time.sleep(random.uniform(2.0, 4.0))

                if CloudflareHandler and CloudflareHandler.is_challenge_page_selenium(driver):
                    result['cloudflare'] = True
                    logger.info("    🛡️ Unexpected CF challenge (UC), waiting...")
                    if CloudflareHandler.wait_for_challenge_resolution_selenium(driver, timeout=90):
                        logger.info("    ✅ Cloudflare resolved (UC)!")
                        if self.cookie_mgr:
                            try:
                                self.cookie_mgr.save_cookies_selenium(driver, url)
                            except Exception:
                                pass
                        time.sleep(8)
                    else:
                        return result

                # Handle ads
                if self.ad_blocker:
                    try:
                        self.ad_blocker.handle_ads_selenium(driver, url)
                        self.ad_blocker.reset_stats()
                    except Exception:
                        pass

                # Scroll
                self._scroll_page_selenium(driver)

            # Extract images
            images = self._extract_images_selenium(driver, url)

            # ML fallback
            if len(images) < 3 and MLSiteLearner:
                try:
                    html = driver.page_source
                    ml_images = MLSiteLearner.analyze_dom_for_manga_images(html, driver.current_url)
                    if len(ml_images) > len(images):
                        images = ml_images
                except Exception:
                    pass

            if images:
                result['success'] = True
                result['image_urls'] = images

        except Exception as e:
            logger.debug(f"    UC method error: {e}")
        finally:
            # Stop popup closer if running
            if popup_closer_inst:
                try:
                    popup_closer_inst.stop_monitoring()
                except Exception:
                    pass
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

        return result

    # ─── Image Extraction Helpers ────────────────────────────────────

    def _extract_images_playwright(self, page, url: str) -> List[str]:
        """Extract manga image URLs from a Playwright page."""
        from urllib.parse import urljoin

        # Get site-specific selectors from database
        selectors = []
        if self.website_db:
            try:
                selectors = self.website_db.get_selectors(url)
            except Exception:
                pass

        # Add generic fallbacks
        selectors.extend([
            '.reading-content img',
            '.wp-manga-chapter-img',
            '#chapter-content img',
            '.chapter-images img',
            'img[data-src]',
            'img[src*="chapter"]',
            'img[src*="page"]',
            'img',
        ])

        image_urls = []
        seen = set()

        for selector in selectors:
            try:
                images = page.locator(selector).all()
                for img in images:
                    src = (
                        img.get_attribute('data-src') or
                        img.get_attribute('data-lazy-src') or
                        img.get_attribute('data-full-url') or
                        img.get_attribute('data-original') or
                        img.get_attribute('src')
                    )
                    if src and self._is_valid_image_url(src):
                        abs_src = urljoin(page.url, src) if not src.startswith('http') else src
                        if abs_src not in seen:
                            image_urls.append(abs_src)
                            seen.add(abs_src)
            except Exception:
                continue
            if image_urls:
                break

        return image_urls

    def _extract_images_selenium(self, driver, url: str) -> List[str]:
        """Extract manga image URLs from a Selenium driver."""
        from urllib.parse import urljoin

        image_urls = []
        seen = set()
        try:
            images = driver.find_elements(By.TAG_NAME, 'img') if By else []
            for img in images:
                src = (
                    img.get_attribute('data-src') or
                    img.get_attribute('data-lazy-src') or
                    img.get_attribute('data-full-url') or
                    img.get_attribute('data-original') or
                    img.get_attribute('src')
                )
                if src and self._is_valid_image_url(src):
                    abs_src = urljoin(driver.current_url, src) if not src.startswith('http') else src
                    if abs_src not in seen:
                        image_urls.append(abs_src)
                        seen.add(abs_src)
        except Exception as e:
            logger.debug(f"    Selenium image extraction error: {e}")

        return image_urls

    # ─── Scrolling ───────────────────────────────────────────────────

    def _scroll_page_playwright(self, page):
        """Scroll page to trigger lazy-loading with natural timing."""
        try:
            page.evaluate("""
                async () => {
                    await new Promise((resolve) => {
                        let totalHeight = 0;
                        const scrollHeight = document.body.scrollHeight;
                        const viewport = window.innerHeight;
                        const scroll = () => {
                            const distance = 200 + Math.floor(Math.random() * 200);
                            window.scrollBy({ top: distance, behavior: 'smooth' });
                            totalHeight += distance;
                            if (totalHeight >= scrollHeight - viewport) {
                                resolve();
                            } else {
                                setTimeout(scroll, 80 + Math.floor(Math.random() * 100));
                            }
                        };
                        scroll();
                    });
                }
            """)
            page.wait_for_timeout(random.randint(1500, 2500))
            # Scroll back to top then to bottom (triggers more lazy images)
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
            page.wait_for_timeout(random.randint(400, 800))
            page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
            page.wait_for_timeout(random.randint(1500, 2500))
        except Exception as e:
            logger.debug(f"    Scroll error (Playwright): {e}")

    def _scroll_page_selenium(self, driver):
        """Scroll page to trigger lazy-loading with natural timing."""
        try:
            total_height = driver.execute_script("return document.body.scrollHeight")
            current = 0
            while current < total_height:
                step = random.randint(200, 400)
                current += step
                driver.execute_script(f"window.scrollTo({{top: {min(current, total_height)}, behavior: 'smooth'}})")
                time.sleep(random.uniform(0.08, 0.18))

            time.sleep(random.uniform(1.5, 2.5))
            driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'})")
            time.sleep(random.uniform(0.5, 1.0))
            driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            logger.debug(f"    Scroll error (Selenium): {e}")

    # ─── Validation ──────────────────────────────────────────────────

    @staticmethod
    def _is_valid_image_url(url: str) -> bool:
        """Check if URL is likely a manga page image."""
        if not url:
            return False
        url_lower = url.lower()
        exclude = [
            'logo', 'avatar', 'icon', 'banner', 'button', 'background',
            'zeropixel', 'pixel', 'tracking', 'spacer', 'transparent',
            'gravatar', 'captcha', '/ads/',
        ]
        if any(kw in url_lower for kw in exclude):
            return False
        valid_exts = ['.jpg', '.jpeg', '.png', '.webp']
        if any(ext in url_lower.split('?')[0] for ext in valid_exts):
            return True
        if 'image' in url_lower or 'img' in url_lower:
            return True
        return False

    @staticmethod
    def _get_domain(url: str) -> str:
        try:
            netloc = urlparse(url).netloc
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            return netloc
        except Exception:
            return 'unknown'
