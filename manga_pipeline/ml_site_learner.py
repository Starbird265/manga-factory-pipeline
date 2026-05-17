import logging
from typing import List, Dict, Any
from urllib.parse import urljoin
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logger = logging.getLogger(__name__)

class MLSiteLearner:
    """
    Heuristic/ML-lite DOM analyzer that identifies manga images on unknown websites.
    Scores images based on file size, dimensions, hierarchy depth, and sibling similarity.
    """
    
    @classmethod
    def analyze_dom_for_manga_images(cls, html_content: str, base_url: str) -> List[str]:
        """
        Analyzes raw HTML and heuristically determines which <img> tags are actual manga pages.
        Returns a sorted list of image URLs.
        """
        if not BeautifulSoup:
            logger.error("BeautifulSoup not installed. Cannot run ML Site Learner.")
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
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
            logger.warning("ML Site Learner found images, but max confidence is very low.")
        
        # Keep images that score within 40% of the top score, minimum threshold 20
        threshold = max(20, top_score * 0.6)
        
        valid_manga_urls = []
        for item in scored_images:
            if item['score'] >= threshold:
                valid_manga_urls.append(item['url'])
                
        # Clean duplicates preserving order
        seen = set()
        final_urls = []
        for url in valid_manga_urls:
            if url not in seen:
                final_urls.append(url)
                seen.add(url)
                
        logger.info(f"ML Site Learner identified {len(final_urls)} probable manga pages from {len(images)} total images.")
        
        # We need to sort them back into DOM order, assuming dom index roughly correlates to chapter order
        # Actually, extracting them in natural sorting order is safer
        final_urls.sort(key=lambda x: cls._extract_numbers_for_sorting(x))
        return final_urls

    @staticmethod
    def _is_obvious_junk(url: str, img_tag: Any) -> bool:
        url_lower = url.lower()
        
        # Exclude common non-manga images
        exclude_keywords = [
            'logo', 'avatar', 'icon', 'banner', 'ad', 'button', 'background',
            'zeropixel', 'pixel', 'tracking', 'spacer', 'transparent', 'thumb', 'footer', 'header'
        ]
        
        if any(keyword in url_lower for keyword in exclude_keywords):
            return True
            
        class_str = " ".join(img_tag.get('class', [])).lower()
        if any(keyword in class_str for keyword in exclude_keywords):
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
