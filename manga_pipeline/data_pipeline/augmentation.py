#!/usr/bin/env python3
"""
Data Augmentation Pipeline
Augment manga panel dataset with transformations while preserving bounding boxes
"""

import cv2
import numpy as np
import random
from pathlib import Path
from typing import List, Dict, Tuple
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataAugmenter:
    """Augment dataset with various transformations"""
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)
        self.stats = {"augmented": 0, "skipped": 0}
    
    def augment_brightness_contrast(self, image: np.ndarray,
                                    brightness_range: Tuple[float, float] = (0.7, 1.3),
                                    contrast_range: Tuple[float, float] = (0.8, 1.2)) -> np.ndarray:
        """Adjust brightness and contrast"""
        brightness = random.uniform(*brightness_range)
        contrast = random.uniform(*contrast_range)
        
        # Apply transformations
        image = cv2.convertScaleAbs(image, alpha=contrast, beta=(brightness - 1) * 50)
        return image
    
    def add_gaussian_noise(self, image: np.ndarray, sigma: float = 10) -> np.ndarray:
        """Add Gaussian noise"""
        noise = np.random.normal(0, sigma, image.shape).astype(np.uint8)
        noisy_image = cv2.add(image, noise)
        return noisy_image
    
    def horizontal_flip(self, image: np.ndarray, boxes: List[Dict]) -> Tuple[np.ndarray, List[Dict]]:
        """
        Flip image horizontally and adjust bounding boxes
        Note: Only flip non-text classes (panel, face)
        """
        h, w = image.shape[:2]
        flipped_image = cv2.flip(image, 1)
        
        flipped_boxes = []
        for box in boxes:
            # Skip text-based classes (dialogue, thought, sfx)
            if box['class'] in ['dialogue', 'thought', 'sfx']:
                continue
            
            # Flip x coordinates
            x = box['x']
            width = box['width']
            new_x = w - (x + width)
            
            flipped_boxes.append({
                'x': int(new_x),
                'y': box['y'],
                'width': width,
                'height': box['height'],
                'class': box['class']
            })
        
        return flipped_image, flipped_boxes
    
    def augment_single_image(self, image_path: Path, label_path: Path,
                            output_images_dir: Path, output_labels_dir: Path,
                            augmentation_types: List[str] = ['brightness', 'noise']) -> int:
        """
        Augment a single image with multiple transformations
        
        Args:
            image_path: Path to image
            label_path: Path to YOLO label file
            output_images_dir: Output directory for augmented images
            output_labels_dir: Output directory for augmented labels
            augmentation_types: List of augmentation types to apply
            
        Returns:
            Number of augmented images created
        """
        try:
            # Load image
            image = cv2.imread(str(image_path))
            if image is None:
                logger.warning(f"Cannot load image: {image_path}")
                return 0
            
            h, w = image.shape[:2]
            
            # Load labels (YOLO format)
            boxes_yolo = []
            boxes_abs = []
            
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    
                    class_id = int(parts[0])
                    center_x, center_y, norm_w, norm_h = map(float, parts[1:5])
                    
                    # Convert to absolute coordinates
                    x = int((center_x - norm_w / 2) * w)
                    y = int((center_y - norm_h / 2) * h)
                    width = int(norm_w * w)
                    height = int(norm_h * h)
                    
                    # Map class_id to class name
                    class_names = ['panel', 'dialogue', 'thought', 'face', 'sfx']
                    class_name = class_names[class_id] if class_id < len(class_names) else 'panel'
                    
                    boxes_abs.append({
                        'x': x, 'y': y, 'width': width, 'height': height,
                        'class': class_name, 'class_id': class_id
                    })
                    boxes_yolo.append(line.strip())
            
            count = 0
            output_images_dir.mkdir(parents=True, exist_ok=True)
            output_labels_dir.mkdir(parents=True, exist_ok=True)
            
            # Original image (just copy)
            stem = image_path.stem
            
            # Apply augmentations
            if 'brightness' in augmentation_types:
                aug_image = self.augment_brightness_contrast(image.copy())
                aug_name = f"{stem}_bright"
                cv2.imwrite(str(output_images_dir / f"{aug_name}{image_path.suffix}"), aug_image)
                
                # Save same labels
                with open(output_labels_dir / f"{aug_name}.txt", 'w') as f:
                    f.write('\n'.join(boxes_yolo))
                count += 1
            
            if 'noise' in augmentation_types:
                aug_image = self.add_gaussian_noise(image.copy())
                aug_name = f"{stem}_noise"
                cv2.imwrite(str(output_images_dir / f"{aug_name}{image_path.suffix}"), aug_image)
                
                # Save same labels
                with open(output_labels_dir / f"{aug_name}.txt", 'w') as f:
                    f.write('\n'.join(boxes_yolo))
                count += 1
            
            if 'flip' in augmentation_types:
                flip_image, flip_boxes = self.horizontal_flip(image.copy(), boxes_abs)
                
                # Only save if we have boxes after filtering
                if flip_boxes:
                    aug_name = f"{stem}_flip"
                    cv2.imwrite(str(output_images_dir / f"{aug_name}{image_path.suffix}"), flip_image)
                    
                    # Convert boxes back to YOLO format
                    flip_h, flip_w = flip_image.shape[:2]
                    yolo_lines = []
                    for box in flip_boxes:
                        center_x = (box['x'] + box['width'] / 2) / flip_w
                        center_y = (box['y'] + box['height'] / 2) / flip_h
                        norm_w = box['width'] / flip_w
                        norm_h = box['height'] / flip_h
                        
                        yolo_lines.append(
                            f"{box['class_id']} {center_x:.6f} {center_y:.6f} {norm_w:.6f} {norm_h:.6f}"
                        )
                    
                    with open(output_labels_dir / f"{aug_name}.txt", 'w') as f:
                        f.write('\n'.join(yolo_lines))
                    count += 1
            
            self.stats["augmented"] += count
            return count
            
        except Exception as e:
            logger.error(f"Error augmenting {image_path}: {e}")
            self.stats["skipped"] += 1
            return 0
    
    def augment_dataset(self, input_dir: Path, output_dir: Path,
                       augmentation_types: List[str] = ['brightness', 'noise', 'flip'],
                       augment_train_only: bool = True) -> Dict:
        """
        Augment entire dataset
        
        Args:
            input_dir: Input directory with images/ and labels/ subdirs (with train/val/test splits)
            output_dir: Output directory for augmented dataset
            augmentation_types: List of augmentation types
            augment_train_only: If True, only augment training set
            
        Returns:
            Statistics dictionary
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        
        splits = ['train', 'val', 'test'] if not augment_train_only else ['train']
        
        for split in splits:
            images_input = input_dir / "images" / split
            labels_input = input_dir / "labels" / split
            
            if not images_input.exists() or not labels_input.exists():
                logger.warning(f"Split {split} not found, skipping")
                continue
            
            images_output = output_dir / "images" / split
            labels_output = output_dir / "labels" / split
            
            # Get all images
            image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp']:
                image_files.extend(images_input.glob(ext))
            
            logger.info(f"Augmenting {len(image_files)} images in {split} split...")
            
            for img_path in image_files:
                label_path = labels_input / f"{img_path.stem}.txt"
                
                if not label_path.exists():
                    logger.warning(f"No label for {img_path}, skipping")
                    continue
                
                # First, copy original
                import shutil
                images_output.mkdir(parents=True, exist_ok=True)
                labels_output.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img_path, images_output / img_path.name)
                shutil.copy2(label_path, labels_output / label_path.name)
                
                # Then augment
                self.augment_single_image(
                    img_path, label_path,
                    images_output, labels_output,
                    augmentation_types
                )
        
        # Copy data.yaml if exists
        if (input_dir / "data.yaml").exists():
            import shutil
            shutil.copy2(input_dir / "data.yaml", output_dir / "data.yaml")
        
        return dict(self.stats)
    
    def print_stats(self):
        """Print augmentation statistics"""
        print("\n" + "="*50)
        print("Data Augmentation Statistics")
        print("="*50)
        print(f"Augmented images: {self.stats['augmented']}")
        print(f"Skipped images: {self.stats['skipped']}")
        print("="*50 + "\n")


def augment_dataset(input_dir: str, output_dir: str,
                   types: List[str] = None,
                   train_only: bool = True,
                   seed: int = 42) -> Dict:
    """
    Convenience function to augment dataset
    
    Args:
        input_dir: Input directory with train/val/test splits
        output_dir: Output directory
        types: Augmentation types (default: ['brightness', 'noise', 'flip'])
        train_only: Only augment training set
        seed: Random seed
        
    Returns:
        Statistics dictionary
    """
    if types is None:
        types = ['brightness', 'noise', 'flip']
    
    augmenter = DataAugmenter(seed=seed)
    stats = augmenter.augment_dataset(Path(input_dir), Path(output_dir), types, train_only)
    augmenter.print_stats()
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Augment manga dataset")
    parser.add_argument("input_dir", help="Input directory with train/val/test splits")
    parser.add_argument("output_dir", help="Output directory for augmented dataset")
    parser.add_argument("--types", nargs='+', default=['brightness', 'noise', 'flip'],
                       help="Augmentation types (default: brightness noise flip)")
    parser.add_argument("--all-splits", action='store_true',
                       help="Augment all splits (default: train only)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    
    args = parser.parse_args()
    
    augment_dataset(args.input_dir, args.output_dir, args.types, not args.all_splits, args.seed)
