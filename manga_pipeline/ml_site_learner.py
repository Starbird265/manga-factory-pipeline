import logging
import json
from pathlib import Path
from typing import List, Dict, Any
from urllib.parse import urlparse, urljoin
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from security_manager import SecurityManager

logger = logging.getLogger(__name__)

class MLSiteLearner:
    """
    Heuristic/ML-lite DOM analyzer that identifies manga images on unknown websites.
    Secured with caching so it remembers the structure of a site once learned.
    """
    _cache = None
    _security_mgr = None
    _cache_path = Path("ml_site_profiles.json")

    @classmethod
    def _init_cache(cls):
        if cls._cache is not None:
            return

        cls._security_mgr = SecurityManager(".")
        cls._cache = {}
        if cls._cache_path.exists():
            try:
                with open(cls._cache_path, 'r') as f:
                    data = json.load(f)
                if cls._security_mgr.verify_data(data):
                    cls._cache = {k: v for k, v in data.items() if k != '_signature'}
                    logger.debug(f"Loaded secured ML site profiles for {len(cls._cache)} domains.")
                else:
                    # Preserve pre-signing local profiles, then rewrite them
                    # with the current key. Otherwise each startup forgets the
                    # selector learned for a site and re-runs full discovery.
                    cls._cache = {
                        key: value
                        for key, value in data.items()
                        if key != '_signature' and isinstance(value, dict)
                    }
                    if cls._cache:
                        logger.warning(
                            "ML site profiles have no valid signature; importing and re-signing the local cache."
                        )
                        cls._save_cache()
                    else:
                        logger.warning("ML site profile cache is empty or malformed; starting fresh.")
            except Exception as e:
                logger.error(f"Failed to load ML site profiles: {e}")

    @classmethod
    def _save_cache(cls):
        if cls._cache is None or not cls._security_mgr:
            return
        try:
            signed_data = cls._security_mgr.sign_data(cls._cache)
            temp_path = cls._cache_path.with_suffix(cls._cache_path.suffix + ".tmp")
            with open(temp_path, 'w') as f:
                json.dump(signed_data, f, indent=2)
            temp_path.replace(cls._cache_path)
        except Exception as e:
            logger.error(f"Failed to save ML site profiles: {e}")

    @classmethod
    def _get_domain(cls, url: str) -> str:
        try:
            netloc = urlparse(url).netloc
            if netloc.startswith('www.'):
                return netloc[4:]
            return netloc
        except:
            return "unknown"

    @classmethod
    def _deduce_selector(cls, valid_elements: List[Any]) -> str:
        """
        Analyzes the winning <img> tags and deduces a CSS selector that matches them.
        """
        if not valid_elements:
            return ""

        from collections import Counter
        class_counter = Counter()

        for img in valid_elements:
            classes = img.get('class', [])
            for c in classes:
                class_counter[c] += 1

        # If all images share a class, that's our golden selector
        total_imgs = len(valid_elements)
        for c, count in class_counter.most_common():
            if count == total_imgs and c not in ['img', 'lazy', 'lazyload']:
                return f"img.{c}"

        # Fallback to parent container tracking
        parent_class_counter = Counter()
        parent_id_counter = Counter()

        for img in valid_elements:
            parent = img.parent
            if parent:
                for c in parent.get('class', []):
                    parent_class_counter[c] += 1
                pid = parent.get('id')
                if pid:
                    parent_id_counter[pid] += 1

        for pid, count in parent_id_counter.most_common():
            if count == total_imgs:
                return f"#{pid} img"

        for c, count in parent_class_counter.most_common():
            if count == total_imgs:
                return f".{c} img"

        return "img" # Ultimate fallback, just find images (not ideal)


    @classmethod
    def analyze_dom_for_manga_images(cls, html_content: str, base_url: str) -> List[str]:
        """
        Analyzes raw HTML to extract manga pages. Uses a secured cache of deduced
        CSS selectors first. If the cache fails (DOM changed), it falls back to
        full ML heuristic scoring and re-learns the structure.
        """
        if not BeautifulSoup:
            logger.error("BeautifulSoup not installed. Cannot run ML Site Learner.")
            return []

        cls._init_cache()
        domain = cls._get_domain(base_url)
        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. FAST PATH: Check secured cache for known structure
        if domain in cls._cache:
            selector = cls._cache[domain].get('selector')
            if selector:
                cached_imgs = soup.select(selector)
                if len(cached_imgs) >= 3: # Must find at least a few pages to trust the cache
                    logger.info(f"ML Site Learner using cached structure '{selector}' for {domain} ({len(cached_imgs)} images)")
                    urls = []
                    for img in cached_imgs:
                        src = img.get('data-src') or img.get('data-lazy-src') or img.get('data-full-url') or img.get('src')
                        if src and not cls._is_obvious_junk(src, img):
                            urls.append(urljoin(base_url, src))

                    if len(urls) >= 3:
                        # Success with cache!
                        urls = list(dict.fromkeys(urls)) # dedup
                        urls.sort(key=lambda x: cls._extract_numbers_for_sorting(x))
                        return urls

                logger.warning(f"Cached structure '{selector}' failed for {domain} (Structure changed?). Re-learning...")

        # 2. SLOW PATH: Full ML Heuristic Evaluation
        images = soup.find_all('img')

        scored_images = []

        for idx, img in enumerate(images):
            # 1. Extract the best URL (Data-src usually holds the real image in lazy-loaded pages)
            src = (img.get('data-src') or
                   img.get('data-lazy-src') or
                   img.get('data-full-url') or
                   img.get('src') or "")

            if not src or cls._is_obvious_junk(src, img):
                continue

            src = urljoin(base_url, src)

            # 2. Score the image
            score = cls._score_image(img, idx, len(images))

            scored_images.append({
                'url': src,
                'score': score,
                'element': img
            })

        # 3. Filter and cluster
        # Manga pages usually have high scores and appear in clusters (siblings)
        # We find the threshold dynamically.
        if not scored_images:
            return []

        # Sort by score descending to find the top tier
        scored_images.sort(key=lambda x: x['score'], reverse=True)

        # If the top score is very low, we might not have found manga pages
        top_score = scored_images[0]['score']
        if top_score < 30:
            logger.warning("ML Site Learner found images, but max confidence is too low to trust.")
            return []

        # Keep images that score within 40% of the top score, minimum threshold 20
        threshold = max(20, top_score * 0.6)

        valid_manga_urls = []
        for item in scored_images:
            if item['score'] >= threshold:
                valid_manga_urls.append(item['url'])

        # Clean duplicates preserving order
        seen = set()
        final_urls = []
        valid_elements = []
        for item in scored_images:
            if item['score'] >= threshold:
                url = item['url']
                if url not in seen:
                    final_urls.append(url)
                    valid_elements.append(item['element'])
                    seen.add(url)

        logger.info(f"ML Site Learner identified {len(final_urls)} probable manga pages from {len(images)} total images.")

        # Deduce the best CSS selector for next time and save it securely
        best_selector = cls._deduce_selector(valid_elements)
        if best_selector and best_selector != "img":
            cls._cache[domain] = {'selector': best_selector}
            cls._save_cache()
            logger.info(f"ML Site Learner deduced and secured site structure for {domain}: '{best_selector}'")

        # We need to sort them back into DOM order, assuming dom index roughly correlates to chapter order
        # Actually, extracting them in natural sorting order is safer
        final_urls.sort(key=lambda x: cls._extract_numbers_for_sorting(x))
        return final_urls

    @staticmethod
    def _is_obvious_junk(url: str, img_tag: Any) -> bool:
        url_lower = url.lower()

        # Exclude common non-manga images
        exclude_keywords = [
            'logo', 'avatar', 'icon', 'banner', 'button', 'background',
            'zeropixel', 'pixel', 'tracking', 'spacer', 'transparent', 'thumb', 'footer', 'header'
        ]

        if any(keyword in url_lower for keyword in exclude_keywords):
            return True

        class_str = " ".join(img_tag.get('class', [])).lower()
        if any(keyword in class_str for keyword in exclude_keywords):
            return True

        # A bare "ad" substring wrongly excludes legitimate paths such as
        # "/upload/". Only reject the common ad-route and ad-server markers.
        if any(marker in url_lower for marker in ('/ad/', '/ads/', 'adserver', 'advertis')):
            return True

        # SVGs in readers are almost always reaction icons, UI controls, or
        # challenge artwork. They are not processable manga pages.
        path_without_query = url_lower.split('?', 1)[0]
        if path_without_query.endswith('.svg') or 'image/svg+xml' in url_lower:
            return True

        if not any(ext in url_lower.split('?')[0] for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            # It might be an image router lacking extension, but if it has 'gif', block it
            if '.gif' in url_lower or 'base64' in url_lower:
                return True

        return False

    @staticmethod
    def _score_image(img_tag: Any, dom_index: int, total_images: int) -> float:
        """
        Assigns a probability score (0-100+) that this image is a manga page.
        """
        score = 0.0

        # FACTOR 1: Class names
        class_str = " ".join(img_tag.get('class', [])).lower()
        good_classes = ['chapter-img', 'page', 'manga', 'reading', 'content-img', 'wp-manga']
        if any(keyword in class_str for keyword in good_classes):
            score += 40

        # FACTOR 2: ID
        id_str = img_tag.get('id', '').lower()
        if 'image' in id_str or 'page' in id_str:
            score += 20

        # FACTOR 3: Attributes indicating lazy loading (manga sites love lazy loading)
        if img_tag.get('data-src') or img_tag.get('data-lazy-src'):
            score += 30

        # Modern SSR readers often mark chapter pages explicitly instead of
        # using WordPress-style classes. These attributes are much stronger
        # evidence than generic page position or a UI icon's filename.
        if img_tag.has_attr('data-reader-page-image'):
            score += 80
        if img_tag.has_attr('data-reader-index'):
            score += 40

        # Real reader pages normally declare substantial rendered dimensions.
        try:
            width = int(img_tag.get('width') or 0)
            height = int(img_tag.get('height') or 0)
            if width >= 400 and height >= 600:
                score += 25
        except (TypeError, ValueError):
            pass

        # FACTOR 4: Parent containers
        parent = img_tag.parent
        if parent:
            parent_class = " ".join(parent.get('class', [])).lower()
            if 'reader' in parent_class or 'chapter' in parent_class or 'page' in parent_class:
                score += 30

        # FACTOR 5: Tree depth (Manga images are usually nested deeply inside a central container)
        # We approximate depth by counting parents
        depth = len(list(img_tag.parents))
        if depth > 5:
            score += 10

        # FACTOR 6: Position in DOM. Manga pages are rarely the first or last few images.
        if 0.1 < (dom_index / max(1, total_images)) < 0.9:
            score += 10

        return score

    @staticmethod
    def _extract_numbers_for_sorting(s: str) -> List[int]:
        """
        Extracts all numeric sequences from a string to allow for natural sorting.
        e.g. 'page-10.jpg' -> [10]
        """
        import re
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]
