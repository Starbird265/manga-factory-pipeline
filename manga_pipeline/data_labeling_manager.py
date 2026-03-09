#!/usr/bin/env python3
"""
Data Labeling Manager for Manga Factory
Manages, validates, and analyzes training data for ML panel detection
"""

import json
import os
from pathlib import Path
import cv2
import numpy as np
from typing import List, Dict, Tuple
import argparse
from datetime import datetime
from collections import Counter

# Optional imports with fallbacks
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import seaborn as sns
    SEABORN_AVAILABLE = True
except ImportError:
    SEABORN_AVAILABLE = False


class DataLabelingManager:
    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path.home() / 'MangaFactory'
        
        self.base_dir = Path(base_dir)
        self.ml_training_dir = self.base_dir / 'ml_training_data'
        self.training_crops_dir = self.ml_training_dir / 'training_crops'
        self.user_provided_dir = self.training_crops_dir / 'user_provided'
        self.auto_validated_dir = self.training_crops_dir / 'auto_validated'
        self.models_dir = self.ml_training_dir / 'models'
        
        # Create directories if they don't exist
        for dir_path in [self.user_provided_dir, self.auto_validated_dir, self.models_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def scan_training_data(self) -> Dict:
        """Scan and analyze all training data"""
        stats = {
            'user_provided': {'images': 0, 'annotations': 0, 'total_panels': 0, 'files': []},
            'auto_validated': {'images': 0, 'annotations': 0, 'total_panels': 0, 'files': []},
            'errors': []
        }
        
        # Scan user-provided data
        user_jsons = list(self.user_provided_dir.glob('*.json'))
        for json_file in user_jsons:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    annotation = json.load(f)
                
                # Verify corresponding image exists
                img_filename = json_file.with_suffix('.jpg').name
                img_path = json_file.parent / img_filename
                
                if img_path.exists():
                    panel_count = len(annotation.get('panels', []))
                    stats['user_provided']['total_panels'] += panel_count
                    stats['user_provided']['files'].append({
                        'json_path': str(json_file),
                        'img_path': str(img_path),
                        'panel_count': panel_count,
                        'source': annotation.get('source', 'unknown')
                    })
            except Exception as e:
                stats['errors'].append(f"Error reading {json_file}: {e}")
        
        stats['user_provided']['annotations'] = len(user_jsons)
        stats['user_provided']['images'] = len([f for f in stats['user_provided']['files']])
        
        # Scan auto-validated data
        auto_jsons = list(self.auto_validated_dir.glob('*.json'))
        for json_file in auto_jsons:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    annotation = json.load(f)
                
                # Verify corresponding image exists
                img_filename = json_file.with_suffix('.jpg').name
                img_path = json_file.parent / img_filename
                
                if img_path.exists():
                    panel_count = len(annotation.get('panels', []))
                    stats['auto_validated']['total_panels'] += panel_count
                    stats['auto_validated']['files'].append({
                        'json_path': str(json_file),
                        'img_path': str(img_path),
                        'panel_count': panel_count,
                        'source': annotation.get('source', 'unknown')
                    })
            except Exception as e:
                stats['errors'].append(f"Error reading {json_file}: {e}")
        
        stats['auto_validated']['annotations'] = len(auto_jsons)
        stats['auto_validated']['images'] = len([f for f in stats['auto_validated']['files']])
        
        return stats

    def validate_annotations(self, check_images: bool = True) -> Dict:
        """Validate annotation integrity"""
        validation_results = {
            'valid': [],
            'invalid': [],
            'warnings': [],
            'summary': {}
        }
        
        all_files = []
        # Combine both sources
        user_files = [(f, 'user_provided') for f in self.user_provided_dir.glob('*.json')]
        auto_files = [(f, 'auto_validated') for f in self.auto_validated_dir.glob('*.json')]
        all_files.extend(user_files)
        all_files.extend(auto_files)
        
        for json_file, source in all_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    annotation = json.load(f)
                
                is_valid = True
                issues = []
                
                # Check required fields
                required_fields = ['image_path', 'panels']
                for field in required_fields:
                    if field not in annotation:
                        issues.append(f"Missing required field: {field}")
                        is_valid = False
                
                # Check panels structure
                if 'panels' in annotation:
                    for i, panel in enumerate(annotation['panels']):
                        required_panel_fields = ['x', 'y', 'width', 'height']
                        for field in required_panel_fields:
                            if field not in panel:
                                issues.append(f"Panel {i} missing field: {field}")
                                is_valid = False
                            elif not isinstance(panel[field], (int, float)):
                                issues.append(f"Panel {i} field {field} is not numeric: {panel[field]}")
                                is_valid = False
                            elif field in ['x', 'y', 'width', 'height'] and panel[field] < 0:
                                issues.append(f"Panel {i} field {field} is negative: {panel[field]}")
                                is_valid = False
                
                # Check image file exists if requested
                if check_images:
                    img_path = json_file.parent / annotation.get('image_path', '')
                    if not img_path.exists():
                        issues.append(f"Image file does not exist: {img_path}")
                        is_valid = False
                    else:
                        # Check if panel coordinates are within image bounds
                        img = cv2.imread(str(img_path))
                        if img is not None:
                            height, width = img.shape[:2]
                            for i, panel in enumerate(annotation['panels']):
                                x, y, w, h = panel['x'], panel['y'], panel['width'], panel['height']
                                if x + w > width or y + h > height:
                                    issues.append(f"Panel {i} extends beyond image bounds (image: {width}x{height}, panel: {x+w}x{y+h})")
                                    # Add as warning rather than error, as it might be a minor issue
                                    validation_results['warnings'].append(f"{json_file}: {issues[-1]}")
                
                # Record result
                result = {
                    'file': str(json_file),
                    'source': source,
                    'valid': is_valid,
                    'issues': issues,
                    'panel_count': len(annotation.get('panels', []))
                }
                
                if is_valid:
                    validation_results['valid'].append(result)
                else:
                    validation_results['invalid'].append(result)
                    
            except json.JSONDecodeError as e:
                validation_results['invalid'].append({
                    'file': str(json_file),
                    'source': source,
                    'valid': False,
                    'issues': [f"Invalid JSON: {e}"],
                    'panel_count': 0
                })
            except Exception as e:
                validation_results['invalid'].append({
                    'file': str(json_file),
                    'source': source,
                    'valid': False,
                    'issues': [f"Unexpected error: {e}"],
                    'panel_count': 0
                })
        
        # Create summary
        validation_results['summary'] = {
            'total_files': len(validation_results['valid']) + len(validation_results['invalid']),
            'valid_files': len(validation_results['valid']),
            'invalid_files': len(validation_results['invalid']),
            'total_panels': sum(r['panel_count'] for r in validation_results['valid']),
            'warnings_count': len(validation_results['warnings'])
        }
        
        return validation_results

    def analyze_data_distribution(self) -> Dict:
        """Analyze distribution of panel sizes, aspect ratios, etc."""
        analysis = {
            'panel_sizes': [],
            'aspect_ratios': [],
            'positions': [],
            'sources': Counter(),
            'total_panels': 0
        }
        
        all_files = list(self.user_provided_dir.glob('*.json')) + list(self.auto_validated_dir.glob('*.json'))
        
        for json_file in all_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    annotation = json.load(f)
                
                source = annotation.get('source', 'unknown')
                analysis['sources'][source] += 1
                
                img_path = json_file.parent / annotation.get('image_path', '')
                img_dims = None
                if img_path.exists():
                    img = cv2.imread(str(img_path))
                    if img is not None:
                        img_dims = img.shape[:2]  # (height, width)
                
                for panel in annotation.get('panels', []):
                    x, y, w, h = panel['x'], panel['y'], panel['width'], panel['height']
                    
                    analysis['panel_sizes'].append((w, h))
                    aspect_ratio = w / h if h > 0 else 0
                    analysis['aspect_ratios'].append(aspect_ratio)
                    analysis['positions'].append((x, y))
                    
                    analysis['total_panels'] += 1
                    
            except Exception as e:
                print(f"Error analyzing {json_file}: {e}")
        
        return analysis

    def generate_statistics_report(self) -> str:
        """Generate a comprehensive statistics report"""
        stats = self.scan_training_data()
        validation = self.validate_annotations()
        analysis = self.analyze_data_distribution()
        
        report = []
        report.append("=" * 60)
        report.append("MANGA PANEL TRAINING DATA STATISTICS REPORT")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Overall statistics
        report.append("OVERALL STATISTICS:")
        report.append("-" * 30)
        report.append(f"Total Training Samples: {stats['user_provided']['annotations'] + stats['auto_validated']['annotations']}")
        report.append(f"Total Panels: {stats['user_provided']['total_panels'] + stats['auto_validated']['total_panels']}")
        report.append(f"User-Provided Samples: {stats['user_provided']['annotations']} ({stats['user_provided']['total_panels']} panels)")
        report.append(f"Auto-Validated Samples: {stats['auto_validated']['annotations']} ({stats['auto_validated']['total_panels']} panels)")
        report.append("")
        
        # Validation results
        report.append("VALIDATION RESULTS:")
        report.append("-" * 30)
        report.append(f"Valid Annotation Files: {validation['summary']['valid_files']}")
        report.append(f"Invalid Annotation Files: {validation['summary']['invalid_files']}")
        report.append(f"Total Warnings: {validation['summary']['warnings_count']}")
        report.append("")
        
        # Data distribution
        if analysis['panel_sizes']:
            widths, heights = zip(*analysis['panel_sizes'])
            avg_width = sum(widths) / len(widths)
            avg_height = sum(heights) / len(heights)
            
            aspects = analysis['aspect_ratios']
            avg_aspect = sum(aspects) / len(aspects) if aspects else 0
            
            report.append("PANEL DISTRIBUTION:")
            report.append("-" * 30)
            report.append(f"Total Panels Analyzed: {analysis['total_panels']}")
            report.append(f"Average Panel Size: {avg_width:.1f} x {avg_height:.1f}")
            report.append(f"Average Aspect Ratio: {avg_aspect:.2f}")
            report.append(f"Sources: {dict(analysis['sources'])}")
            report.append("")
        
        # Errors if any
        if stats['errors']:
            report.append("ERRORS FOUND:")
            report.append("-" * 30)
            for error in stats['errors']:
                report.append(f"- {error}")
            report.append("")
        
        if validation['invalid']:
            report.append("INVALID ANNOTATIONS:")
            report.append("-" * 30)
            for invalid in validation['invalid'][:5]:  # Show first 5
                report.append(f"- {invalid['file']}: {invalid['issues'][:3]}")  # First 3 issues
            if len(validation['invalid']) > 5:
                report.append(f"... and {len(validation['invalid']) - 5} more")
            report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)

    def visualize_data_distribution(self, output_path: str = None):
        """Create visualizations of data distribution"""
        if not MATPLOTLIB_AVAILABLE:
            print("matplotlib not available. Install with: pip install matplotlib")
            return
            
        analysis = self.analyze_data_distribution()
        
        if not analysis['panel_sizes']:
            print("No data to visualize")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Manga Panel Training Data Distribution', fontsize=16)
        
        # Panel width distribution
        widths, heights = zip(*analysis['panel_sizes'])
        axes[0, 0].hist(widths, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
        axes[0, 0].set_title('Panel Width Distribution')
        axes[0, 0].set_xlabel('Width (pixels)')
        axes[0, 0].set_ylabel('Frequency')
        
        # Panel height distribution
        axes[0, 1].hist(heights, bins=50, alpha=0.7, color='lightgreen', edgecolor='black')
        axes[0, 1].set_title('Panel Height Distribution')
        axes[0, 1].set_xlabel('Height (pixels)')
        axes[0, 1].set_ylabel('Frequency')
        
        # Aspect ratio distribution
        axes[1, 0].hist(analysis['aspect_ratios'], bins=50, alpha=0.7, color='salmon', edgecolor='black')
        axes[1, 0].set_title('Panel Aspect Ratio Distribution')
        axes[1, 0].set_xlabel('Aspect Ratio (Width/Height)')
        axes[1, 0].set_ylabel('Frequency')
        
        # Source distribution
        sources = list(analysis['sources'].keys())
        counts = list(analysis['sources'].values())
        axes[1, 1].bar(sources, counts, color=['coral', 'lightblue'] if len(sources) <= 2 else 'lightgray')
        axes[1, 1].set_title('Data Source Distribution')
        axes[1, 1].set_xlabel('Source')
        axes[1, 1].set_ylabel('Number of Annotations')
        plt.setp(axes[1, 1].get_xticklabels(), rotation=45, ha="right")
        
        plt.tight_layout()
        
        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"Visualization saved to: {output_path}")
        else:
            plt.show()

    def export_clean_dataset(self, output_dir: Path, min_panel_size: Tuple[int, int] = (50, 50)):
        """Export a clean dataset with basic filtering"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        user_output_dir = output_dir / 'user_provided'
        auto_output_dir = output_dir / 'auto_validated'
        user_output_dir.mkdir(exist_ok=True)
        auto_output_dir.mkdir(exist_ok=True)
        
        # Process user-provided data
        user_jsons = list(self.user_provided_dir.glob('*.json'))
        user_exported = 0
        
        for json_file in user_jsons:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    annotation = json.load(f)
                
                # Filter panels by minimum size
                filtered_panels = []
                for panel in annotation.get('panels', []):
                    if panel['width'] >= min_panel_size[0] and panel['height'] >= min_panel_size[1]:
                        filtered_panels.append(panel)
                
                if filtered_panels:  # Only export if there are valid panels
                    annotation['panels'] = filtered_panels
                    output_json = user_output_dir / json_file.name
                    with open(output_json, 'w', encoding='utf-8') as f:
                        json.dump(annotation, f, indent=2)
                    
                    # Copy corresponding image
                    img_filename = json_file.with_suffix('.jpg').name
                    src_img = json_file.parent / img_filename
                    dst_img = user_output_dir / img_filename
                    if src_img.exists():
                        import shutil
                        shutil.copy2(src_img, dst_img)
                    
                    user_exported += 1
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
        
        # Process auto-validated data
        auto_jsons = list(self.auto_validated_dir.glob('*.json'))
        auto_exported = 0
        
        for json_file in auto_jsons:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    annotation = json.load(f)
                
                # Filter panels by minimum size
                filtered_panels = []
                for panel in annotation.get('panels', []):
                    if panel['width'] >= min_panel_size[0] and panel['height'] >= min_panel_size[1]:
                        filtered_panels.append(panel)
                
                if filtered_panels:  # Only export if there are valid panels
                    annotation['panels'] = filtered_panels
                    output_json = auto_output_dir / json_file.name
                    with open(output_json, 'w', encoding='utf-8') as f:
                        json.dump(annotation, f, indent=2)
                    
                    # Copy corresponding image
                    img_filename = json_file.with_suffix('.jpg').name
                    src_img = json_file.parent / img_filename
                    dst_img = auto_output_dir / img_filename
                    if src_img.exists():
                        import shutil
                        shutil.copy2(src_img, dst_img)
                    
                    auto_exported += 1
            except Exception as e:
                print(f"Error processing {json_file}: {e}")
        
        print(f"Exported clean dataset:")
        print(f"  User-provided: {user_exported} files")
        print(f"  Auto-validated: {auto_exported} files")
        print(f"  Output directory: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description='Manage and analyze manga panel training data')
    parser.add_argument('--base-dir', type=str, help='Base directory for MangaFactory data')
    parser.add_argument('--scan', action='store_true', help='Scan and report training data statistics')
    parser.add_argument('--validate', action='store_true', help='Validate annotation integrity')
    parser.add_argument('--analyze', action='store_true', help='Analyze data distribution')
    parser.add_argument('--visualize', type=str, help='Generate visualization (specify output path)')
    parser.add_argument('--export-clean', type=str, help='Export clean dataset to directory')
    parser.add_argument('--report', action='store_true', help='Generate full statistics report')
    
    args = parser.parse_args()
    
    manager = DataLabelingManager(Path(args.base_dir) if args.base_dir else None)
    
    if args.scan:
        stats = manager.scan_training_data()
        print("Training Data Scan Results:")
        print(json.dumps(stats, indent=2))
    
    if args.validate:
        validation = manager.validate_annotations()
        print("Validation Results:")
        print(json.dumps(validation['summary'], indent=2))
        
        if validation['invalid']:
            print(f"\nFirst few invalid files:")
            for invalid in validation['invalid'][:5]:
                print(f"  {invalid['file']}: {invalid['issues'][:3]}")
    
    if args.analyze:
        analysis = manager.analyze_data_distribution()
        print("Data Distribution Analysis:")
        print(json.dumps({
            'total_panels': analysis['total_panels'],
            'sources': dict(analysis['sources']),
            'sample_counts': {
                'panel_sizes': len(analysis['panel_sizes']),
                'aspect_ratios': len(analysis['aspect_ratios'])
            }
        }, indent=2))
    
    if args.visualize:
        manager.visualize_data_distribution(args.visualize)
    
    if args.export_clean:
        manager.export_clean_dataset(Path(args.export_clean))
    
    if args.report:
        report = manager.generate_statistics_report()
        print(report)


if __name__ == "__main__":
    main()