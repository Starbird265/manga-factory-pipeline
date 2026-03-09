#!/usr/bin/env python3
"""
Auto-Annotator for Active Learning
Pre-fill annotations using trained model predictions for faster human review
"""

import logging
from pathlib import Path
from typing import List, Dict
import json
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoAnnotator:
    """Auto-annotate images with model predictions for human review"""
    
    def __init__(self, model_path: Path):
        """
        Initialize auto-annotator
        
        Args:
            model_path: Path to trained YOLO model
        """
        self.model_path = model_path
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load YOLO model"""
        try:
            from ml_models.yolo_panel_detector import YOLOPanelDetector
            self.model = YOLOPanelDetector(self.model_path)
            logger.info(f"Loaded model from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def auto_annotate_image(self, image_path: Path,
                           conf_threshold: float = 0.4) -> Dict:
        """
        Auto-annotate a single image
        
        Args:
            image_path: Path to image
            conf_threshold: Confidence threshold (higher = more conservative)
            
        Returns:
            Annotation dictionary
        """
        # Run inference
        predictions = self.model.detect_panels(image_path, conf_threshold)
        
        # Load image to get dimensions
        import cv2
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Cannot load image: {image_path}")
        
        h, w = img.shape[:2]
        
        # Convert to annotation format
        annotations = []
        for pred in predictions:
            annotation = {
                "x": pred['x'],
                "y": pred['y'],
                "width": pred['width'],
                "height": pred['height'],
                "class": pred['class'],
                "confidence": pred['confidence'],
                "auto_generated": True  # Mark as auto-generated
            }
            annotations.append(annotation)
        
        # Create annotation data
        data = {
            "image_path": image_path.name,
            "image_width": w,
            "image_height": h,
            "annotations": annotations,
            "num_annotations": len(annotations),
            "auto_generated": True,
            "needs_review": True,
            "model_used": str(self.model_path)
        }
        
        return data
    
    def auto_annotate_directory(self, input_dir: Path, output_dir: Path,
                                conf_threshold: float = 0.4,
                                copy_images: bool = True) -> Dict:
        """
        Auto-annotate all images in directory
        
        Args:
            input_dir: Directory with images
            output_dir: Directory to save annotations (and optionally images)
            conf_threshold: Confidence threshold
            copy_images: Whether to copy images to output directory
            
        Returns:
            Statistics dictionary
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all images
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp']:
            image_files.extend(input_dir.glob(ext))
        
        logger.info(f"Found {len(image_files)} images")
        
        stats = {
            "total_images": len(image_files),
            "annotated": 0,
            "total_annotations": 0,
            "avg_confidence": 0
        }
        
        all_confidences = []
        
        for img_path in image_files:
            try:
                # Auto-annotate
                annotation_data = self.auto_annotate_image(img_path, conf_threshold)
                
                # Save annotation
                json_path = output_dir / f"{img_path.stem}.json"
                with open(json_path, 'w') as f:
                    json.dump(annotation_data, f, indent=2)
                
                # Copy image if requested
                if copy_images:
                    shutil.copy2(img_path, output_dir / img_path.name)
                
                # Update stats
                stats["annotated"] += 1
                stats["total_annotations"] += len(annotation_data["annotations"])
                
                for ann in annotation_data["annotations"]:
                    all_confidences.append(ann["confidence"])
                
                logger.info(f"Annotated {img_path.name}: {len(annotation_data['annotations'])} panels")
                
            except Exception as e:
                logger.error(f"Failed to annotate {img_path}: {e}")
        
        if all_confidences:
            stats["avg_confidence"] = sum(all_confidences) / len(all_confidences)
        
        logger.info(f"\n✓ Auto-annotation complete!")
        logger.info(f"  Images annotated: {stats['annotated']}/{stats['total_images']}")
        logger.info(f"  Total annotations: {stats['total_annotations']}")
        logger.info(f"  Avg confidence: {stats['avg_confidence']:.3f}")
        
        return stats


def auto_annotate_for_review(image_dir: str, output_dir: str,
                             model_path: str,
                             conf_threshold: float = 0.4) -> Dict:
    """
    Convenience function to auto-annotate images for human review
    
    Args:
        image_dir: Directory with images
        output_dir: Output directory
        model_path: Path to trained model
        conf_threshold: Confidence threshold
        
    Returns:
        Statistics dictionary
    """
    annotator = AutoAnnotator(Path(model_path))
    stats = annotator.auto_annotate_directory(
        Path(image_dir),
        Path(output_dir),
        conf_threshold,
        copy_images=True
    )
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-Annotator")
    parser.add_argument("image_dir", help="Directory with images")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("model_path", help="Path to trained YOLO model")
    parser.add_argument("--conf", type=float, default=0.4, help="Confidence threshold")
    
    args = parser.parse_args()
    
    auto_annotate_for_review(args.image_dir, args.output_dir, args.model_path, args.conf)
