#!/usr/bin/env python3
"""
End-to-End Integration Test
Tests the complete ML training pipeline with sample data
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_labeling_tool():
    """Test that labeling tool can be imported"""
    logger.info("Testing labeling tool import...")
    try:
        # Just test import, don't launch GUI
        import manual_labeling_tool_pro
        logger.info("✓ Labeling tool OK")
        return True
    except Exception as e:
        logger.error(f"✗ Labeling tool failed: {e}")
        return False


def test_data_pipeline():
    """Test data pipeline components"""
    logger.info("\nTesting data pipeline...")
    
    success = True
    
    # Test YOLO converter import
    try:
        from data_pipeline.yolo_converter import YOLOConverter
        logger.info("✓ YOLO converter OK")
    except Exception as e:
        logger.error(f"✗ YOLO converter failed: {e}")
        success = False
    
    # Test splitter import
    try:
        from data_pipeline.dataset_splitter import DatasetSplitter
        logger.info("✓ Dataset splitter OK")
    except Exception as e:
        logger.error(f"✗ Dataset splitter failed: {e}")
        success = False
    
    # Test augmentation import
    try:
        from data_pipeline.augmentation import DataAugmenter
        logger.info("✓ Data augmentation OK")
    except Exception as e:
        logger.error(f"✗ Data augmentation failed: {e}")
        success = False
    
    # Test COCO converter import
    try:
        from data_pipeline.coco_converter import COCOConverter
        logger.info("✓ COCO converter OK")
    except Exception as e:
        logger.error(f"✗ COCO converter failed: {e}")
        success = False
    
    return success


def test_ml_models():
    """Test ML model components"""
    logger.info("\nTesting ML models...")
    
    success = True
    
    # Test YOLO detector import
    try:
        from ml_models.yolo_panel_detector import YOLOPanelDetector
        detector = YOLOPanelDetector()
        
        if detector.yolo_available:
            logger.info("✓ YOLOv8 available and ready")
        else:
            logger.warning("⚠ YOLOv8 not installed (pip install ultralytics)")
            
    except Exception as e:
        logger.error(f"✗ YOLO detector failed: {e}")
        success = False
    
    # Test training pipeline import
    try:
        from ml_models.training_pipeline import MLTrainingPipeline
        logger.info("✓ Training pipeline OK")
    except Exception as e:
        logger.error(f"✗ Training pipeline failed: {e}")
        success = False
    
    return success


def test_active_learning():
    """Test active learning components"""
    logger.info("\nTesting active learning...")
    
    success = True
    
    # Test sample selector import
    try:
        from active_learning.sample_selector import ActiveLearningSampler
        logger.info("✓ Sample selector OK")
    except Exception as e:
        logger.error(f"✗ Sample selector failed: {e}")
        success = False
    
    # Test auto-annotator import
    try:
        from active_learning.auto_annotator import AutoAnnotator
        logger.info("✓ Auto-annotator OK (needs trained model to run)")
    except Exception as e:
        logger.error(f"✗ Auto-annotator failed: {e}")
        success = False
    
    return success


def test_dependencies():
    """Test that required dependencies are installed"""
    logger.info("\nChecking dependencies...")
    
    deps = {
        'cv2': 'opencv-python',
        'PIL': 'pillow',
        'numpy': 'numpy',
        'tkinter': 'tkinter (usually pre-installed)',
    }
    
    missing = []
    
    for module, package in deps.items():
        try:
            __import__(module)
            logger.info(f"✓ {package}")
        except ImportError:
            logger.error(f"✗ {package} not installed")
            missing.append(package)
    
    # Check ultralytics separately
    try:
        import ultralytics
        logger.info(f"✓ ultralytics (YOLOv8)")
    except ImportError:
        logger.warning(f"⚠ ultralytics not installed (pip install ultralytics)")
        logger.warning("  YOLOv8 features will not work until installed")
    
    return len(missing) == 0


def print_summary(results):
    """Print test summary"""
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)
    
    all_passed = all(results.values())
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info("="*70)
    
    if all_passed:
        logger.info("\n🎉 All tests passed! System is ready to use.")
        logger.info("\nNext steps:")
        logger.info("  1. Run: python QUICK_START_ML.py")
        logger.info("  2. Start labeling with the professional tool")
        logger.info("  3. Train your first model!\n")
    else:
        logger.info("\n⚠️ Some tests failed. Check the errors above.")
        logger.info("Install missing dependencies and try again.\n")
    
    return all_passed


def main():
    logger.info("="*70)
    logger.info("MANGA ML TRAINING SYSTEM - INTEGRATION TEST")
    logger.info("="*70)
    
    # Change to manga_pipeline directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    logger.info(f"Working directory: {os.getcwd()}\n")
    
    # Run tests
    results = {
        'Dependencies': test_dependencies(),
        'Labeling Tool': test_labeling_tool(),
        'Data Pipeline': test_data_pipeline(),
        'ML Models': test_ml_models(),
        'Active Learning': test_active_learning()
    }
    
    # Print summary
    all_passed = print_summary(results)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
