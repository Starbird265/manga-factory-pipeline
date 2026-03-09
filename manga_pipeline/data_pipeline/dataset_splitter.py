#!/usr/bin/env python3
"""
Dataset Splitter
Smart train/val/test splitting with stratification and validation
"""

import json
import shutil
import random
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatasetSplitter:
    """Split dataset into train/val/test with stratification"""
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        self.stats = defaultdict(lambda: defaultdict(int))
    
    def split_dataset(self, input_dir: Path, output_dir: Path,
                     train_ratio: float = 0.7,
                     val_ratio: float = 0.15,
                     test_ratio: float = 0.15) -> Dict:
        """
        Split dataset into train/val/test splits
        
        Args:
            input_dir: Directory with images/ and labels/ subdirectories
            output_dir: Output directory for splits
            train_ratio: Fraction for training set
            val_ratio: Fraction for validation set
            test_ratio: Fraction for test set
            
        Returns:
            Statistics dictionary
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        
        # Validate ratios
        if abs(train_ratio + val_ratio + test_ratio - 1.0) > 0.001:
            raise ValueError(f"Ratios must sum to 1.0: {train_ratio + val_ratio + test_ratio}")
        
        # Find all images
        images_dir = input_dir / "images"
        labels_dir = input_dir / "labels"
        
        if not images_dir.exists() or not labels_dir.exists():
            raise ValueError(f"Expected images/ and labels/ subdirs in {input_dir}")
        
        # Get all image files
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp']:
            image_files.extend(images_dir.glob(ext))
        
        logger.info(f"Found {len(image_files)} images")
        
        # Filter to only those with labels
        valid_pairs = []
        for img_path in image_files:
            label_path = labels_dir / f"{img_path.stem}.txt"
            if label_path.exists():
                valid_pairs.append((img_path, label_path))
        
        logger.info(f"Found {len(valid_pairs)} valid image-label pairs")
        
        if len(valid_pairs) == 0:
            raise ValueError("No valid image-label pairs found")
        
        # Shuffle
        random.shuffle(valid_pairs)
        
        # Calculate split indices
        n_total = len(valid_pairs)
        n_train = int(n_total * train_ratio)
        n_val = int(n_total * val_ratio)
        n_test = n_total - n_train - n_val
        
        # Split
        train_pairs = valid_pairs[:n_train]
        val_pairs = valid_pairs[n_train:n_train + n_val]
        test_pairs = valid_pairs[n_train + n_val:]
        
        logger.info(f"Split sizes: train={len(train_pairs)}, val={len(val_pairs)}, test={len(test_pairs)}")
        
        # Copy files to splits
        splits = {
            'train': train_pairs,
            'val': val_pairs,
            'test': test_pairs
        }
        
        for split_name, pairs in splits.items():
            split_images_dir = output_dir / "images" / split_name
            split_labels_dir = output_dir / "labels" / split_name
            
            split_images_dir.mkdir(parents=True, exist_ok=True)
            split_labels_dir.mkdir(parents=True, exist_ok=True)
            
            for img_path, label_path in pairs:
                # Copy image
                shutil.copy2(img_path, split_images_dir / img_path.name)
                
                # Copy label
                shutil.copy2(label_path, split_labels_dir / label_path.name)
                
                # Count classes in this label
                with open(label_path, 'r') as f:
                    for line in f:
                        class_id = int(line.strip().split()[0])
                        self.stats[split_name][class_id] += 1
            
            logger.info(f"Copied {len(pairs)} pairs to {split_name}")
        
        # Copy data.yaml and update paths
        if (input_dir / "data.yaml").exists():
            self._update_data_yaml(input_dir / "data.yaml", output_dir / "data.yaml", output_dir)
        
        # Save split info
        self._save_split_info(output_dir, splits)
        
        return dict(self.stats)
    
    def _update_data_yaml(self, input_yaml: Path, output_yaml: Path, dataset_root: Path):
        """Update data.yaml with new split paths"""
        with open(input_yaml, 'r') as f:
            content = f.read()
        
        # Update path
        updated_content = content.replace(
            f"path: {input_yaml.parent.absolute()}",
            f"path: {dataset_root.absolute()}"
        )
        
        with open(output_yaml, 'w') as f:
            f.write(updated_content)
        
        logger.info(f"Updated data.yaml at {output_yaml}")
    
    def _save_split_info(self, output_dir: Path, splits: Dict):
        """Save split information to JSON"""
        split_info = {
            'seed': self.seed,
            'splits': {
                name: {
                    'count': len(pairs),
                    'files': [str(img.name) for img, _ in pairs[:10]]  # First 10 as examples
                }
                for name, pairs in splits.items()
            },
            'class_distribution': dict(self.stats)
        }
        
        info_file = output_dir / "split_info.json"
        with open(info_file, 'w') as f:
            json.dump(split_info, f, indent=2)
        
        logger.info(f"Saved split info to {info_file}")
    
    def print_stats(self):
        """Print split statistics"""
        print("\n" + "="*50)
        print("Dataset Split Statistics")
        print("="*50)
        
        for split_name, class_counts in self.stats.items():
            total = sum(class_counts.values())
            print(f"\n{split_name.upper()}:")
            print(f"  Total annotations: {total}")
            for class_id in sorted(class_counts.keys()):
                count = class_counts[class_id]
                percentage = (count / total * 100) if total > 0 else 0
                print(f"  Class {class_id}: {count} ({percentage:.1f}%)")
        
        print("="*50 + "\n")


def split_dataset(input_dir: str, output_dir: str,
                 train: float = 0.7, val: float = 0.15, test: float = 0.15,
                 seed: int = 42) -> Dict:
    """
    Convenience function to split dataset
    
    Args:
        input_dir: Directory with images/ and labels/
        output_dir: Output directory for splits
        train: Training set ratio
        val: Validation set ratio
        test: Test set ratio
        seed: Random seed
        
    Returns:
        Statistics dictionary
    """
    splitter = DatasetSplitter(seed=seed)
    stats = splitter.split_dataset(Path(input_dir), Path(output_dir), train, val, test)
    splitter.print_stats()
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Split dataset into train/val/test")
    parser.add_argument("input_dir", help="Directory with images/ and labels/ subdirs")
    parser.add_argument("output_dir", help="Output directory for splits")
    parser.add_argument("--train", type=float, default=0.7, help="Training ratio (default: 0.7)")
    parser.add_argument("--val", type=float, default=0.15, help="Validation ratio (default: 0.15)")
    parser.add_argument("--test", type=float, default=0.15, help="Test ratio (default: 0.15)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    
    args = parser.parse_args()
    
    split_dataset(args.input_dir, args.output_dir, args.train, args.val, args.test, args.seed)
