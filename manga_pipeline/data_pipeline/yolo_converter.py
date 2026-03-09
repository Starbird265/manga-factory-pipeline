#!/usr/bin/env python3
"""
YOLO Format Converter
Converts manga panel annotations from JSON to YOLO format for training
Supports multi-class labels: panel, dialogue, thought, face, sfx
"""

import json
import shutil
from pathlib import Path
from typing import List, Dict, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YOLOConverter:
    """Convert annotations to YOLO format"""
    
    # Class mapping
    CLASS_MAPPING = {
        "panel": 0,
        "dialogue": 1,
        "thought": 2,
        "face": 3,
        "sfx": 4
    }
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.stats = {
            "total_images": 0,
            "total_annotations": 0,
            "class_counts": {cls: 0 for cls in self.CLASS_MAPPING.keys()},
            "errors": 0
        }
    
    def convert_annotation(self, json_path: Path, image_path: Path, 
                          output_labels_dir: Path, output_images_dir: Path) -> bool:
        """
        Convert a single JSON annotation to YOLO format
        
        Args:
            json_path: Path to JSON annotation file
            image_path: Path to source image
            output_labels_dir: Directory to save YOLO label files
            output_images_dir: Directory to copy images
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load JSON
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Get image dimensions
            img_width = data.get("image_width")
            img_height = data.get("image_height")
            
            if not img_width or not img_height:
                # Try to get from image
                import cv2
                img = cv2.imread(str(image_path))
                if img is None:
                    logger.error(f"Cannot load image: {image_path}")
                    return False
                img_height, img_width = img.shape[:2]
            
            # Convert annotations
            yolo_lines = []
            annotations = data.get("annotations", data.get("panels", []))
            
            for ann in annotations:
                # Get class
                class_name = ann.get("class", "panel")
                if class_name not in self.CLASS_MAPPING:
                    logger.warning(f"Unknown class '{class_name}', defaulting to 'panel'")
                    class_name = "panel"
                
                class_id = self.CLASS_MAPPING[class_name]
                
                # Get bbox
                x = ann.get("x", 0)
                y = ann.get("y", 0)
                w = ann.get("width", 0)
                h = ann.get("height", 0)
                
                if w <= 0 or h <= 0:
                    logger.warning(f"Invalid bbox in {json_path}: w={w}, h={h}")
                    continue
                
                # Convert to YOLO format (normalized center x, center y, width, height)
                center_x = (x + w / 2) / img_width
                center_y = (y + h / 2) / img_height
                norm_w = w / img_width
                norm_h = h / img_height
                
                # Validate
                if not (0 <= center_x <= 1 and 0 <= center_y <= 1 and 
                       0 <= norm_w <= 1 and 0 <= norm_h <= 1):
                    logger.warning(f"Invalid normalized bbox in {json_path}")
                    continue
                
                # Format: <class_id> <center_x> <center_y> <width> <height>
                yolo_line = f"{class_id} {center_x:.6f} {center_y:.6f} {norm_w:.6f} {norm_h:.6f}"
                yolo_lines.append(yolo_line)
                
                # Update stats
                self.stats["class_counts"][class_name] += 1
            
            if not yolo_lines:
                logger.warning(f"No valid annotations in {json_path}")
                return False
            
            # Save YOLO label file
            output_labels_dir.mkdir(parents=True, exist_ok=True)
            label_file = output_labels_dir / f"{image_path.stem}.txt"
            
            with open(label_file, 'w') as f:
                f.write('\n'.join(yolo_lines))
            
            # Copy image
            output_images_dir.mkdir(parents=True, exist_ok=True)
            dest_image = output_images_dir / image_path.name
            
            if image_path.exists():
                shutil.copy2(image_path, dest_image)
            else:
                logger.error(f"Source image not found: {image_path}")
                return False
            
            # Update stats
            self.stats["total_images"] += 1
            self.stats["total_annotations"] += len(yolo_lines)
            
            return True
            
        except Exception as e:
            logger.error(f"Error converting {json_path}: {e}")
            self.stats["errors"] += 1
            return False
    
    def convert_directory(self, input_dir: Path, output_dir: Path) -> Dict:
        """
        Convert all annotations in a directory to YOLO format
        
        Args:
            input_dir: Directory containing JSON + image pairs
            output_dir: Output directory for YOLO dataset
            
        Returns:
            Statistics dictionary
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        
        # Create output structure
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        
        # Find all JSON files
        json_files = list(input_dir.glob("*.json"))
        logger.info(f"Found {len(json_files)} JSON files in {input_dir}")
        
        success_count = 0
        
        for json_path in json_files:
            # Find corresponding image
            image_path = None
            for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
                potential_image = json_path.with_suffix(ext)
                if potential_image.exists():
                    image_path = potential_image
                    break
            
            if not image_path:
                logger.warning(f"No image found for {json_path}")
                continue
            
            # Convert
            if self.convert_annotation(json_path, image_path, labels_dir, images_dir):
                success_count += 1
            
            # Progress
            if (success_count + self.stats["errors"]) % 100 == 0:
                logger.info(f"Processed {success_count + self.stats['errors']} files...")
        
        logger.info(f"Conversion complete: {success_count} successful, {self.stats['errors']} errors")
        
        # Save class mapping
        self._save_class_config(output_dir)
        
        return self.stats
    
    def _save_class_config(self, output_dir: Path):
        """Save classes.txt and data.yaml for YOLO training"""
        # Save classes.txt
        classes_file = output_dir / "classes.txt"
        with open(classes_file, 'w') as f:
            for class_name in sorted(self.CLASS_MAPPING.keys(), key=lambda x: self.CLASS_MAPPING[x]):
                f.write(f"{class_name}\n")
        
        # Save data.yaml (YOLO training config)
        yaml_content = f"""# Manga Panel Detection Dataset
# Auto-generated by YOLO Converter

path: {output_dir.absolute()}  # dataset root dir
train: images/train  # train images (relative to 'path')
val: images/val  # val images (relative to 'path')
test: images/test  # test images (relative to 'path') optional

# Classes
names:
  0: panel
  1: dialogue
  2: thought
  3: face
  4: sfx

# Stats
# Total images: {self.stats['total_images']}
# Total annotations: {self.stats['total_annotations']}
"""
        
        yaml_file = output_dir / "data.yaml"
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)
        
        logger.info(f"Saved class config to {classes_file} and {yaml_file}")
    
    def print_stats(self):
        """Print conversion statistics"""
        print("\n" + "="*50)
        print("YOLO Conversion Statistics")
        print("="*50)
        print(f"Total images: {self.stats['total_images']}")
        print(f"Total annotations: {self.stats['total_annotations']}")
        print(f"Errors: {self.stats['errors']}")
        print("\nClass distribution:")
        for class_name, count in sorted(self.stats['class_counts'].items()):
            percentage = (count / self.stats['total_annotations'] * 100) if self.stats['total_annotations'] > 0 else 0
            print(f"  {class_name}: {count} ({percentage:.1f}%)")
        print("="*50 + "\n")


def convert_to_yolo(input_dir: str, output_dir: str) -> Dict:
    """
    Convenience function to convert annotations to YOLO format
    
    Args:
        input_dir: Directory with JSON annotations and images
        output_dir: Output directory for YOLO dataset
        
    Returns:
        Statistics dictionary
    """
    converter = YOLOConverter(output_dir)
    stats = converter.convert_directory(Path(input_dir), Path(output_dir))
    converter.print_stats()
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert manga annotations to YOLO format")
    parser.add_argument("input_dir", help="Directory containing JSON + image pairs")
    parser.add_argument("output_dir", help="Output directory for YOLO dataset")
    
    args = parser.parse_args()
    
    convert_to_yolo(args.input_dir, args.output_dir)
