import logging
import concurrent.futures
import threading
from typing import List, Dict, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    """
    Manages the concurrent processing of multiple manga chapters.
    Instead of downloading sequentially, it uses a ThreadPool to process
    multiple chapters at once, maximizing bandwidth and CPU usage.
    """
    def __init__(self, max_concurrent_downloads: int = 3):
        self.max_workers = max_concurrent_downloads
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        self.futures = []
        self.results = []
        self._lock = threading.Lock()
        
    def submit_chapter(self, factory_creator_func: Callable, url: str, kwargs: Dict):
        """
        Submits a single chapter url to be processed by an isolated MangaFactory instance.
        """
        future = self.executor.submit(self._process_single_chapter, factory_creator_func, url, kwargs)
        self.futures.append(future)
        return future
        
    def _process_single_chapter(self, factory_creator_func: Callable, url: str, kwargs: Dict) -> Dict:
        """
        Worker thread function that instantiates a MangaFactory and runs its pipeline.
        """
        result = {
            'url': url,
            'success': False,
            'stages_completed': [],
            'error': None
        }
        
        try:
            logger.info(f"[ORCHESTRATOR] Starting pipeline for {url}")
            
            # Instantiate isolated factory for this thread
            factory = factory_creator_func(url=url, **kwargs)
            
            # Step 1: Download
            if not kwargs.get('skip_download', False):
                logger.info(f"[{url}] === DOWNLOAD PHASE ===")
                if not factory.download_chapter(url):
                    raise Exception("Download failed")
                result['stages_completed'].append('download')
                
            # Step 2: Clean
            if not kwargs.get('skip_clean', False):
                logger.info(f"[{url}] === CLEANING PHASE ===")
                if not factory.clean_pages_enhanced():
                    raise Exception("Cleaning failed")
                result['stages_completed'].append('clean')
                
            # Step 3: Stitching
            if not kwargs.get('skip_stitch', False):
                logger.info(f"[{url}] === STITCHING PHASE ===")
                factory.process_stitching_enhanced(
                    force_format=kwargs.get('force_format'),
                    extract_single_panels=kwargs.get('stitch_extract_panels', False)
                )
                result['stages_completed'].append('stitch')
                
            # Step 4: Panel Extraction
            if not kwargs.get('skip_slice', False):
                logger.info(f"[{url}] === PANEL EXTRACTION PHASE ===")
                if not factory.extract_panels_enhanced(skip_validation=False):
                    raise Exception("Panel extraction failed")
                result['stages_completed'].append('slice')
                
            # Step 5: OCR
            if not kwargs.get('skip_ocr', False):
                logger.info(f"[{url}] === OCR PHASE ===")
                factory.process_ocr_enhanced(
                    ocr_lang=kwargs.get('ocr_lang', 'eng'),
                    confidence_threshold=kwargs.get('ocr_confidence', 60),
                    preprocessing_mode=kwargs.get('ocr_mode', 'medium'),
                    save_preprocessed=kwargs.get('save_preprocessed', False)
                )
                result['stages_completed'].append('ocr')
                
            # Step 6: Script Generation
            logger.info(f"[{url}] === SCRIPT GENERATION PHASE ===")
            if kwargs.get('ai_script', False):
                factory.generate_ai_enhanced_script(
                    chapter_title=kwargs.get('chapter_title', ''),
                    series_context=kwargs.get('series_context', ''),
                    gemini_api_key=kwargs.get('gemini_api_key', None)
                )
            else:
                factory.generate_script_enhanced(add_emotions=kwargs.get('emotion', False))
            result['stages_completed'].append('script')
            
            result['success'] = True
            logger.info(f"[ORCHESTRATOR] Successfully completed pipeline for {url}")
            
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Pipeline failed for {url}: {str(e)}")
            result['error'] = str(e)
            
        with self._lock:
            self.results.append(result)
            
        return result
        
    def wait_all(self) -> List[Dict]:
        """
        Wait for all submitted chapters to finish processing.
        """
        logger.info(f"[ORCHESTRATOR] Waiting for {len(self.futures)} chapters to complete...")
        concurrent.futures.wait(self.futures)
        logger.info("[ORCHESTRATOR] All chapters processed.")
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        return self.results
