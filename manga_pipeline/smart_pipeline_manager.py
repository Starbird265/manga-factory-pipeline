import json
import logging
import time
import threading
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse
from security_manager import SecurityManager

logger = logging.getLogger(__name__)

class SmartPipelineManager:
    """
    Learns and optimizes end-to-end processing per domain.
    Caches scraping strategies (requests vs playwright vs UC) and processing heuristics
    (skip_denoise, fast_ocr) to make the pipeline faster with every download.
    """
    def __init__(self, data_dir: str = '.', config_file: str = 'pipeline_stats.json'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_dir / config_file
        self.domain_stats: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self.security_mgr = SecurityManager(data_dir)

        self._load_stats()

    def _load_stats(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)

                if self.security_mgr.verify_data(data):
                    self.domain_stats = {k: v for k, v in data.items() if k != '_signature'}
                    logger.debug(f"Loaded secured pipeline intelligence for {len(self.domain_stats)} domains.")
                else:
                    # Versions before signed persistence stored plain local
                    # JSON. Treat that as a legacy cache, preserve the learned
                    # methods, then immediately re-sign it with the current
                    # key. Throwing it away makes every launch look like the
                    # first run and forces the full scraper chain again.
                    self.domain_stats = {
                        key: value
                        for key, value in data.items()
                        if key != '_signature' and isinstance(value, dict)
                    }
                    if self.domain_stats:
                        logger.warning(
                            "Pipeline memory has no valid signature; importing and re-signing the local cache."
                        )
                        self._save_stats()
                    else:
                        logger.warning("Pipeline memory is empty or malformed; starting fresh.")
            except Exception as e:
                logger.error(f"Failed to load pipeline stats: {e}")
                self.domain_stats = {}

    def _save_stats(self):
        with self._lock:
            try:
                temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
                signed_data = self.security_mgr.sign_data(self.domain_stats)
                with open(temp_path, 'w') as f:
                    json.dump(signed_data, f, indent=2)
                temp_path.replace(self.config_path)
            except Exception as e:
                logger.error(f"Failed to save pipeline stats: {e}")

    def _get_domain(self, url: str) -> str:
        try:
            netloc = urlparse(url).netloc
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            return netloc
        except:
            return "unknown_domain"

    def get_strategy(self, url: str) -> Dict[str, Any]:
        """
        Returns the optimal known strategies for a given domain.
        If unknown, returns safe defaults.
        """
        domain = self._get_domain(url)
        with self._lock:
            stats = self.domain_stats.get(domain, {})

        best_scraper = stats.get('best_scraper')
        # Older cache files used the library name; the unified runner uses the
        # short dispatch key. Normalize it before the engine builds its chain.
        if best_scraper == 'undetected_chromedriver':
            best_scraper = 'undetected_chrome'

        return {
            'best_scraper': best_scraper,
            'delay_needed': stats.get('min_delay', 0.5), # Standard small delay
            'skip_denoise': stats.get('clean_images', False), # False means OpenCV is skipped for speed
            'fast_ocr': stats.get('fast_ocr', False), # Skip Tesseract PSM 6 heavy config
            'success_rate': stats.get('success_rate', 1.0)
        }

    def record_scraper_result(self, url: str, scraper_name: str, success: bool, duration: float, is_cloudflare: bool = False):
        """
        Learn from a scraping attempt.
        """
        # Store the same method key used by UnifiedBypassEngine so the learned
        # strategy can be moved to the front of its next attempt.
        if scraper_name == 'undetected_chromedriver':
            scraper_name = 'undetected_chrome'
        domain = self._get_domain(url)
        with self._lock:
            if domain not in self.domain_stats:
                self.domain_stats[domain] = {
                    'attempts': 0,
                    'successes': 0,
                    'scrapers_tested': {},
                    'best_scraper': 'requests',
                    'clean_images': False,
                    'fast_ocr': False
                }

            stats = self.domain_stats[domain]
            stats['attempts'] += 1

            if scraper_name not in stats['scrapers_tested']:
                stats['scrapers_tested'][scraper_name] = {'successes': 0, 'failures': 0, 'avg_duration': 100.0}

            scraper_stats = stats['scrapers_tested'][scraper_name]

            if success:
                stats['successes'] += 1
                scraper_stats['successes'] += 1
                # Exponential moving average of speed
                alpha = 0.3
                scraper_stats['avg_duration'] = (alpha * duration) + ((1 - alpha) * scraper_stats['avg_duration'])

                # A successful scraper becomes the preference whenever the
                # current preference has no proven win or has already failed.
                # This avoids retrying requests on every chapter after a
                # browser method has demonstrated that the site needs it.
                current_best = stats.get('best_scraper')
                current_stats = stats.get('scrapers_tested', {}).get(current_best, {})
                current_has_proven_win = (
                    current_stats.get('successes', 0) > current_stats.get('failures', 0)
                )

                if scraper_name == 'requests':
                    stats['best_scraper'] = 'requests'
                elif not current_has_proven_win:
                    stats['best_scraper'] = scraper_name

            else:
                scraper_stats['failures'] += 1
                # If current best scraper failed heavily, demote it
                if stats['best_scraper'] == scraper_name and scraper_stats['failures'] > 2:
                    if scraper_name == 'requests':
                        stats['best_scraper'] = 'playwright' # Escalate
                    elif scraper_name == 'playwright':
                        stats['best_scraper'] = 'undetected_chrome' # Escalate

                # Add delay if Cloudflare tripped
                if is_cloudflare:
                    stats['min_delay'] = min(stats.get('min_delay', 0.5) + 1.0, 10.0)

            stats['success_rate'] = stats['successes'] / max(1, stats['attempts'])

        # Periodically flush
        self._save_stats()

    def record_processing_result(self, url: str, is_high_quality: bool, text_density: float):
        """
        Learn from the cleaning/OCR phases.
        If images are consistently high quality, skip OpenCV denoising to save massive CPU time.
        If text density is low (action panels), use fast OCR.
        """
        domain = self._get_domain(url)
        with self._lock:
            if domain not in self.domain_stats:
                return # Should have been created by scraper result

            stats = self.domain_stats[domain]

            # Update image quality metric
            current_hq_score = stats.get('_hq_streak', 0)
            if is_high_quality:
                current_hq_score += 1
            else:
                current_hq_score -= 1

            stats['_hq_streak'] = max(-5, min(10, current_hq_score))

            # If we have 3 high quality chapters in a row from this site, we can safely skip denoising
            stats['clean_images'] = (stats['_hq_streak'] > 2)

            # Text density logic
            current_td = stats.get('avg_text_density', 0.5)
            stats['avg_text_density'] = (0.3 * text_density) + (0.7 * current_td)

            # If text is very sparse, use fast OCR settings
            stats['fast_ocr'] = (stats['avg_text_density'] < 0.1)

        self._save_stats()
