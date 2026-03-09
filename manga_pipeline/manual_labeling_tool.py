#!/usr/bin/env python3
"""
Manual Labeling Tool for Manga Panel Detection
Provides a GUI interface for manually annotating manga panels with bounding boxes
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from PIL import Image, ImageTk
import json
import os
from pathlib import Path
import numpy as np


class ManualLabelingTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Manga Panel Labeling Tool")
        self.root.geometry("1200x800")
        
        # Variables
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.photo = None
        self.canvas_image = None
        self.panels = []  # List of panel coordinates [(x, y, width, height)]
        self.current_panel = None
        self.drawing = False
        self.start_x = 0
        self.start_y = 0
        
        # Canvas for image display
        self.canvas = tk.Canvas(root, bg='gray')
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        
        # Control frame
        control_frame = ttk.Frame(root)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Buttons
        ttk.Button(control_frame, text="Load Image", command=self.load_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Clear All", command=self.clear_annotations).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Save Labels", command=self.save_labels).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Next Image", command=self.next_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Prev Image", command=self.prev_image).pack(side=tk.LEFT, padx=5)
        
        # Info label
        self.info_label = ttk.Label(control_frame, text="Load an image to start labeling panels")
        self.info_label.pack(side=tk.RIGHT, padx=5)
        
        # Store image list for navigation
        self.image_list = []
        self.current_image_index = 0

    def load_image(self):
        """Load an image for labeling"""
        file_path = filedialog.askopenfilename(
            title="Select Manga Page Image",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif")]
        )
        
        if not file_path:
            return
            
        self.image_path = Path(file_path)
        
        # Load image
        self.original_image = cv2.imread(str(self.image_path))
        if self.original_image is None:
            messagebox.showerror("Error", "Could not load image")
            return
            
        # Convert BGR to RGB for display
        image_rgb = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB)
        self.display_image = image_rgb.copy()
        
        # Resize image to fit canvas while maintaining aspect ratio
        canvas_width = self.canvas.winfo_width() - 20
        canvas_height = self.canvas.winfo_height() - 20
        height, width = self.display_image.shape[:2]
        
        scale_w = canvas_width / width if width > 0 else 1
        scale_h = canvas_height / height if height > 0 else 1
        scale = min(scale_w, scale_h, 1.0)  # Don't upscale
        
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        self.display_image = cv2.resize(self.display_image, (new_width, new_height))
        self.scale_factor = scale
        
        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(Image.fromarray(self.display_image))
        
        # Clear canvas and add image
        self.canvas.delete("all")
        self.canvas_image = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        
        # Draw existing panels if any
        self.draw_existing_panels()
        
        # Update info
        self.info_label.config(text=f"Loaded: {self.image_path.name} | Panels: {len(self.panels)}")
        
        # Reset current panel
        self.panels = []
        self.current_panel = None

    def draw_existing_panels(self):
        """Draw all existing panel annotations"""
        for panel in self.panels:
            x, y, w, h = panel
            # Scale coordinates back to display size
            x_scaled = x * self.scale_factor
            y_scaled = y * self.scale_factor
            w_scaled = w * self.scale_factor
            h_scaled = h * self.scale_factor
            
            # Draw rectangle
            self.canvas.create_rectangle(
                x_scaled, y_scaled, 
                x_scaled + w_scaled, y_scaled + h_scaled,
                outline='red', width=2, dash=(4, 2)
            )

    def on_mouse_down(self, event):
        """Start drawing a panel annotation"""
        if self.original_image is None:
            return
            
        self.drawing = True
        self.start_x = event.x
        self.start_y = event.y
        self.current_panel = (event.x, event.y, 0, 0)

    def on_mouse_drag(self, event):
        """Continue drawing during drag"""
        if not self.drawing or self.current_panel is None:
            return
            
        # Delete previous temporary rectangle
        for item in self.canvas.find_withtag("temp_rect"):
            self.canvas.delete(item)
        
        # Calculate current rectangle
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        
        # Draw temporary rectangle
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline='yellow', width=2, dash=(2, 2),
            tags="temp_rect"
        )

    def on_mouse_up(self, event):
        """Finish drawing a panel annotation"""
        if not self.drawing:
            return
            
        self.drawing = False
        
        # Calculate final rectangle
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        
        # Ensure proper coordinate order
        min_x = min(x1, x2)
        min_y = min(y1, y2)
        max_x = max(x1, x2)
        max_y = max(y1, y2)
        
        width = max_x - min_x
        height = max_y - min_y
        
        # Only add if rectangle is large enough (at least 10x10 pixels in display size)
        if width >= 10 and height >= 10:
            # Convert back to original image coordinates
            orig_x = int(min_x / self.scale_factor)
            orig_y = int(min_y / self.scale_factor)
            orig_width = int(width / self.scale_factor)
            orig_height = int(height / self.scale_factor)
            
            self.panels.append((orig_x, orig_y, orig_width, orig_height))
            
            # Redraw the rectangle permanently
            self.canvas.create_rectangle(
                min_x, min_y, max_x, max_y,
                outline='red', width=2, dash=(4, 2)
            )
        
        # Remove temporary rectangle
        for item in self.canvas.find_withtag("temp_rect"):
            self.canvas.delete(item)
        
        # Update info
        self.info_label.config(text=f"Loaded: {self.image_path.name} | Panels: {len(self.panels)}")

    def clear_annotations(self):
        """Clear all panel annotations"""
        self.panels = []
        self.current_panel = None
        
        # Redraw image without rectangles
        self.canvas.delete("all")
        self.canvas_image = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        
        # Update info
        self.info_label.config(text=f"Cleared annotations for: {self.image_path.name}")

    def save_labels(self):
        """Save panel annotations to JSON file"""
        if not self.image_path or not self.panels:
            messagebox.showwarning("Warning", "No annotations to save")
            return
            
        # Create annotation dictionary
        annotation = {
            'image_path': self.image_path.name,
            'original_path': str(self.image_path.absolute()),
            'panels': [
                {
                    'x': x,
                    'y': y,
                    'width': w,
                    'height': h
                }
                for x, y, w, h in self.panels
            ],
            'quality_scores': [1.0] * len(self.panels),  # Perfect quality for manually labeled
            'source': 'manual_annotation',
            'created_at': str(Path.home() / 'MangaFactory' / 'ml_training_data' / 'training_crops' / 'user_provided')
        }
        
        # Determine output path
        output_dir = Path.home() / 'MangaFactory' / 'ml_training_data' / 'training_crops' / 'user_provided'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create output filename
        stem = self.image_path.stem
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"{stem}_{timestamp}.json"
        image_filename = f"{stem}_{timestamp}.jpg"
        
        json_path = output_dir / json_filename
        image_path = output_dir / image_filename
        
        # Save JSON annotation
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(annotation, f, indent=2)
        
        # Save image in the required format
        # Convert back to BGR for saving
        image_bgr = cv2.cvtColor(self.original_image, cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(image_path), image_bgr)
        
        messagebox.showinfo("Success", f"Labels saved to:\n{json_path}\nImage copied to:\n{image_path}")

    def next_image(self):
        """Load next image from directory"""
        if not self.image_path:
            messagebox.showwarning("Warning", "Load an image first")
            return
            
        # Get directory of current image
        img_dir = self.image_path.parent
        self._load_image_from_directory(img_dir, 1)  # Move forward

    def prev_image(self):
        """Load previous image from directory"""
        if not self.image_path:
            messagebox.showwarning("Warning", "Load an image first")
            return
            
        # Get directory of current image
        img_dir = self.image_path.parent
        self._load_image_from_directory(img_dir, -1)  # Move backward

    def _load_image_from_directory(self, directory, direction):
        """Helper to load next/previous image in directory"""
        # Get all image files in directory
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(directory.glob(f'*{ext}'))
            image_files.extend(directory.glob(f'*{ext.upper()}'))
        
        # Sort files
        image_files = sorted(image_files, key=lambda x: x.name.lower())
        
        if not image_files:
            messagebox.showwarning("Warning", "No images found in directory")
            return
            
        # Find current index
        try:
            current_idx = image_files.index(self.image_path)
        except ValueError:
            current_idx = 0  # Start from beginning if current image not found
            
        # Calculate new index
        new_idx = (current_idx + direction) % len(image_files)
        
        # Load the new image
        self.image_path = image_files[new_idx]
        self.current_image_index = new_idx
        self.image_list = image_files
        
        # Load the image
        self.original_image = cv2.imread(str(self.image_path))
        if self.original_image is None:
            messagebox.showerror("Error", "Could not load image")
            return
            
        # Convert BGR to RGB for display
        image_rgb = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB)
        self.display_image = image_rgb.copy()
        
        # Resize image to fit canvas while maintaining aspect ratio
        canvas_width = self.canvas.winfo_width() - 20
        canvas_height = self.canvas.winfo_height() - 20
        height, width = self.display_image.shape[:2]
        
        scale_w = canvas_width / width if width > 0 else 1
        scale_h = canvas_height / height if height > 0 else 1
        scale = min(scale_w, scale_h, 1.0)  # Don't upscale
        
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        self.display_image = cv2.resize(self.display_image, (new_width, new_height))
        self.scale_factor = scale
        
        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(Image.fromarray(self.display_image))
        
        # Clear canvas and add image
        self.canvas.delete("all")
        self.canvas_image = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        
        # Reset panels for new image
        self.panels = []
        self.current_panel = None
        
        # Update info
        self.info_label.config(
            text=f"Image {new_idx + 1}/{len(image_files)}: {self.image_path.name} | Panels: {len(self.panels)}"
        )


def main():
    root = tk.Tk()
    app = ManualLabelingTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()