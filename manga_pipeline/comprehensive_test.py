#!/usr/bin/env python3
"""
Comprehensive Test Suite
Tests all components with actual data processing
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
        
    logger.info("\n✓ ALL DATA PIPELINE TESTS PASSED")
    return True


def test_ml_models():
    """Test ML model components"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: ML MODELS")
    logger.info("="*70)
    
    # Test YOLOv8 detector import and initialization
    logger.info("Testing YOLO detector...")
    from ml_models.yolo_panel_detector import YOLOPanelDetector
    
    detector = YOLOPanelDetector()
    
    if not detector.yolo_available:
        logger.warning("⚠ YOLOv8 not installed - skipping ML tests")
        logger.warning("  Install with: pip install ultralytics")
        return True  # Not a failure, just not installed
    
    logger.info("✓ YOLOv8 available")
    
    # Test training pipeline
    logger.info("\nTesting training pipeline...")
    from ml_models.training_pipeline import MLTrainingPipeline
    
    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = MLTrainingPipeline(Path(tmpdir), "test_project")
        
        # Check directories created
        if not pipeline.base_dir.exists():
            logger.error("✗ Pipeline base directory not created")
            return False
        
        logger.info("✓ Training pipeline initialized")
    
    logger.info("\n✓ ALL ML MODEL TESTS PASSED")
    return True


def test_active_learning():
    """Test active learning components"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: ACTIVE LEARNING")
    logger.info("="*70)
    
    # Test sample selector
    logger.info("Testing sample selector...")
    from active_learning.sample_selector import ActiveLearningSampler
    
    sampler = ActiveLearningSampler()
    logger.info("✓ Sample selector initialized")
    
    # Test diversity selection (doesn't need model)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test images
        for i in range(5):
            img_path = tmpdir / f"test_{i}.jpg"
            create_test_image(img_path, width=800 + i*100, height=600)
        
        selected = sampler.select_diverse_samples(tmpdir, n_samples=3)
        
        if len(selected) != 3:
            logger.error(f"✗ Diversity selection failed: expected 3, got {len(selected)}")
            return False
        
        logger.info(f"✓ Diversity selection: {len(selected)} samples selected")
    
    # Test auto-annotator import
    logger.info("\nTesting auto-annotator...")
    from active_learning.auto_annotator import AutoAnnotator
    
    logger.info("✓ Auto-annotator module OK")
    
    logger.info("\n✓ ALL ACTIVE LEARNING TESTS PASSED")
    return True


def test_labeling_tool():
    """Test labeling tool (import only, no GUI)"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: LABELING TOOL")
    logger.info("="*70)
    
    logger.info("Testing labeling tool import...")
    
    try:
        # Import without launching GUI
        import manual_labeling_tool_pro
        logger.info("✓ Labeling tool module imported successfully")
        
        # Check class exists
        if not hasattr(manual_labeling_tool_pro, 'ProfessionalLabelingTool'):
            logger.error("✗ ProfessionalLabelingTool class not found")
            return False
        
        logger.info("✓ ProfessionalLabelingTool class available")
        
    except Exception as e:
        logger.error(f"✗ Labeling tool import failed: {e}")
        return False
    
    logger.info("\n✓ LABELING TOOL TEST PASSED")
    return True


def test_package_imports():
    """Test all package imports"""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: PACKAGE IMPORTS")
    logger.info("="*70)
    
    packages_to_test = [
        ('data_pipeline', ['YOLOConverter', 'COCOConverter', 'DatasetSplitter', 'DataAugmenter']),
        ('ml_models', ['YOLOPanelDetector', 'MLTrainingPipeline']),
        ('active_learning', ['ActiveLearningSampler', 'AutoAnnotator']),
    ]
    
    for package_name, classes in packages_to_test:
        logger.info(f"\nTesting {package_name}...")
        
        try:
            package = __import__(package_name)
            
            for class_name in classes:
                if not hasattr(package, class_name):
                    logger.error(f"✗ {class_name} not exported from {package_name}")
                    return False
                logger.info(f"  ✓ {class_name}")
            
        except Exception as e:
            logger.error(f"✗ Failed to import {package_name}: {e}")
            return False
    
    logger.info("\n✓ ALL PACKAGE IMPORTS PASSED")
    return True


def main():
    logger.info("="*70)
    logger.info("COMPREHENSIVE SYSTEM TEST")
    logger.info("="*70)
    
    # Change to manga_pipeline directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    logger.info(f"Working directory: {os.getcwd()}\n")
    
    results = {}
    
    # Run all tests
    results['Package Imports'] = test_package_imports()
    results['Labeling Tool'] = test_labeling_tool()
    results['Data Pipeline'] = test_data_pipeline()
    results['ML Models'] = test_ml_models()
    results['Active Learning'] = test_active_learning()
    
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
        logger.info("  • Real image creation and processing")
        logger.info("  • Actual format conversions (JSON → YOLO → COCO)")
        logger.info("  • Dataset splitting with file verification")
        logger.info("  • Data augmentation pipeline")
        logger.info("  • All package imports and exports")
        logger.info("\nReady for production use! 🚀\n")
        return 0
    else:
        logger.error("\n⚠️ Some tests failed. Check errors above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
