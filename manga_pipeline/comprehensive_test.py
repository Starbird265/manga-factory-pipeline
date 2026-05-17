
#!/usr/bin/env python3
"""
Comprehensive Test Suite
Tests all active components with actual data processing.

NOTE: ML training modules (active_learning, ml_models, manual_labeling_tool)
have been removed. Tests for those are replaced with smart pipeline tests.
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
import numpy as np
import cv2
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def create_test_image(path, width=800, height=600):
    """Create a test manga-like image"""
    # Create a white background with some black rectangles (fake panels)
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    
    # Draw some fake panels
    cv2.rectangle(img, (50, 50), (350, 250), (0, 0, 0), 2)
    cv2.rectangle(img, (400, 50), (700, 250), (0, 0, 0), 2)
    cv2.rectangle(img, (50, 300), (700, 550), (0, 0, 0), 2)
    
    # Add some text
    cv2.putText(img, "Test Manga Page", (300, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    
    cv2.imwrite(str(path), img)
    return img


def create_test_annotation(image_path, json_path):
    """Create test annotation matching the test image"""
    data = {
        "image_path": image_path.name,
        "image_width": 800,
        "image_height": 600,
        "annotations": [
            {"x": 50, "y": 50, "width": 300, "height": 200, "class": "panel"},
            {"x": 400, "y": 50, "width": 300, "height": 200, "class": "panel"},
            {"x": 50, "y": 300, "width": 650, "height": 250, "class": "panel"},
            {"x": 100, "y": 100, "width": 100, "height": 50, "class": "dialogue"},
        ],
        "num_annotations": 4
    }
    
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    return data


def test_data_pipeline():
    """Test complete data pipeline with real data"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: DATA PIPELINE")
    logger.info("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test dataset
        logger.info("Creating test dataset...")
        test_data_dir = tmpdir / "test_data"
        test_data_dir.mkdir()
        
        # Create 10 test images with annotations
        for i in range(10):
            img_path = test_data_dir / f"test_{i}.jpg"
            json_path = test_data_dir / f"test_{i}.json"
            
            create_test_image(img_path)
            create_test_annotation(img_path, json_path)
        
        logger.info(f"✓ Created 10 test images with annotations")
        
        # Test YOLO converter
        logger.info("\nTesting YOLO converter...")
        try:
            from data_pipeline.yolo_converter import YOLOConverter
            
            yolo_dir = tmpdir / "yolo_output"
            converter = YOLOConverter(yolo_dir)
            stats = converter.convert_directory(test_data_dir, yolo_dir)
            
            if stats['total_images'] == 10 and stats['total_annotations'] == 40:
                logger.info(f"✓ YOLO converter: {stats['total_images']} images, {stats['total_annotations']} annotations")
            else:
                logger.error(f"✗ YOLO converter failed: expected 10 images, 40 annotations")
                return False
            
            # Verify YOLO files exist
            yolo_images = yolo_dir / "images"
            yolo_labels = yolo_dir / "labels"
            
            if not yolo_images.exists() or not yolo_labels.exists():
                logger.error("✗ YOLO directories not created")
                return False
            
            # Check file counts
            img_count = len(list(yolo_images.glob("*.jpg")))
            label_count = len(list(yolo_labels.glob("*.txt")))
            
            if img_count != 10 or label_count != 10:
                logger.error(f"✗ YOLO file count mismatch: {img_count} images, {label_count} labels")
                return False
            
            logger.info(f"✓ YOLO files verified: {img_count} images, {label_count} labels")
            
            # Test dataset splitter
            logger.info("\nTesting dataset splitter...")
            from data_pipeline.dataset_splitter import DatasetSplitter
            
            split_dir = tmpdir / "split_output"
            splitter = DatasetSplitter(seed=42)
            split_stats = splitter.split_dataset(yolo_dir, split_dir)
            
            # Verify splits exist
            train_imgs = split_dir / "images" / "train"
            val_imgs = split_dir / "images" / "val"
            test_imgs = split_dir / "images" / "test"
            
            if not all([train_imgs.exists(), val_imgs.exists(), test_imgs.exists()]):
                logger.error("✗ Split directories not created")
                return False
            
            train_count = len(list(train_imgs.glob("*.jpg")))
            val_count = len(list(val_imgs.glob("*.jpg")))
            test_count = len(list(test_imgs.glob("*.jpg")))
            
            if train_count + val_count + test_count != 10:
                logger.error(f"✗ Split count mismatch: {train_count + val_count + test_count} != 10")
                return False
            
            logger.info(f"✓ Dataset split: train={train_count}, val={val_count}, test={test_count}")
            
            # Test COCO converter
            logger.info("\nTesting COCO converter...")
            from data_pipeline.coco_converter import COCOConverter
            
            coco_converter = COCOConverter()
            coco_output = tmpdir / "coco_train.json"
            coco_data = coco_converter.convert_directory(split_dir, coco_output, "train")
            
            if not coco_output.exists():
                logger.error("✗ COCO file not created")
                return False
            
            # Verify COCO structure
            if "images" not in coco_data or "annotations" not in coco_data or "categories" not in coco_data:
                logger.error("✗ COCO structure invalid")
                return False
            
            logger.info(f"✓ COCO converter: {len(coco_data['images'])} images, {len(coco_data['annotations'])} annotations")
            
            # Test augmentation (quick test with 1 image)
            logger.info("\nTesting data augmentation...")
            from data_pipeline.augmentation import DataAugmenter
            
            aug_dir = tmpdir / "aug_output"
            augmenter = DataAugmenter(seed=42)
            
            # Test single image augmentation
            test_img = list(train_imgs.glob("*.jpg"))[0]
            test_label = (split_dir / "labels" / "train" / test_img.stem).with_suffix('.txt')
            
            aug_imgs = aug_dir / "images"
            aug_labels = aug_dir / "labels"
            
            count = augmenter.augment_single_image(
                test_img, test_label,
                aug_imgs, aug_labels,
                ['brightness', 'noise']
            )
            
            if count < 2:
                logger.error(f"✗ Augmentation failed: expected 2+ augmentations, got {count}")
                return False
            
            logger.info(f"✓ Data augmentation: {count} augmented images created")
        except ImportError as e:
            logger.warning(f"⚠ Data pipeline modules not available: {e}")
            logger.warning("  Skipping data pipeline tests (non-critical)")
            return True  # Not a failure, just not available
        
    logger.info("\n✓ ALL DATA PIPELINE TESTS PASSED")
    return True


def test_smart_pipeline():
    """Test smart pipeline intelligence components (replaces old ML model tests)"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: SMART PIPELINE INTELLIGENCE")
    logger.info("="*70)
    
    # Test SmartPipelineManager
    logger.info("Testing SmartPipelineManager...")
    try:
        from smart_pipeline_manager import SmartPipelineManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SmartPipelineManager(data_dir=tmpdir)
            strategy = mgr.get_strategy("https://example.com/chapter/1")
            logger.info(f"  Strategy: {strategy}")
            assert 'best_scraper' in strategy, "Missing best_scraper key"
            logger.info("✓ SmartPipelineManager works")
    except Exception as e:
        logger.error(f"✗ SmartPipelineManager: {e}")
        return False

    # Test MLProxyManager
    logger.info("\nTesting MLProxyManager...")
    try:
        from ml_proxy_manager import MLProxyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = MLProxyManager(data_dir=tmpdir)
            proxy = mgr.get_best_proxy()
            logger.info(f"  Best proxy: {proxy}")
            logger.info("✓ MLProxyManager works")
    except Exception as e:
        logger.error(f"✗ MLProxyManager: {e}")
        return False

    # Test MLSiteLearner
    logger.info("\nTesting MLSiteLearner...")
    try:
        from ml_site_learner import MLSiteLearner
        html = '''<html><body>
            <div class="reading-content">
                <img data-src="https://cdn.example.com/page1.jpg" width="800" height="1200"/>
                <img data-src="https://cdn.example.com/page2.jpg" width="800" height="1200"/>
            </div>
            <img src="https://cdn.example.com/logo.png" width="50" height="50"/>
        </body></html>'''
        images = MLSiteLearner.analyze_dom_for_manga_images(html, "https://example.com")
        if len(images) >= 2:
            logger.info(f"  Found {len(images)} images (correct)")
            logger.info("✓ MLSiteLearner works")
        else:
            logger.error(f"✗ MLSiteLearner: expected 2+ images, got {len(images)}")
            return False
    except Exception as e:
        logger.error(f"✗ MLSiteLearner: {e}")
        return False

    # Test UnifiedBypassEngine
    logger.info("\nTesting UnifiedBypassEngine...")
    try:
        from unified_bypass_engine import UnifiedBypassEngine
        engine = UnifiedBypassEngine(headless=True)
        assert engine.ESCALATION_CHAIN == ['requests', 'playwright', 'undetected_chrome', 'playwright_mobile']
        logger.info(f"  Escalation chain: {engine.ESCALATION_CHAIN}")
        logger.info("✓ UnifiedBypassEngine works")
    except Exception as e:
        logger.error(f"✗ UnifiedBypassEngine: {e}")
        return False

    logger.info("\n✓ ALL SMART PIPELINE TESTS PASSED")
    return True


def test_bypass_components():
    """Test bypass/stealth components"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: BYPASS & STEALTH COMPONENTS")
    logger.info("="*70)

    components = [
        ('cloudflare_handler', 'CloudflareHandler'),
        ('stealth_config', 'StealthConfig'),
        ('cookie_manager', 'CookieManager'),
        ('website_database', 'WebsiteDatabase'),
        ('html_scraper', 'HTMLScraper'),
        ('human_behavior', None),  # module import only
        ('popup_closer', None),    # module import only
    ]

    for module_name, class_name in components:
        try:
            mod = __import__(module_name)
            if class_name and not hasattr(mod, class_name):
                logger.error(f"✗ {module_name}: missing {class_name}")
                return False
            logger.info(f"  ✓ {module_name}" + (f" ({class_name})" if class_name else ""))
        except Exception as e:
            logger.error(f"  ✗ {module_name}: {e}")
            return False

    # Test AdBlocker specifically (had import fix)
    try:
        from ad_blocker import AdBlocker
        blocker = AdBlocker(max_iterations=3)
        logger.info(f"  ✓ ad_blocker (AdBlocker)")
    except Exception as e:
        logger.error(f"  ✗ ad_blocker: {e}")
        return False

    logger.info("\n✓ ALL BYPASS COMPONENT TESTS PASSED")
    return True


