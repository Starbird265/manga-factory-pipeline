#!/usr/bin/env python3
"""
COCO Format Converter
Converts manga panel annotations to COCO JSON format for Detectron2
"""

import json
import cv2
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class COCOConverter:
    """Convert annotations to COCO format"""
    
    # Class definitions
    CATEGORIES = [
        {"id": 1, "name": "panel", "supercategory": "manga_element"},
        {"id": 2, "name": "dialogue", "supercategory": "text"},
        {"id": 3, "name": "thought", "supercategory": "text"},
        {"id": 4, "name": "face", "supercategory": "character"},
        {"id": 5, "name": "sfx", "supercategory": "text"}
    ]
    
    def __init__(self):
        self.annotation_id = 1
        self.image_id = 1
        self.stats = {"images": 0, "annotations": 0}
    
    def convert_directory(self, input_dir: Path, output_file: Path, split_name: str = "train") -> Dict:
        """
        Convert directory of annotations to COCO format
        
        Args:
            input_dir: Directory with images/ and labels/ subdirectories
            output_file: Output JSON file
            split_name: Split name (train/val/test)
            
        Returns:
            COCO format dictionary
        """
        input_dir = Path(input_dir)
        images_dir = input_dir / "images" / split_name
        labels_dir = input_dir / "labels" / split_name
        
        if not images_dir.exists() or not labels_dir.exists():
            raise ValueError(f"Expected images/{split_name} and labels/{split_name} in {input_dir}")
        
        # Initialize COCO structure
        coco_data = {
            "info": {
                "description": "Manga Panel Detection Dataset",
                "version": "1.0",
                "year": datetime.now().year,
                "date_created": datetime.now().isoformat()
            },
            "licenses": [],
            "categories": self.CATEGORIES,
            "images": [],
            "annotations": []
        }
        
        # Get all images
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp']:
            image_files.extend(images_dir.glob(ext))
        
        logger.info(f"Converting {len(image_files)} images to COCO format...")
        
        for img_path in sorted(image_files):
            label_path = labels_dir / f"{img_path.stem}.txt"
            
            if not label_path.exists():
                logger.warning(f"No label for {img_path}, skipping")
                continue
            
            # Load image to get dimensions
            img = cv2.imread(str(img_path))
            if img is None:
                logger.warning(f"Cannot load {img_path}, skipping")
                continue
            
            height, width = img.shape[:2]
            
            # Add image info
            image_info = {
                "id": self.image_id,
                "file_name": str(img_path.relative_to(input_dir)),
                "width": width,
                "height": height
            }
            coco_data["images"].append(image_info)
            
            # Load and convert annotations
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    
                    class_id = int(parts[0]) + 1  # COCO uses 1-indexed
                    center_x, center_y, norm_w, norm_h = map(float, parts[1:5])
                    
                    # Convert to absolute bbox [x, y, width, height]
                    x = (center_x - norm_w / 2) * width
                    y = (center_y - norm_h / 2) * height
                    w = norm_w * width
                    h = norm_h * height
                    
                    # Create annotation
                    annotation = {
                        "id": self.annotation_id,
                        "image_id": self.image_id,
                        "category_id": class_id,
                        "bbox": [x, y, w, h],
                        "area": w * h,
                        "iscrowd": 0
                    }
                    coco_data["annotations"].append(annotation)
                    
                    self.annotation_id += 1
                    self.stats["annotations"] += 1
            
            self.image_id += 1
            self.stats["images"] += 1
        
        # Save to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(coco_data, f, indent=2)
        
        logger.info(f"Saved COCO annotations to {output_file}")
        
        return coco_data
    
    def print_stats(self):
        """Print conversion statistics"""
        print("\n" + "="*50)
        print("COCO Conversion Statistics")
        print("="*50)
        print(f"Images: {self.stats['images']}")
        print(f"Annotations: {self.stats['annotations']}")
        print("="*50 + "\n")


def convert_to_coco(input_dir: str, output_file: str, split: str = "train") -> Dict:
    """
    Convenience function to convert to COCO format
    
    Args:
        input_dir: Directory with images/ and labels/ subdirs
        output_file: Output JSON file
        split: Split name (train/val/test)
        
    Returns:
        COCO format dictionary
    """
    converter = COCOConverter()
    coco_data = converter.convert_directory(Path(input_dir), Path(output_file), split)
    converter.print_stats()
    return coco_data


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert to COCO format")
    parser.add_argument("input_dir", help="Directory with images/ and labels/ subdirs")
    parser.add_argument("output_file", help="Output JSON file")
    parser.add_argument("--split", default="train", help="Split name (train/val/test)")
    
    args = parser.parse_args()
    
    convert_to_coco(args.input_dir, args.output_file, args.split)
