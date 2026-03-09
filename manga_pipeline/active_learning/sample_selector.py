#!/usr/bin/env python3
"""
Active Learning Sample Selector
Intelligently select unlabeled samples for annotation to maximize model improvement
"""

import logging
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ActiveLearningSampler:
    """Select most informative samples for labeling"""
    
    def __init__(self, model_path: Path = None):
        """
        Initialize active learning sampler
        
        Args:
            model_path: Path to trained YOLO model
        """
        self.model_path = model_path
        self.model = None
        
        if model_path and model_path.exists():
            self._load_model()
    
    def _load_model(self):
        """Load YOLO model for predictions"""
        try:
            from ml_models.yolo_panel_detector import YOLOPanelDetector
            self.model = YOLOPanelDetector(self.model_path)
            logger.info(f"Loaded model from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model = None
    
    def calculate_uncertainty(self, predictions: List[Dict]) -> float:
        """
        Calculate uncertainty score for predictions
        
        Uses entropy-based uncertainty: samples with many low-confidence predictions
        are more uncertain
        
        Args:
            predictions: List of predictions with 'confidence' field
            
        Returns:
            Uncertainty score (higher = more uncertain)
        """
        if not predictions:
            return 1.0  # Max uncertainty for no predictions
        
        confidences = [p['confidence'] for p in predictions]
        
        # Calculate entropy
        entropy = 0
        for conf in confidences:
            if conf > 0:
                entropy -= conf * np.log(conf + 1e-10)
        
        # Average confidence (lower = more uncertain)
        avg_conf = np.mean(confidences)
        
        # Combined score
        uncertainty = entropy + (1 - avg_conf)
        
        return uncertainty
    
    def select_uncertain_samples(self, unlabeled_dir: Path, 
                                 n_samples: int = 50,
                                 conf_threshold: float = 0.25) -> List[Tuple[Path, float]]:
        """
        Select most uncertain samples from unlabeled images
        
        Args:
            unlabeled_dir: Directory with unlabeled images
            n_samples: Number of samples to select
            conf_threshold: Confidence threshold for predictions
            
        Returns:
            List of (image_path, uncertainty_score) tuples
        """
        if self.model is None:
            logger.error("No model loaded")
            return []
        
        logger.info(f"Scanning {unlabeled_dir} for unlabeled images...")
        
        # Find all images
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp']:
            image_files.extend(unlabeled_dir.glob(ext))
        
        logger.info(f"Found {len(image_files)} images")
        
        # Calculate uncertainty for each image
        uncertainties = []
        
        for img_path in image_files:
            # Skip if already has annotations
            if img_path.with_suffix('.json').exists():
                continue
            
            # Run inference
            predictions = self.model.detect_panels(img_path, conf_threshold)
            
            # Calculate uncertainty
            uncertainty = self.calculate_uncertainty(predictions)
            
            uncertainties.append((img_path, uncertainty))
        
        logger.info(f"Calculated uncertainty for {len(uncertainties)} unlabeled images")
        
        # Sort by uncertainty (descending)
        uncertainties.sort(key=lambda x: x[1], reverse=True)
        
        # Select top N
        selected = uncertainties[:n_samples]
        
        return selected
    
    def select_diverse_samples(self, unlabeled_dir: Path,
                              n_samples: int = 50) -> List[Path]:
        """
        Select diverse samples using simple image-level features
        
        Args:
            unlabeled_dir: Directory with unlabeled images
            n_samples: Number of samples to select
            
        Returns:
            List of image paths
        """
        import cv2
        
        logger.info("Selecting diverse samples...")
        
        # Find all images
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.webp']:
            image_files.extend(unlabeled_dir.glob(ext))
        
        # Extract simple features (mean color, dimensions, edge density)
        features = []
        for img_path in image_files:
            if img_path.with_suffix('.json').exists():
                continue
            
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            
            # Simple features
            h, w = img.shape[:2]
            mean_color = np.mean(img, axis=(0, 1))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.mean(edges > 0)
            
            feature_vec = np.array([h / 1000, w / 1000, *mean_color / 255, edge_density])
            features.append((img_path, feature_vec))
        
        if not features:
            return []
        
        # K-means clustering for diversity (simplified version)
        # Select samples from different clusters
        selected = []
        remaining = list(features)
        
        # First sample: random
        if remaining:
            idx = np.random.randint(len(remaining))
            selected.append(remaining.pop(idx))
        
        # Remaining samples: farthest from selected
        while len(selected) < n_samples and remaining:
            # Calculate min distance to selected samples
            distances = []
            for img_path, feat in remaining:
                min_dist = min([
                    np.linalg.norm(feat - sel_feat)
                    for _, sel_feat in selected
                ])
                distances.append(min_dist)
            
            # Select farthest
            idx = np.argmax(distances)
            selected.append(remaining.pop(idx))
        
        logger.info(f"Selected {len(selected)} diverse samples")
        
        return [img_path for img_path, _ in selected]
    
    def save_selection(self, selected_samples: List, output_file: Path):
        """
        Save selected samples to JSON file
        
        Args:
            selected_samples: List of (path, score) tuples or paths
            output_file: Output JSON file
        """
        data = {
            "timestamp": str(Path().absolute()),
            "n_samples": len(selected_samples),
            "samples": []
        }
        
        for item in selected_samples:
            if isinstance(item, tuple):
                path, score = item
                data["samples"].append({
                    "path": str(path),
                    "score": float(score)
                })
            else:
                data["samples"].append({
                    "path": str(item)
                })
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved selection to {output_file}")


def select_samples_for_labeling(unlabeled_dir: str,
                                output_file: str,
                                model_path: str = None,
                                n_samples: int = 50,
                                strategy: str = 'uncertainty') -> List:
    """
    Convenience function to select samples for labeling
    
    Args:
        unlabeled_dir: Directory with unlabeled images
        output_file: Output JSON file
        model_path: Path to trained model (required for uncertainty)
        n_samples: Number of samples to select
        strategy: Selection strategy ('uncertainty' or 'diversity')
        
    Returns:
        List of selected samples
    """
    sampler = ActiveLearningSampler(Path(model_path) if model_path else None)
    
    if strategy == 'uncertainty':
        if not model_path:
            raise ValueError("model_path required for uncertainty sampling")
        selected = sampler.select_uncertain_samples(Path(unlabeled_dir), n_samples)
    elif strategy == 'diversity':
        selected = sampler.select_diverse_samples(Path(unlabeled_dir), n_samples)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    
    sampler.save_selection(selected, Path(output_file))
    
    return selected


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Active Learning Sample Selector")
    parser.add_argument("unlabeled_dir", help="Directory with unlabeled images")
    parser.add_argument("output_file", help="Output JSON file with selected samples")
    parser.add_argument("--model", help="Path to trained YOLO model")
    parser.add_argument("--n-samples", type=int, default=50, help="Number of samples to select")
    parser.add_argument("--strategy", choices=['uncertainty', 'diversity'], default='uncertainty',
                       help="Selection strategy")
    
    args = parser.parse_args()
    
    select_samples_for_labeling(
        args.unlabeled_dir,
        args.output_file,
        args.model,
        args.n_samples,
        args.strategy
    )