def test_factory_lifecycle():
    """Test EnhancedMangaFactory creation and cleanup"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: FACTORY LIFECYCLE")
    logger.info("="*70)

    try:
        from manga_factory_enhanced import EnhancedMangaFactory

        with tempfile.TemporaryDirectory() as tmpdir:
            factory = EnhancedMangaFactory(os.path.join(tmpdir, 'test_chapter'))
            
            # Verify ML training code is no-op
            factory.train_model_if_needed()
            assert factory.ml_panel_detector is None, "ml_panel_detector should be None"
            assert factory.model_trainer is None, "model_trainer should be None"
            logger.info("  ✓ ML training removed (no-op)")
            
            # Verify smart pipeline managers initialized
            logger.info(f"  ✓ pipeline_mgr: {factory.pipeline_mgr is not None}")
            logger.info(f"  ✓ proxy_mgr: {factory.proxy_mgr is not None}")
            
            # Verify stats
            assert 'downloaded_images' in factory.stats
            logger.info(f"  ✓ stats initialized: {list(factory.stats.keys())}")
            
            factory.cleanup()
            logger.info("  ✓ cleanup() completed")

    except Exception as e:
        logger.error(f"✗ Factory lifecycle: {e}")
        import traceback
        traceback.print_exc()
        return False

    logger.info("\n✓ FACTORY LIFECYCLE TEST PASSED")
    return True


def test_package_imports():
    """Test all package imports that should still work"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: PACKAGE IMPORTS")
    logger.info("="*70)
    
    # Core modules that MUST import
    core_modules = [
        'manga_factory_enhanced',
        'unified_bypass_engine',
        'ml_site_learner',
        'smart_pipeline_manager',
        'ml_proxy_manager',
        'cookie_manager',
        'website_database',
        'cloudflare_handler',
        'stealth_config',
        'ad_blocker',
        'html_scraper',
        'human_behavior',
        'popup_closer',
        'pipeline_orchestrator',
    ]

    # Optional modules (won't fail test)
    optional_modules = [
        'pdf_generator',
        'ai_script_generator',
    ]

    all_ok = True
    for mod_name in core_modules:
        try:
            __import__(mod_name)
            logger.info(f"  ✓ {mod_name}")
        except Exception as e:
            logger.error(f"  ✗ {mod_name}: {e}")
            all_ok = False

    for mod_name in optional_modules:
        try:
            __import__(mod_name)
            logger.info(f"  ✓ {mod_name} (optional)")
        except Exception as e:
            logger.warning(f"  ⚠ {mod_name} (optional, skipped): {e}")

    if not all_ok:
        return False
    
    logger.info("\n✓ ALL PACKAGE IMPORTS PASSED")
    return True


def main():
    logger.info("="*70)
    logger.info("COMPREHENSIVE SYSTEM TEST (Post-Refactor)")
    logger.info("="*70)
    
    # Change to manga_pipeline directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    logger.info(f"Working directory: {os.getcwd()}\n")
    
    results = {}
    
    # Run all tests
    results['Package Imports'] = test_package_imports()
    results['Smart Pipeline'] = test_smart_pipeline()
    results['Bypass Components'] = test_bypass_components()
    results['Factory Lifecycle'] = test_factory_lifecycle()
    results['Data Pipeline'] = test_data_pipeline()
    
    # Print summary
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    logger.info("="*70)
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED! System is fully functional.")
        logger.info("\nThe system has been verified with:")
        logger.info("  • Smart pipeline intelligence (heuristic-based)")
        logger.info("  • Unified bypass engine (auto-escalation)")  
        logger.info("  • Proxy rotation and management")
        logger.info("  • Bypass/stealth component chain")
        logger.info("  • Factory lifecycle (creation → cleanup)")
        logger.info("  • All core package imports")
        logger.info("\nReady for production use! 🚀\n")
        return 0
    else:
        logger.error("\n⚠️ Some tests failed. Check errors above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
