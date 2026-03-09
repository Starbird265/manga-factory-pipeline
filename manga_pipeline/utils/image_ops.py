import os
import subprocess
import logging
from PIL import Image, ExifTags
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class ImageOps:
    """
    High-performance image operations ported from Moltbot's image-ops.ts.
    Uses macOS 'sips' when available for maximum speed, falls back to Pillow.
    """
    
    @staticmethod
    def get_metadata(file_path: str) -> Dict[str, Any]:
        """Get image dimensions and format."""
        try:
            with Image.open(file_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode
                }
        except Exception as e:
            logger.error(f"Failed to get metadata for {file_path}: {e}")
            return {}

    @staticmethod
    def resize_to_jpeg(input_path: str, output_path: str, max_side: int = 2000, quality: int = 85) -> bool:
        """
        Resize image and convert to JPEG. 
        Uses 'sips' on macOS for high-performance processing.
        """
        # Try sips first on macOS
        if os.name == 'posix' and os.path.exists('/usr/bin/sips'):
            try:
                # sips -Z <max_side> <input> --out <output>
                # Note: -s format jpeg ensures it's converted
                cmd = [
                    '/usr/bin/sips',
                    '-Z', str(max_side),
                    '-s', 'format', 'jpeg',
                    '-s', 'formatOptions', str(quality),
                    input_path,
                    '--out', output_path
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                return True
            except Exception as e:
                logger.warning(f"sips resize failed, falling back to Pillow: {e}")

        # Fallback to Pillow
        try:
            with Image.open(input_path) as img:
                # Handle orientation
                img = ImageOps.normalize_orientation(img)
                
                # Convert to RGB if needed
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # Resize
                img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                img.save(output_path, "JPEG", quality=quality, optimize=True)
                return True
        except Exception as e:
            logger.error(f"Pillow resize failed: {e}")
            return False

    @staticmethod
    def normalize_orientation(img: Image.Image) -> Image.Image:
        """Corrects image orientation based on EXIF data."""
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            
            exif = img._getexif()
            if exif is not None:
                orientation = exif.get(orientation)
                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
        except Exception:
            # Fallback if EXIF reading fails
            pass
        return img

    @staticmethod
    def optimize_manga_page(input_path: str, output_path: str, target_width: int = 1200) -> bool:
        """
        Standardize manga page width for better stitching and OCR results.
        """
        try:
            with Image.open(input_path) as img:
                width, height = img.size
                if width == target_width:
                    # Just convert/optimize if width already matches
                    return ImageOps.resize_to_jpeg(input_path, output_path, max_side=max(width, height))
                
                # Calculate new height to maintain aspect ratio
                new_height = int(height * (target_width / width))
                
                # Use sips for the final operation
                return ImageOps.resize_to_jpeg(input_path, output_path, max_side=max(target_width, new_height))
        except Exception as e:
            logger.error(f"Manga optimization failed: {e}")
            return False
