#!/usr/bin/env python3
"""
Integration Script for Manual Labels
Integrates manually labeled data with the existing ML training pipeline
"""

import json
import shutil
from pathlib import Path
import argparse
from datetime import datetime
import sys
import os

# Add the manga_pipeline directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from panel_ml_detector import TrainingDataManager
from import_training_data import import_training_data


def integrate_manual_labels(manual_labels_dir: Path, target_base_dir: Path = None):
    """
    Integrate manually labeled data into the training system
    
    Args:
        manual_labels_dir: Directory containing manually labeled JSON + image files
        target_base_dir: Base directory for MangaFactory (defaults to home/MangaFactory)
    """
    if target_base_dir is None:
        target_base_dir = Path.home() / 'MangaFactory'
    
    manual_labels_dir = Path(manual_labels_dir)
    
    if not manual_labels_dir.exists():
        print(f"Error: Manual labels directory does not exist: {manual_labels_dir}")
        return False
    
    # Find all JSON annotation files
    json_files = list(manual_labels_dir.glob('*.json'))
    print(f"Found {len(json_files)} annotation files in {manual_labels_dir}")
    
    if not json_files:
        print("No annotation files found. Looking for JSON files...")
        return False
    
    # Initialize training data manager
    training_manager = TrainingDataManager(target_base_dir)
    
    imported_count = 0
    
    for json_file in json_files:
        try:
            # Read the annotation
            with open(json_file, 'r', encoding='utf-8') as f:
                annotation = json.load(f)
            
            # Verify the annotation has required fields
            required_fields = ['image_path', 'panels']
            missing_fields = [field for field in required_fields if field not in annotation]
            
            if missing_fields:
                print(f"Warning: {json_file} missing fields: {missing_fields}. Skipping.")
                continue
            
            # Find the corresponding image file
            image_filename = annotation['image_path']
            image_path = manual_labels_dir / image_filename
            
            if not image_path.exists():
                # Try alternative extensions
                for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']:
                    alt_path = manual_labels_dir / f"{Path(image_filename).stem}{ext}"
                    if alt_path.exists():
                        image_path = alt_path
                        break
            
            if not image_path.exists():
                print(f"Warning: Image file not found for {json_file}: {image_path}. Skipping.")
                continue
            
            # Extract panels and quality scores
            panels = annotation.get('panels', [])
            quality_scores = annotation.get('quality_scores', [1.0] * len(panels))  # Assume perfect quality for manual labels
            
            # Save to training data
            success = training_manager.save_training_sample(
                image_path=image_path,
                panels=panels,
                quality_scores=quality_scores,
                source='manual_annotation'
            )
            
            if success:
                imported_count += 1
                print(f"✓ Integrated {image_path.name} with {len(panels)} panels")
            else:
                print(f"✗ Failed to integrate {image_path.name}")
                
        except Exception as e:
            print(f"✗ Error processing {json_file}: {e}")
    
    print(f"\nSuccessfully integrated {imported_count} manual annotation files")
    
    # Print current training stats
    stats = training_manager.get_training_stats()
    print(f"\nCurrent Training Stats:")
    print(f"  Total samples: {stats['total_samples']}")
    print(f"  User-provided: {stats['user_provided_samples']}")
    print(f"  Auto-validated: {stats['auto_validated_samples']}")
    print(f"  Pending samples: {stats['pending_samples']}")
    
    return imported_count > 0


def prepare_manual_labeling_session(output_dir: Path = None):
    """
    Prepare a directory for manual labeling session
    
    Args:
        output_dir: Directory to prepare (defaults to home/MangaFactory/manual_labeling)
    """
    if output_dir is None:
        output_dir = Path.home() / 'MangaFactory' / 'manual_labeling'
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    raw_dir = output_dir / 'raw_pages'
    raw_dir.mkdir(exist_ok=True)
    
    labeled_dir = output_dir / 'labeled_data'
    labeled_dir.mkdir(exist_ok=True)
    
    print(f"Manual labeling session prepared at: {output_dir}")
    print(f"  Raw pages directory: {raw_dir}")
    print(f"  Labeled data directory: {labeled_dir}")
    print(f"\nTo start labeling:")
    print(f"  1. Place manga page images in the 'raw_pages' directory")
    print(f"  2. Run the manual labeling tool to annotate panels")
    print(f"  3. Save labeled annotations to the 'labeled_data' directory")
    print(f"  4. Use this script to integrate the labeled data")


def train_model_if_needed(base_dir: Path = None):
    """
    Check if model training is needed and trigger training if sufficient data exists
    
    Args:
        base_dir: Base directory for MangaFactory (defaults to home/MangaFactory)
    """
    if base_dir is None:
        base_dir = Path.home() / 'MangaFactory'
    
    from panel_ml_detector import create_model_trainer
    
    trainer = create_model_trainer(base_dir)
    
    # Check if we have enough data to trigger training
    if trainer.training_root.exists():
        # Count available training images
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
        all_images = []
        
        # Look in both user_provided and auto_validated
        for subfolder in ['user_provided', 'auto_validated']:
            search_path = trainer.dataset_dir / subfolder
            if search_path.exists():
                for ext in image_extensions:
                    found = list(search_path.rglob(f"*{ext}"))
                    found += list(search_path.rglob(f"*{ext.upper()}"))
                    all_images.extend(found)
        
        print(f"Found {len(all_images)} training images")
        
        if len(all_images) >= 10:  # Minimum threshold for training
            print(f"Training model with {len(all_images)} images...")
            success = trainer.train_model(epochs=5)
            
            if success:
                print("✓ Model training completed successfully!")
            else:
                print("✗ Model training failed or was skipped")
        else:
            print(f"Not enough training data ({len(all_images)} < 10). Collect more labeled samples.")
    else:
        print(f"Training data directory does not exist: {trainer.training_root}")


def main():
    parser = argparse.ArgumentParser(
        description='Integrate manual labels with manga panel detection training pipeline'
    )
    parser.add_argument(
        '--integrate', 
        type=str, 
        help='Directory containing manually labeled JSON + image files to integrate'
    )
    parser.add_argument(
        '--prepare-session', 
        action='store_true', 
        help='Prepare a directory for a new manual labeling session'
    )
    parser.add_argument(
        '--session-dir', 
        type=str, 
        help='Directory for manual labeling session (default: ~/MangaFactory/manual_labeling)'
    )
    parser.add_argument(
        '--train-model', 
        action='store_true', 
        help='Train the ML model if sufficient data exists'
    )
    parser.add_argument(
        '--base-dir', 
        type=str, 
        help='Base directory for MangaFactory (default: ~/MangaFactory)'
    )
    
    args = parser.parse_args()
    
    base_dir = Path(args.base_dir) if args.base_dir else Path.home() / 'MangaFactory'
    
    if args.prepare_session:
        session_dir = Path(args.session_dir) if args.session_dir else None
        prepare_manual_labeling_session(session_dir)
    
    if args.integrate:
        integrate_manual_labels(Path(args.integrate), base_dir)
    
    if args.train_model:
        train_model_if_needed(base_dir)


if __name__ == "__main__":
    main()