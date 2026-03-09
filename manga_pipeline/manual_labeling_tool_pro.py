#!/usr/bin/env python3
"""
Professional Manual Labeling Tool for Manga Panel Detection
Enhanced version with zoom, pan, multi-class support, and keyboard shortcuts
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from PIL import Image, ImageTk
import json
import os
from pathlib import Path
import numpy as np
from typing import List, Dict, Tuple, Optional

class PanelAnnotation:
    """Represents a single panel annotation"""
    def __init__(self, x1: int, y1: int, x2: int, y2: int, label_class: str = "panel"):
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.label_class = label_class
    
    def to_dict(self) -> Dict:
        return {
            "x": self.x1,
            "y": self.y1,
            "width": self.x2 - self.x1,
            "height": self.y2 - self.y1,
            "class": self.label_class
        }
    
    def contains_point(self, x: int, y: int) -> bool:
        """Check if point is inside this annotation"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class ProfessionalLabelingTool:
    """Professional labeling tool with advanced features"""
    
    # Class definitions with colors
    LABEL_CLASSES = {
        "panel": {"color": "#00FF00", "name": "Panel"},
        "dialogue": {"color": "#FF00FF", "name": "Dialogue Bubble"},
        "thought": {"color": "#00FFFF", "name": "Thought Bubble"},
        "face": {"color": "#FFFF00", "name": "Character Face"},
        "sfx": {"color": "#FF8800", "name": "Sound Effect"}
    }
    
    def __init__(self, root):
        self.root = root
        self.root.title("Professional Manga Labeling Tool")
        self.root.geometry("1600x900")
        
        # State variables
        self.image_path = None
        self.current_image = None
        self.original_image = None
        self.photo_image = None
        self.image_list = []
        self.current_index = -1
        
        # Annotations
        self.annotations: List[PanelAnnotation] = []
        self.history: List[List[PanelAnnotation]] = []  # For undo/redo
        self.history_index = -1
        
        # Drawing state
        self.drawing = False
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None
        self.current_class = "panel"
        
        # Zoom and pan
        self.zoom_level = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        self.panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        
        # Selection
        self.selected_annotation = None
        
        # Setup UI
        self._setup_ui()
        self._bind_keyboard_shortcuts()
        
        # Auto-load last directory if exists
        self.last_dir = Path.home() / "MangaFactory" / "ml_training_data"
        
    def _setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Toolbar at top
        self._create_toolbar(main_container)
        
        # Content area (canvas + controls)
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side: Canvas with scrollbars
        canvas_frame = ttk.Frame(content_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Canvas with scrollbars
        self.canvas = tk.Canvas(canvas_frame, bg='#2b2b2b', cursor='crosshair')
        
        # Scrollbars
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        
        self.canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        # Grid layout for canvas and scrollbars
        self.canvas.grid(row=0, column=0, sticky='nsew')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Bind canvas events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_start)  # Right click for pan
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_end)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # For Mac/Windows
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)  # For Linux
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)  # For Linux
        self.canvas.bind("<Motion>", self.on_mouse_move)
        
        # Right panel: Controls
        self._create_control_panel(content_frame)
        
        # Status bar at bottom
        self._create_status_bar(main_container)
        
    def _create_toolbar(self, parent):
        """Create toolbar with main actions"""
        toolbar = ttk.Frame(parent, relief=tk.RAISED, borderwidth=1)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # File operations
        ttk.Button(toolbar, text="📁 Load Image", command=self.load_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="💾 Save Labels", command=self.save_labels).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Navigation
        ttk.Button(toolbar, text="⬅️ Previous", command=self.prev_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Next ➡️", command=self.next_image).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Zoom controls
        ttk.Button(toolbar, text="🔍+ Zoom In", command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔍- Zoom Out", command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🔲 Fit", command=self.zoom_fit).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="100%", command=self.zoom_100).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Edit operations
        ttk.Button(toolbar, text="↶ Undo", command=self.undo).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="↷ Redo", command=self.redo).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🗑️ Clear All", command=self.clear_annotations).pack(side=tk.LEFT, padx=2)
        
    def _create_control_panel(self, parent):
        """Create right control panel"""
        control_panel = ttk.Frame(parent, width=300)
        control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        control_panel.pack_propagate(False)
        
        # Class selection
        class_frame = ttk.LabelFrame(control_panel, text="Label Class", padding=10)
        class_frame.pack(fill=tk.X, pady=5)
        
        self.class_var = tk.StringVar(value="panel")
        for class_id, class_info in self.LABEL_CLASSES.items():
            rb = ttk.Radiobutton(
                class_frame,
                text=class_info["name"],
                variable=self.class_var,
                value=class_id,
                command=self.on_class_changed
            )
            rb.pack(anchor=tk.W, pady=2)
        
        # Zoom control
        zoom_frame = ttk.LabelFrame(control_panel, text="Zoom Control", padding=10)
        zoom_frame.pack(fill=tk.X, pady=5)
        
        self.zoom_label = ttk.Label(zoom_frame, text="Zoom: 100%")
        self.zoom_label.pack()
        
        self.zoom_slider = ttk.Scale(
            zoom_frame,
            from_=10,
            to=500,
            orient=tk.HORIZONTAL,
            command=self.on_zoom_slider
        )
        self.zoom_slider.set(100)
        self.zoom_slider.pack(fill=tk.X, pady=5)
        
        # Annotations list
        annotations_frame = ttk.LabelFrame(control_panel, text="Annotations", padding=10)
        annotations_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Scrollable listbox
        list_frame = ttk.Frame(annotations_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.annotations_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.annotations_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.annotations_listbox.yview)
        
        self.annotations_listbox.bind("<<ListboxSelect>>", self.on_annotation_selected)
        
        ttk.Button(annotations_frame, text="Delete Selected", command=self.delete_selected).pack(pady=5)
        
        # Legend
        legend_frame = ttk.LabelFrame(control_panel, text="Color Legend", padding=10)
        legend_frame.pack(fill=tk.X, pady=5)
        
        for class_id, class_info in self.LABEL_CLASSES.items():
            legend_item = ttk.Frame(legend_frame)
            legend_item.pack(anchor=tk.W, pady=2)
            
            color_box = tk.Canvas(legend_item, width=20, height=20, bg=class_info["color"])
            color_box.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(legend_item, text=class_info["name"]).pack(side=tk.LEFT)
        
        # Keyboard shortcuts help
        help_frame = ttk.LabelFrame(control_panel, text="Keyboard Shortcuts", padding=10)
        help_frame.pack(fill=tk.X, pady=5)
        
        shortcuts_text = """
Ctrl+Z: Undo
Ctrl+Y: Redo
Delete: Remove selected
Ctrl+S: Save
←/→: Prev/Next image
1-5: Quick class select
Mouse wheel: Zoom
Right drag: Pan
        """.strip()
        
        ttk.Label(help_frame, text=shortcuts_text, justify=tk.LEFT, font=('Courier', 9)).pack()
        
    def _create_status_bar(self, parent):
        """Create status bar"""
        status_frame = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=1)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_label = ttk.Label(status_frame, text="Ready", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.coords_label = ttk.Label(status_frame, text="X: 0, Y: 0", width=20)
        self.coords_label.pack(side=tk.RIGHT, padx=5)
        
        self.image_info_label = ttk.Label(status_frame, text="No image loaded", width=30)
        self.image_info_label.pack(side=tk.RIGHT, padx=5)
        
    def _bind_keyboard_shortcuts(self):
        """Bind keyboard shortcuts"""
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Delete>", lambda e: self.delete_selected())
        self.root.bind("<Control-s>", lambda e: self.save_labels())
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("<Right>", lambda e: self.next_image())
        
        # Quick class selection
        self.root.bind("1", lambda e: self._quick_select_class("panel"))
        self.root.bind("2", lambda e: self._quick_select_class("dialogue"))
        self.root.bind("3", lambda e: self._quick_select_class("thought"))
        self.root.bind("4", lambda e: self._quick_select_class("face"))
        self.root.bind("5", lambda e: self._quick_select_class("sfx"))
        
    def _quick_select_class(self, class_id: str):
        """Quick select class by number key"""
        self.class_var.set(class_id)
        self.current_class = class_id
        self.update_status(f"Selected class: {self.LABEL_CLASSES[class_id]['name']}")
    
    def load_image(self):
        """Load an image for annotation"""
        file_path = filedialog.askopenfilename(
            title="Select Image",
            initialdir=self.last_dir,
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        self._load_image_file(file_path)
        
    def _load_image_file(self, file_path: str):
        """Internal method to load image from path"""
        try:
            self.image_path = Path(file_path)
            self.last_dir = self.image_path.parent
            
            # Load image
            self.original_image = cv2.imread(str(file_path))
            if self.original_image is None:
                messagebox.showerror("Error", f"Failed to load image: {file_path}")
                return
            
            self.original_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB)
            
            # Reset zoom and pan
            self.zoom_level = 1.0
            self.pan_offset_x = 0
            self.pan_offset_y = 0
            self.zoom_slider.set(100)
            
            # Load existing annotations if present
            self._load_existing_annotations()
            
            # Update image list
            self._update_image_list()
            
            # Display image
            self.display_image()
            
            # Update UI
            h, w = self.original_image.shape[:2]
            self.image_info_label.config(text=f"{self.image_path.name} ({w}x{h})")
            self.update_status(f"Loaded: {self.image_path.name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")
    
    def _load_existing_annotations(self):
        """Load existing annotations from JSON file"""
        json_path = self.image_path.with_suffix('.json')
        self.annotations = []
        
        if json_path.exists():
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                # Handle both old and new format
                if "panels" in data:
                    for panel in data["panels"]:
                        x = panel.get("x", 0)
                        y = panel.get("y", 0)
                        w = panel.get("width", 0)
                        h = panel.get("height", 0)
                        cls = panel.get("class", "panel")
                        
                        self.annotations.append(PanelAnnotation(x, y, x + w, y + h, cls))
                
                self.update_status(f"Loaded {len(self.annotations)} existing annotations")
                
            except Exception as e:
                self.update_status(f"Warning: Could not load existing annotations: {e}")
        
        # Reset history
        self.history = [list(self.annotations)]
        self.history_index = 0
        self.update_annotations_list()
    
    def _update_image_list(self):
        """Update list of images in directory"""
        if not self.image_path:
            return
        
        directory = self.image_path.parent
        extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        
        self.image_list = []
        for ext in extensions:
            self.image_list.extend(directory.glob(f'*{ext}'))
            self.image_list.extend(directory.glob(f'*{ext.upper()}'))
        
        self.image_list = sorted(set(self.image_list))
        
        try:
            self.current_index = self.image_list.index(self.image_path)
        except ValueError:
            self.current_index = -1
    
    def display_image(self):
        """Display the image on canvas with current zoom and pan"""
        if self.original_image is None:
            return
        
        # Apply zoom
        h, w = self.original_image.shape[:2]
        new_w = int(w * self.zoom_level)
        new_h = int(h * self.zoom_level)
        
        # Resize image
        if self.zoom_level != 1.0:
            self.current_image = cv2.resize(
                self.original_image,
                (new_w, new_h),
                interpolation=cv2.INTER_LINEAR if self.zoom_level > 1 else cv2.INTER_AREA
            )
        else:
            self.current_image = self.original_image.copy()
        
        # Convert to PIL Image
        pil_image = Image.fromarray(self.current_image)
        self.photo_image = ImageTk.PhotoImage(pil_image)
        
        # Clear canvas
        self.canvas.delete("all")
        
        # Update scroll region
        self.canvas.config(scrollregion=(0, 0, new_w, new_h))
        
        # Display image
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo_image, tags="image")
        
        # Draw all annotations
        self.draw_all_annotations()
        
        # Update zoom label
        self.zoom_label.config(text=f"Zoom: {int(self.zoom_level * 100)}%")
    
    def draw_all_annotations(self):
        """Draw all annotation rectangles"""
        for i, ann in enumerate(self.annotations):
            color = self.LABEL_CLASSES[ann.label_class]["color"]
            width = 3 if ann == self.selected_annotation else 2
            
            # Scale coordinates by zoom
            x1 = int(ann.x1 * self.zoom_level)
            y1 = int(ann.y1 * self.zoom_level)
            x2 = int(ann.x2 * self.zoom_level)
            y2 = int(ann.y2 * self.zoom_level)
            
            # Draw rectangle
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline=color,
                width=width,
                tags=f"annotation_{i}"
            )
            
            # Draw label
            label_text = f"{ann.label_class}"
            self.canvas.create_text(
                x1 + 5, y1 + 5,
                text=label_text,
                fill=color,
                anchor=tk.NW,
                font=('Arial', 10, 'bold'),
                tags=f"annotation_{i}"
            )
    
    def on_mouse_down(self, event):
        """Start drawing annotation"""
        if self.original_image is None:
            return
        
        # Get canvas coordinates
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Convert to image coordinates
        self.start_x = int(canvas_x / self.zoom_level)
        self.start_y = int(canvas_y / self.zoom_level)
        
        self.drawing = True
        self.current_class = self.class_var.get()
    
    def on_mouse_drag(self, event):
        """Update rectangle while dragging"""
        if not self.drawing or self.original_image is None:
            return
        
        # Remove previous rectangle
        self.canvas.delete("current_rect")
        
        # Get canvas coordinates
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Convert to zoomed coordinates for display
        x1_display = int(self.start_x * self.zoom_level)
        y1_display = int(self.start_y * self.zoom_level)
        
        # Draw current rectangle
        color = self.LABEL_CLASSES[self.current_class]["color"]
        self.current_rect_id = self.canvas.create_rectangle(
            x1_display, y1_display, canvas_x, canvas_y,
            outline=color,
            width=2,
            dash=(4, 4),
            tags="current_rect"
        )
    
    def on_mouse_up(self, event):
        """Finish drawing annotation"""
        if not self.drawing or self.original_image is None:
            return
        
        self.drawing = False
        self.canvas.delete("current_rect")
        
        # Get canvas coordinates
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Convert to image coordinates
        end_x = int(canvas_x / self.zoom_level)
        end_y = int(canvas_y / self.zoom_level)
        
        # Validate minimum size
        if abs(end_x - self.start_x) < 10 or abs(end_y - self.start_y) < 10:
            self.update_status("Annotation too small, ignored")
            return
        
        # Create annotation
        annotation = PanelAnnotation(self.start_x, self.start_y, end_x, end_y, self.current_class)
        self.annotations.append(annotation)
        
        # Save to history
        self._save_to_history()
        
        # Redraw
        self.display_image()
        self.update_annotations_list()
        self.update_status(f"Added {self.current_class} annotation")
    
    def on_pan_start(self, event):
        """Start panning"""
        self.panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.canvas.config(cursor="fleur")
    
    def on_pan_drag(self, event):
        """Pan the canvas"""
        if not self.panning:
            return
        
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        
        self.canvas.xview_scroll(-dx, "units")
        self.canvas.yview_scroll(-dy, "units")
        
        self.pan_start_x = event.x
        self.pan_start_y = event.y
    
    def on_pan_end(self, event):
        """Stop panning"""
        self.panning = False
        self.canvas.config(cursor="crosshair")
    
    def on_mouse_wheel(self, event):
        """Zoom with mouse wheel"""
        if self.original_image is None:
            return
        
        # Determine zoom direction
        if event.num == 4 or event.delta > 0:
            # Zoom in
            self.zoom_level = min(self.zoom_level * 1.25, self.max_zoom)
        else:
            # Zoom out
            self.zoom_level = max(self.zoom_level / 1.25, self.min_zoom)
        
        # Update slider
        self.zoom_slider.set(int(self.zoom_level * 100))
        
        # Redisplay
        self.display_image()
    
    def on_zoom_slider(self, value):
        """Handle zoom slider change"""
        if self.original_image is None:
            return
        
        self.zoom_level = float(value) / 100.0
        self.display_image()
    
    def on_mouse_move(self, event):
        """Update coordinate display"""
        if self.original_image is None:
            return
        
        # Get canvas coordinates
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Convert to image coordinates
        img_x = int(canvas_x / self.zoom_level)
        img_y = int(canvas_y / self.zoom_level)
        
        # Update label
        self.coords_label.config(text=f"X: {img_x}, Y: {img_y}")
    
    def zoom_in(self):
        """Zoom in by 25%"""
        if self.original_image is None:
            return
        self.zoom_level = min(self.zoom_level * 1.25, self.max_zoom)
        self.zoom_slider.set(int(self.zoom_level * 100))
        self.display_image()
    
    def zoom_out(self):
        """Zoom out by 25%"""
        if self.original_image is None:
            return
        self.zoom_level = max(self.zoom_level / 1.25, self.min_zoom)
        self.zoom_slider.set(int(self.zoom_level * 100))
        self.display_image()
    
    def zoom_fit(self):
        """Fit image to canvas"""
        if self.original_image is None:
            return
        
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_h, img_w = self.original_image.shape[:2]
        
        zoom_w = canvas_w / img_w
        zoom_h = canvas_h / img_h
        self.zoom_level = min(zoom_w, zoom_h) * 0.95  # 95% to add margin
        
        self.zoom_slider.set(int(self.zoom_level * 100))
        self.display_image()
    
    def zoom_100(self):
        """Reset to 100% zoom"""
        if self.original_image is None:
            return
        self.zoom_level = 1.0
        self.zoom_slider.set(100)
        self.display_image()
    
    def on_class_changed(self):
        """Handle class selection change"""
        self.current_class = self.class_var.get()
        self.update_status(f"Selected class: {self.LABEL_CLASSES[self.current_class]['name']}")
    
    def update_annotations_list(self):
        """Update the annotations listbox"""
        self.annotations_listbox.delete(0, tk.END)
        
        for i, ann in enumerate(self.annotations):
            w = ann.x2 - ann.x1
            h = ann.y2 - ann.y1
            text = f"{i+1}. {ann.label_class} ({w}x{h})"
            self.annotations_listbox.insert(tk.END, text)
    
    def on_annotation_selected(self, event):
        """Handle annotation selection from list"""
        selection = self.annotations_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_annotation = self.annotations[index]
            self.display_image()
    
    def delete_selected(self):
        """Delete selected annotation"""
        if self.selected_annotation and self.selected_annotation in self.annotations:
            self.annotations.remove(self.selected_annotation)
            self.selected_annotation = None
            self._save_to_history()
            self.display_image()
            self.update_annotations_list()
            self.update_status("Deleted annotation")
    
    def clear_annotations(self):
        """Clear all annotations"""
        if not self.annotations:
            return
        
        if messagebox.askyesno("Confirm", "Delete all annotations?"):
            self.annotations = []
            self.selected_annotation = None
            self._save_to_history()
            self.display_image()
            self.update_annotations_list()
            self.update_status("Cleared all annotations")
    
    def _save_to_history(self):
        """Save current state to history for undo/redo"""
        # Remove any redo history
        self.history = self.history[:self.history_index + 1]
        
        # Add current state
        self.history.append([PanelAnnotation(a.x1, a.y1, a.x2, a.y2, a.label_class) for a in self.annotations])
        self.history_index += 1
        
        # Limit history size
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_index -= 1
    
    def undo(self):
        """Undo last action"""
        if self.history_index > 0:
            self.history_index -= 1
            self.annotations = [PanelAnnotation(a.x1, a.y1, a.x2, a.y2, a.label_class) for a in self.history[self.history_index]]
            self.display_image()
            self.update_annotations_list()
            self.update_status("Undo")
    
    def redo(self):
        """Redo last undone action"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.annotations = [PanelAnnotation(a.x1, a.y1, a.x2, a.y2, a.label_class) for a in self.history[self.history_index]]
            self.display_image()
            self.update_annotations_list()
            self.update_status("Redo")
    
    def save_labels(self):
        """Save annotations to JSON file"""
        if not self.image_path or not self.annotations:
            messagebox.showwarning("Warning", "No annotations to save")
            return
        
        try:
            # Prepare data
            data = {
                "image_path": self.image_path.name,
                "image_width": self.original_image.shape[1],
                "image_height": self.original_image.shape[0],
                "annotations": [ann.to_dict() for ann in self.annotations],
                "num_annotations": len(self.annotations)
            }
            
            # Save to JSON
            json_path = self.image_path.with_suffix('.json')
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.update_status(f"Saved {len(self.annotations)} annotations to {json_path.name}")
            messagebox.showinfo("Success", f"Saved {len(self.annotations)} annotations")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def next_image(self):
        """Load next image in directory"""
        if self.current_index < 0 or self.current_index >= len(self.image_list) - 1:
            self.update_status("No next image")
            return
        
        self.current_index += 1
        self._load_image_file(str(self.image_list[self.current_index]))
    
    def prev_image(self):
        """Load previous image in directory"""
        if self.current_index <= 0:
            self.update_status("No previous image")
            return
        
        self.current_index -= 1
        self._load_image_file(str(self.image_list[self.current_index]))
    
    def update_status(self, message: str):
        """Update status bar message"""
        self.status_label.config(text=message)
        self.root.update_idletasks()


def main():
    root = tk.Tk()
    app = ProfessionalLabelingTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
