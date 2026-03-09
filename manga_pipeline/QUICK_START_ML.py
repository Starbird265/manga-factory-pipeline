#!/usr/bin/env python3
"""
Quick Start Guide - ML Training System
Complete workflow from labeling to trained model
"""

import sys
from pathlib import Path

def print_header(title):
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")

def main():
    print_header("🚀 MANGA ML TRAINING SYSTEM - QUICK START")
    
    print("This system is SEPARATE from the manga processing pipeline.")
    print("It's dedicated to training ML models for panel detection.\n")
    
    print_header("📋 STEP 1: INSTALL DEPENDENCIES")
    
    print("Install required packages:")
    print("```bash")
    print("pip install ultralytics opencv-python pillow numpy")
    print("```\n")
    
    print_header("📝 STEP 2: LABEL YOUR DATA")
    
    print("Use the professional labeling tool:")
    print("```bash")
    print("cd manga_pipeline")
    print("python manual_labeling_tool_pro.py")
    print("```\n")
    
    print("Features:")
    print("  • Zoom: Mouse wheel or slider (10%-500%)")
    print("  • Pan: Right-click drag")
    print("  • Multi-class: panel, dialogue, thought, face, sfx")
    print("  • Shortcuts: Ctrl+Z (undo), Ctrl+S (save), 1-5 (class select)")
    print("  • Navigation: ← → for prev/next image\n")
    
    print("Target: Label 500-1000 images from diverse manga series\n")
    
    print_header("🔄 STEP 3: PREPARE DATASET")
    
    print("Run the complete ML pipeline:")
    print("```bash")
    print("cd manga_pipeline")
    print("python -m ml_models.training_pipeline full \\")
    print("  --base-dir ~/manga_ml_training \\")
    print("  --annotations-dir /path/to/your/labeled/images \\")
    print("  --dataset-name my_manga_v1 \\")
    print("  --model yolov8m \\")
    print("  --epochs 100 \\")
    print("  --device cpu  # or 'cuda' if you have GPU")
    print("```\n")
    
    print("This will:")
    print("  1. Convert JSON → YOLO format")
    print("  2. Split into train/val/test (70/15/15)")
    print("  3. Augment training data (3x more samples)")
    print("  4. Train YOLOv8 model")
    print("  5. Evaluate on validation set\n")
    
    print_header("📊 STEP 4: MONITOR TRAINING")
    
    print("Training metrics are logged in real-time.")
    print("Check results in: ~/manga_ml_training/experiments/\n")
    
    print("Expected timeline:")
    print("  • CPU: 2-4 hours for 100 epochs (500 images)")
    print("  • GPU: 15-30 minutes for 100 epochs (500 images)\n")
    
    print_header("🎯 STEP 5: ACTIVE LEARNING (OPTIONAL)")
    
    print("Reduce labeling effort by 70% using active learning:\n")
    
    print("1. Select uncertain samples:")
    print("```bash")
    print("python -m active_learning.sample_selector \\")
    print("  /path/to/unlabeled/images \\")
    print("  selected_samples.json \\")
    print("  --model ~/manga_ml_training/experiments/my_model/best.pt \\")
    print("  --n-samples 50 \\")
    print("  --strategy uncertainty")
    print("```\n")
    
    print("2. Auto-annotate for review:")
    print("```bash")
    print("python -m active_learning.auto_annotator \\")
    print("  /path/to/unlabeled/images \\")
    print("  /path/to/review/output \\")
    print("  ~/manga_ml_training/experiments/my_model/best.pt \\")
    print("  --conf 0.4")
    print("```\n")
    
    print("3. Review and correct in labeling tool")
    print("4. Retrain model with new labels")
    print("5. Repeat for continuous improvement\n")
    
    print_header("🔧 ADVANCED USAGE")
    
    print("Individual pipeline steps:\n")
    
    print("Prepare dataset only:")
    print("```bash")
    print("python -m ml_models.training_pipeline prepare \\")
    print("  --base-dir ~/manga_ml_training \\")
    print("  --annotations-dir /path/to/labeled/images \\")
    print("  --dataset-name my_manga_v1")
    print("```\n")
    
    print("Train on existing dataset:")
    print("```bash")
    print("python -m ml_models.training_pipeline train \\")
    print("  --base-dir ~/manga_ml_training \\")
    print("  --dataset-name my_manga_v1 \\")
    print("  --model yolov8m \\")
    print("  --epochs 100")
    print("```\n")
    
    print("List all experiments:")
    print("```bash")
    print("python -m ml_models.training_pipeline list \\")
    print("  --base-dir ~/manga_ml_training")
    print("```\n")
    
    print_header("📈 EXPECTED RESULTS")
    
    print("With 500-1000 labeled images:")
    print("  • mAP@50: 85-92%")
    print("  • mAP@50-95: 75-85%")
    print("  • Inference speed: <200ms per image (CPU)\n")
    
    print("With active learning (3-5 iterations):")
    print("  • mAP@50: 92-95%")
    print("  • 70% less manual labeling needed")
    print("  • Better generalization to new manga series\n")
    
    print_header("🐛 TROUBLESHOOTING")
    
    print("Issue: YOLO not installed")
    print("  Fix: pip install ultralytics\n")
    
    print("Issue: Out of memory during training")
    print("  Fix: Reduce batch size (--batch 8 or 4)\n")
    
    print("Issue: Training too slow on CPU")
    print("  Fix 1: Use smaller model (yolov8n instead of yolov8m)")
    print("  Fix 2: Reduce epochs (--epochs 50)")
    print("  Fix 3: Use GPU if available (--device cuda)\n")
    
    print("Issue: Low accuracy")
    print("  Fix 1: Label more diverse samples")
    print("  Fix 2: Check annotation quality")
    print("  Fix 3: Use larger model (yolov8l)")
    print("  Fix 4: Train for more epochs\n")
    
    print_header("📂 FILE STRUCTURE")
    
    print("After running the pipeline:\n")
    print("~/manga_ml_training/")
    print("├── raw_annotations/          # Original JSON + images")
    print("├── processed_datasets/")
    print("│   └── my_manga_v1/")
    print("│       ├── yolo_raw/         # YOLO format conversion")
    print("│       ├── split/            # Train/val/test splits")
    print("│       └── augmented/        # Augmented dataset")
    print("├── trained_models/           # Final models")
    print("└── experiments/")
    print("    ├── experiment_1/         # Training run 1")
    print("    │   ├── weights/")
    print("    │   │   └── best.pt       # Best model checkpoint")
    print("    │   └── results.csv       # Training metrics")
    print("    └── experiments.json      # All experiments log\n")
    
    print_header("✅ NEXT STEPS")
    
    print("1. Press Enter to test the labeling tool now, or Ctrl+C to exit")
    
    try:
        input()
        print("\nLaunching professional labeling tool...")
        print("Load an image to start annotating!\n")
        
        import subprocess
        subprocess.Popen([sys.executable, "manual_labeling_tool_pro.py"])
        
    except KeyboardInterrupt:
        print("\n\nExiting. Happy labeling! 🎨\n")
    except Exception as e:
        print(f"\nCouldn't launch tool: {e}")
        print("Run manually with: python manual_labeling_tool_pro.py\n")


if __name__ == "__main__":
    main()
