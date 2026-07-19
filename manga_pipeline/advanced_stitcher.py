#!/usr/bin/env python3
"""Deterministic chapter stitching with reconstructable strip parts."""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


class AdvancedStitcher:
    """Build a full strip, exact strip parts, and inspectable stitch sections."""

    def __init__(
        self,
        chapter_dir,
        logger: Optional[logging.Logger] = None,
        target_width: int = 1200,
        max_part_height: int = 14000,
        memory_limit_mb: int = 1024,
    ):
        self.chapter_dir = Path(chapter_dir)
        self.clean_dir = self.chapter_dir / "01_clean"
        self.stitched_dir = self.chapter_dir / "02_stitched"
        self.parts_dir = self.stitched_dir / "parts"
        self.sections_dir = self.stitched_dir / "individual"
        self.panels_dir = self.stitched_dir / "panels"
        self.video_scenes_dir = self.stitched_dir / "video_scenes"
        self.logger = logger or logging.getLogger(__name__)
        self.target_width = max(400, int(target_width))
        self.max_part_height = max(2000, int(max_part_height))
        self.memory_limit_bytes = max(256, int(memory_limit_mb)) * 1024 * 1024

    def process_stitching(
        self,
        force_format=None,
        chunk_by_panels=True,
        min_panels_per_chunk=5,
        max_panels_per_chunk=10,
        extract_single_panels=False,
    ) -> Dict:
        del min_panels_per_chunk, max_panels_per_chunk
        sources = self._source_files()
        if not sources:
            return self._failure("No clean images found for stitching")

        self._prepare_output()
        loaded = self._load_images(sources)
        if not loaded:
            return self._failure("No readable clean images found for stitching")

        widths = [image.shape[1] for _, image in loaded]
        canvas_width = min(self.target_width, max(400, int(np.median(widths))))
        normalized = [
            (path, self._normalize_width(image, canvas_width))
            for path, image in loaded
        ]

        sections = []
        previous = None
        total_height = 0
        for index, (path, image) in enumerate(normalized, start=1):
            overlap, seam_score = self._estimate_overlap(previous, image)
            contribution = image[overlap:, :]
            if contribution.size == 0:
                overlap = 0
                seam_score = 0.0
                contribution = image

            section_path = self.sections_dir / f"section_{index:04d}.png"
            self._write_image(section_path, contribution)
            section = {
                "index": index,
                "source": str(path),
                "output": str(section_path),
                "source_height": int(image.shape[0]),
                "height": int(contribution.shape[0]),
                "overlap_removed": int(overlap),
                "seam_score": round(float(seam_score), 4),
                "y_start": int(total_height),
                "y_end": int(total_height + contribution.shape[0]),
            }
            sections.append(section)
            total_height += contribution.shape[0]
            previous = image

        if total_height <= 0:
            return self._failure("Stitching produced an empty strip")

        temp_path = None
        required_bytes = total_height * canvas_width * 3
        if required_bytes > self.memory_limit_bytes:
            handle = tempfile.NamedTemporaryFile(
                prefix="manga_strip_", suffix=".dat", dir=self.stitched_dir, delete=False
            )
            temp_path = Path(handle.name)
            handle.close()
            strip = np.memmap(
                temp_path, dtype=np.uint8, mode="w+", shape=(total_height, canvas_width, 3)
            )
            self.logger.info(
                "Stitch canvas uses disk backing: %.1f MB",
                required_bytes / 1024 / 1024,
            )
        else:
            strip = np.empty((total_height, canvas_width, 3), dtype=np.uint8)

        cursor = 0
        try:
            for section in sections:
                image = cv2.imread(section["output"], cv2.IMREAD_COLOR)
                if image is None:
                    raise RuntimeError(f"Could not reload stitch section: {section['output']}")
                height = image.shape[0]
                strip[cursor:cursor + height, :] = image
                cursor += height

            full_path = self.stitched_dir / "complete_manga_strip.png"
            self._write_image(full_path, strip)

            video_result = self._write_video_scenes(strip, full_path, update_manifest=False)

            part_paths = []
            if chunk_by_panels:
                cuts = self._part_cuts(strip, [s["y_end"] for s in sections])
                start = 0
                for part_index, end in enumerate(cuts, start=1):
                    if end <= start:
                        continue
                    part_path = self.parts_dir / f"stitched_part_{part_index:03d}.png"
                    self._write_image(part_path, strip[start:end, :])
                    part_paths.append(str(part_path))
                    start = end
            else:
                part_paths.append(str(full_path))

            panel_paths = []
            panel_ranges = []
            if extract_single_panels:
                panel_ranges = self._detect_content_ranges(strip)
                if not panel_ranges:
                    panel_ranges = [(s["y_start"], s["y_end"]) for s in sections]
                for panel_index, (start, end) in enumerate(panel_ranges, start=1):
                    panel_path = self.panels_dir / f"panel_{panel_index:04d}.png"
                    self._write_image(panel_path, strip[start:end, :])
                    panel_paths.append(str(panel_path))

            detected_format = force_format or (
                "webtoon" if total_height / max(1, canvas_width) > 2.5 else "manga"
            )
            manifest = {
                "version": 2,
                "format_detected": detected_format,
                "canvas": {
                    "width": canvas_width,
                    "height": total_height,
                    "channels": 3,
                },
                "complete_strip": str(full_path),
                "parts": part_paths,
                "individual_sections": sections,
                "individual_panels": panel_paths,
                "panel_ranges": panel_ranges,
                "video_scenes": video_result.get("scene_files", []),
                "video_scene_ranges": video_result.get("scene_ranges", []),
                "video_scene_manifest": video_result.get("manifest"),
                "reconstructable": True,
            }
            manifest_path = self.stitched_dir / "stitch_manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            output_files = [
                str(full_path),
                *part_paths,
                *panel_paths,
                *video_result.get("scene_files", []),
                str(manifest_path),
            ]
            self.logger.info(
                "Stitch complete: %d sources, %d parts, %d individual strips, %dx%d",
                len(sections),
                len(part_paths),
                len(panel_paths),
                canvas_width,
                total_height,
            )
            return {
                "success": True,
                "format_detected": detected_format,
                "output_files": output_files,
                "complete_strip": str(full_path),
                "part_files": part_paths,
                "section_files": [s["output"] for s in sections],
                "panel_files": panel_paths,
                "video_scene_files": video_result.get("scene_files", []),
                "manifest": str(manifest_path),
                "source_count": len(sections),
                "part_count": len(part_paths),
                "panel_count": len(panel_paths),
                "video_scene_count": int(video_result.get("scene_count", 0)),
            }
        except Exception as exc:
            self.logger.exception("Advanced stitching failed")
            return self._failure(str(exc))
        finally:
            if isinstance(strip, np.memmap):
                strip.flush()
                del strip
            if temp_path and temp_path.exists():
                temp_path.unlink()

    def _source_files(self) -> List[Path]:
        if not self.clean_dir.exists():
            return []
        files = [
            path for path in self.clean_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ]
        return sorted(files, key=lambda path: self._natural_key(path.name))

    def extract_panels_from_complete_strip(self) -> Dict:
        """Rebuild canonical panel cuts from the already-generated full strip."""
        full_path = self.stitched_dir / "complete_manga_strip.png"
        strip = cv2.imread(str(full_path), cv2.IMREAD_COLOR)
        if strip is None:
            return self._failure(f"Complete stitched strip not found: {full_path}")

        if self.panels_dir.exists():
            shutil.rmtree(self.panels_dir)
        self.panels_dir.mkdir(parents=True, exist_ok=True)
        ranges = self._detect_content_ranges(strip)
        panel_paths = []
        for index, (start, end) in enumerate(ranges, start=1):
            panel_path = self.panels_dir / f"panel_{index:04d}.png"
            self._write_image(panel_path, strip[start:end, :])
            panel_paths.append(str(panel_path))

        manifest_path = self.stitched_dir / "stitch_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["individual_panels"] = panel_paths
                manifest["panel_ranges"] = ranges
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except Exception as exc:
                self.logger.warning("Could not update stitch manifest panel cuts: %s", exc)

        self.logger.info("Cut %d filtered panels from the complete stitched strip", len(panel_paths))
        return {
            "success": True,
            "complete_strip": str(full_path),
            "panel_files": panel_paths,
            "panel_ranges": ranges,
            "panel_count": len(panel_paths),
        }

    def extract_video_scenes_from_complete_strip(self) -> Dict:
        """Create strict, bubble-safe video scenes from complete_manga_strip.png."""
        full_path = self.stitched_dir / "complete_manga_strip.png"
        strip = cv2.imread(str(full_path), cv2.IMREAD_COLOR)
        if strip is None:
            return self._failure(f"Complete stitched strip not found: {full_path}")
        return self._write_video_scenes(strip, full_path, update_manifest=True)

    def _write_video_scenes(
        self,
        strip: np.ndarray,
        full_path: Path,
        update_manifest: bool,
    ) -> Dict:
        if self.video_scenes_dir.exists():
            shutil.rmtree(self.video_scenes_dir)
        self.video_scenes_dir.mkdir(parents=True, exist_ok=True)

        scenes, analysis = self._detect_video_scene_ranges(strip)
        scene_files = []
        scene_records = []
        rejected_composition = []
        for source_index, scene in enumerate(scenes, start=1):
            start = int(scene["start"])
            end = int(scene["end"])
            scene_type = str(scene["scene_type"])
            scene_image = np.asarray(strip[start:end, :])
            framed, framing = self._frame_video_scene(
                scene_image,
                scene.get("speech_bubbles", []),
            )
            if self._reject_video_scene(scene, framing):
                rejected_composition.append({
                    "source_index": source_index,
                    "start": start,
                    "end": end,
                    "scene_type": scene_type,
                    "reason": "bubble_or_text_dominant_weak_scene",
                    "framing": framing,
                })
                continue
            index = len(scene_records) + 1
            output_path = self.video_scenes_dir / f"scene_{index:04d}_{scene_type}.png"
            self._write_image(output_path, framed)
            record = dict(scene)
            record["index"] = index
            record["file"] = str(output_path)
            record["framing"] = framing
            scene_records.append(record)
            scene_files.append(str(output_path))

        video_manifest = {
            "version": 1,
            "source": str(full_path),
            "source_size": {
                "width": int(strip.shape[1]),
                "height": int(strip.shape[0]),
            },
            "policy": {
                "source": "complete_manga_strip.png only",
                "dark_scene_aware": True,
                "speech_bubble_boundary_policy": (
                    "dialogue bubbles are optional negative space; outside bubbles are ignored, visible bubble fragments are avoided"
                ),
                "composition_policy": (
                    "favor non-text visual saliency: faces, bodies, action, buildings, and detailed backgrounds"
                ),
                "shape_families": ["landscape_16_9", "square_1_1", "portrait_4_5"],
                "strict_content_filter": True,
            },
            "stats": {
                "scene_count": len(scene_records),
                "night_scene_count": sum(
                    1 for scene in scene_records if scene["scene_type"] == "night"
                ),
                "bubble_candidate_count": len(analysis["bubble_candidates"]),
                "action_beat_candidate_count": len(
                    analysis.get("action_beat_candidates", [])
                ),
                "bubbles_excluded_by_framing": sum(
                    int(scene["framing"]["bubbles_excluded"]) for scene in scene_records
                ),
                "bubbles_remaining": sum(
                    int(scene["framing"]["bubbles_remaining"]) for scene in scene_records
                ),
                "bubbles_kept_whole": sum(
                    int(scene["framing"]["bubbles_remaining"]) for scene in scene_records
                ),
                "partially_cut_bubbles": sum(
                    int(scene["framing"]["partially_cut_bubbles"]) for scene in scene_records
                ),
                "average_bubble_area_ratio": round(float(np.mean([
                    float(scene["framing"].get("bubble_area_ratio", 0.0))
                    for scene in scene_records
                ])) if scene_records else 0.0, 4),
                "rejected_blank_ranges": int(analysis["rejected_blank_ranges"]),
                "rejected_composition_ranges": len(rejected_composition),
            },
            "bubble_candidates": analysis["bubble_candidates"],
            "action_beat_candidates": analysis.get("action_beat_candidates", []),
            "composition_rejects": rejected_composition,
            "scenes": scene_records,
        }
        video_manifest_path = self.video_scenes_dir / "video_scene_manifest.json"
        video_manifest_path.write_text(
            json.dumps(video_manifest, indent=2),
            encoding="utf-8",
        )

        if update_manifest:
            manifest_path = self.stitched_dir / "stitch_manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["video_scenes"] = scene_files
                    manifest["video_scene_ranges"] = [
                        [int(scene["start"]), int(scene["end"])]
                        for scene in scene_records
                    ]
                    manifest["video_scene_manifest"] = str(video_manifest_path)
                    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                except Exception as exc:
                    self.logger.warning("Could not update video scene manifest: %s", exc)

        self.logger.info(
            "Video scene extraction kept %d cuts (%d night scenes, %d protected bubbles)",
            len(scene_records),
            video_manifest["stats"]["night_scene_count"],
            video_manifest["stats"]["bubble_candidate_count"],
        )
        return {
            "success": bool(scene_files),
            "complete_strip": str(full_path),
            "scene_files": scene_files,
            "scene_ranges": [
                [int(scene["start"]), int(scene["end"])] for scene in scene_records
            ],
            "scene_count": len(scene_files),
            "manifest": str(video_manifest_path),
            "stats": video_manifest["stats"],
        }

    @staticmethod
    def _reject_video_scene(scene: Dict, framing: Dict) -> bool:
        """Drop crops that are mostly dialogue/text instead of video-usable artwork."""
        del scene
        bubble_area = float(framing.get("bubble_area_ratio", 0.0))
        partial = int(framing.get("partially_cut_bubbles", 0))
        subject_coverage = float(framing.get("subject_coverage", 0.0))
        visual_density = float(framing.get("visual_density", 0.0))
        quality = float(framing.get("quality_score", 0.0))
        if partial and bubble_area > 0.30 and visual_density < 0.46:
            return True
        if bubble_area > 0.38 and visual_density < 0.36:
            return True
        if bubble_area > 0.48 and visual_density < 0.24:
            return True
        if bubble_area > 0.68 and subject_coverage < 0.86:
            return True
        if quality < 0.24 and subject_coverage < 0.30:
            return True
        return False

    @staticmethod
    def _frame_video_scene(scene: np.ndarray, bubbles: Sequence[Dict]):
        """Render the whole detected scene into a standard video frame.

        Scene splitting decides what belongs together. Framing must preserve that
        artwork instead of zooming into a sub-crop, otherwise faces, bodies, and
        action poses get cut away from the strip.
        """
        height, width = scene.shape[:2]
        natural_ratio = height / float(max(1, width))
        if natural_ratio <= 0.72:
            family = "landscape_16_9"
            target_ratio = 9.0 / 16.0
            output_size = (1600, 900)
        elif natural_ratio <= 1.12:
            family = "square_1_1"
            target_ratio = 1.0
            output_size = (1080, 1080)
        else:
            family = "portrait_4_5"
            target_ratio = 5.0 / 4.0
            output_size = (1080, 1350)

        bubble_boxes = []
        for bubble in bubbles:
            bx = int(bubble.get("x", 0))
            by = int(bubble.get("scene_y", 0))
            bw = int(bubble.get("width", 0))
            bh = int(bubble.get("height", 0))
            if bw > 0 and bh > 0:
                bubble_boxes.append((bx, by, bw, bh))

        center_x = width * 0.5
        center_y = height * 0.5
        scene_gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)
        laplacian = np.abs(cv2.Laplacian(scene_gray, cv2.CV_32F))
        scene_hsv = cv2.cvtColor(scene, cv2.COLOR_BGR2HSV)
        saturation = scene_hsv[:, :, 1].astype(np.float32) / 255.0
        edges = cv2.Canny(scene_gray, 50, 150).astype(np.float32) / 255.0
        local_mean = cv2.GaussianBlur(scene_gray, (0, 0), 5).astype(np.float32)
        local_contrast = np.abs(scene_gray.astype(np.float32) - local_mean) / 64.0
        border_size = max(4, min(width, height) // 18)
        border_pixels = np.concatenate(
            [
                scene_gray[:border_size, :].reshape(-1),
                scene_gray[-border_size:, :].reshape(-1),
                scene_gray[:, :border_size].reshape(-1),
                scene_gray[:, -border_size:].reshape(-1),
            ]
        )
        border_value = float(np.median(border_pixels)) if border_pixels.size else 0.0
        foreground = (
            np.abs(scene_gray.astype(np.float32) - border_value) > 18.0
        ).astype(np.float32)
        lap_scale = float(np.percentile(laplacian, 97)) + 1.0
        lap_norm = np.clip(laplacian / lap_scale, 0.0, 1.0).astype(np.float32)
        visual_weight = (
            lap_norm * 0.36
            + edges * 0.25
            + np.clip(local_contrast, 0.0, 1.0) * 0.20
            + saturation * 0.12
            + foreground * 0.07
        ).astype(np.float32)

        bubble_mask = np.zeros((height, width), dtype=np.float32)
        for bx, by, bw, bh in bubble_boxes:
            pad_x = max(2, min(18, bw // 20))
            pad_y = max(2, min(18, bh // 20))
            x0 = max(0, bx - pad_x)
            y0 = max(0, by - pad_y)
            x1 = min(width, bx + bw + pad_x)
            y1 = min(height, by + bh + pad_y)
            bubble_mask[y0:y1, x0:x1] = 1.0
        visual_weight *= (1.0 - bubble_mask * 0.88)

        total_visual = float(np.sum(visual_weight))
        if total_visual <= 1e-6:
            visual_weight = (lap_norm + foreground * 0.25).astype(np.float32)
            total_visual = float(np.sum(visual_weight))
        yy, xx = np.indices((height, width), dtype=np.float32)
        focus_x = (
            float(np.sum(visual_weight * xx)) / total_visual
            if total_visual > 1e-6 else center_x
        )
        focus_y = (
            float(np.sum(visual_weight * yy)) / total_visual
            if total_visual > 1e-6 else center_y
        )

        output_width, output_height = output_size
        scene_area = float(max(1, width * height))
        bubble_area = float(np.sum(bubble_mask))
        bubble_area_ratio = bubble_area / scene_area
        full_bubbles = 0
        partial_bubbles = 0
        for bx, by, bw, bh in bubble_boxes:
            if bx >= 0 and by >= 0 and bx + bw <= width and by + bh <= height:
                full_bubbles += 1
            else:
                partial_bubbles += 1

        visual_density = min(1.0, (total_visual / scene_area) / 0.16)
        visual_coverage = 1.0
        subject_center_offset = (
            abs(focus_x - center_x) / max(1.0, width)
            + abs(focus_y - center_y) / max(1.0, height)
        )
        detail = min(1.0, float(np.mean(laplacian)) / 26.0)
        contrast = min(1.0, float(np.std(scene_gray)) / 72.0)

        background = AdvancedStitcher._cover_resize(scene, output_width, output_height)
        background = cv2.GaussianBlur(background, (0, 0), sigmaX=20, sigmaY=20)
        background = cv2.addWeighted(background, 0.62, np.zeros_like(background), 0.38, 0)

        contain_scale = min(output_width / float(width), output_height / float(height))
        fitted_width = max(1, int(round(width * contain_scale)))
        fitted_height = max(1, int(round(height * contain_scale)))
        interpolation = cv2.INTER_AREA if contain_scale < 1.0 else cv2.INTER_CUBIC
        fitted = cv2.resize(
            scene,
            (fitted_width, fitted_height),
            interpolation=interpolation,
        )
        x = (output_width - fitted_width) // 2
        y = (output_height - fitted_height) // 2
        framed = background
        framed[y:y + fitted_height, x:x + fitted_width] = fitted

        excluded = 0
        quality_score = min(
            1.0,
            visual_coverage * 0.44
            + visual_density * 0.28
            + detail * 0.16
            + contrast * 0.10
            + 0.02,
        )
        return framed, {
            "shape": family,
            "output_width": int(output_size[0]),
            "output_height": int(output_size[1]),
            "crop_bbox": [0, 0, int(width), int(height)],
            "preserved_full_scene": True,
            "fit_bbox": [int(x), int(y), int(fitted_width), int(fitted_height)],
            "padding": {
                "left": int(x),
                "top": int(y),
                "right": int(output_width - x - fitted_width),
                "bottom": int(output_height - y - fitted_height),
            },
            "bubbles_detected": len(bubble_boxes),
            "bubbles_excluded": int(excluded),
            "bubbles_remaining": int(full_bubbles),
            "partially_cut_bubbles": int(partial_bubbles),
            "bubble_area_ratio": round(float(bubble_area_ratio), 4),
            "subject_coverage": round(float(visual_coverage), 3),
            "visual_density": round(float(visual_density), 3),
            "subject_center_offset": round(float(subject_center_offset), 3),
            "visual_focus": [round(float(focus_x), 1), round(float(focus_y), 1)],
            "quality_score": round(float(quality_score), 3),
        }

    @staticmethod
    def _cover_resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
        src_height, src_width = image.shape[:2]
        scale = max(width / float(max(1, src_width)), height / float(max(1, src_height)))
        resized_width = max(1, int(round(src_width * scale)))
        resized_height = max(1, int(round(src_height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        resized = cv2.resize(
            image,
            (resized_width, resized_height),
            interpolation=interpolation,
        )
        x = max(0, (resized_width - width) // 2)
        y = max(0, (resized_height - height) // 2)
        return resized[y:y + height, x:x + width].copy()

    @staticmethod
    def _intersection_area(a: Sequence[int], b: Sequence[int]) -> int:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x0, y0 = max(ax, bx), max(ay, by)
        x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        return max(0, x1 - x0) * max(0, y1 - y0)

    @staticmethod
    def _integral_sum(integral: np.ndarray, x: int, y: int, width: int, height: int) -> float:
        x1 = x + width
        y1 = y + height
        return float(
            integral[y1, x1]
            - integral[y, x1]
            - integral[y1, x]
            + integral[y, x]
        )

    def _detect_video_scene_ranges(self, strip: np.ndarray):
        """Detect video-ready vertical scenes on bright, dark, and mixed strips."""
        source_height, source_width = strip.shape[:2]
        analysis_width = min(720, source_width)
        if analysis_width != source_width:
            analysis = cv2.resize(
                strip,
                (analysis_width, source_height),
                interpolation=cv2.INTER_AREA,
            )
        else:
            analysis = strip

        gray = cv2.cvtColor(analysis, cv2.COLOR_BGR2GRAY)
        smooth_gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(smooth_gray, 45, 135)
        row_mean = np.mean(smooth_gray, axis=1)
        row_std = np.std(smooth_gray, axis=1)
        edge_density = np.mean(edges > 0, axis=1)
        hsv = cv2.cvtColor(analysis, cv2.COLOR_BGR2HSV)
        row_saturation = np.mean(hsv[:, :, 1].astype(np.float32) / 255.0, axis=1)

        border_width = max(4, analysis_width // 24)
        border_pixels = np.concatenate(
            [smooth_gray[:, :border_width], smooth_gray[:, -border_width:]],
            axis=1,
        )
        border_mean = np.mean(border_pixels, axis=1)
        foreground = np.mean(
            np.abs(smooth_gray.astype(np.float32) - border_mean[:, None]) > 18.0,
            axis=1,
        )

        scale_x = source_width / float(analysis_width)
        bubble_candidates = self._detect_speech_bubble_candidates(
            smooth_gray,
            edges,
            scale_x,
        )
        # Bubbles are OCR/script helpers, not scene anchors. They should not force
        # video cuts to include dialogue that sits outside the useful shot.
        protected = np.zeros(source_height, dtype=bool)

        quiet = (row_std < 10.0) & (edge_density < 0.006) & (foreground < 0.045)
        candidates = []
        for start, end in self._boolean_runs(quiet):
            length = end - start
            if length < 6:
                continue
            target = start + (length // 2)
            cut = self._choose_safe_boundary(
                target,
                max(1, start),
                min(source_height - 1, end),
                row_std,
                edge_density,
                foreground,
                protected,
            )
            if cut is not None:
                candidates.append((cut, 3.0 + min(2.0, length / 40.0), "gutter"))

        window = max(7, min(21, source_height // 1800))
        mean_s = self._smooth_rows(row_mean, window)
        std_s = self._smooth_rows(row_std, window)
        edge_s = self._smooth_rows(edge_density, window)
        foreground_s = self._smooth_rows(foreground, window)
        offset = max(10, min(28, source_height // 500))
        transition = np.zeros(source_height, dtype=np.float32)
        if source_height > offset * 2:
            low = slice(0, source_height - offset * 2)
            high = slice(offset * 2, source_height)
            transition[offset:-offset] = (
                np.abs(mean_s[high] - mean_s[low]) / 255.0
                + np.abs(std_s[high] - std_s[low]) / 90.0
                + np.abs(foreground_s[high] - foreground_s[low]) * 0.9
                + np.abs(edge_s[high] - edge_s[low]) * 5.0
            )
        useful_transition = transition[offset:-offset]
        if useful_transition.size:
            transition_threshold = max(0.16, float(np.percentile(useful_transition, 96)))
            for y in range(offset + 5, source_height - offset - 5):
                value = float(transition[y])
                if value < transition_threshold:
                    continue
                if value < float(np.max(transition[y - 5:y + 6])):
                    continue
                cut = self._choose_safe_boundary(
                    y,
                    max(1, y - 36),
                    min(source_height - 1, y + 37),
                    row_std,
                    edge_density,
                    foreground,
                    protected,
                )
                if cut is not None:
                    candidates.append((cut, 1.0 + value, "transition"))

        action_candidates, action_debug = self._detect_action_beat_boundaries(
            smooth_gray,
            edges,
            row_mean,
            row_std,
            edge_density,
            foreground,
            row_saturation,
        )
        candidates.extend(action_candidates)

        candidates = self._dedupe_boundaries(candidates, min_spacing=180)
        min_scene_height = max(240, min(720, int(source_width * 0.60)))
        if source_width < 260:
            min_scene_height = max(180, min(260, int(source_width * 1.40)))
        min_scene_height = min(source_height, min_scene_height)
        max_scene_height = max(
            min_scene_height * 3,
            max(2200, min(4200, int(source_width * 3.0))),
        )
        target_scene_height = max(
            min_scene_height * 2,
            max(1300, min(2600, int(source_width * 1.75))),
        )

        cuts = []
        cut_kinds = {}
        previous = 0
        for candidate, strength, kind in candidates:
            if candidate - previous < min_scene_height:
                continue
            while candidate - previous > max_scene_height:
                target = min(previous + target_scene_height, candidate - min_scene_height)
                safe = self._choose_safe_boundary(
                    target,
                    previous + min_scene_height,
                    min(previous + max_scene_height, candidate - min_scene_height),
                    row_std,
                    edge_density,
                    foreground,
                    protected,
                )
                if safe is None or safe <= previous:
                    break
                cuts.append(safe)
                cut_kinds[safe] = "length_guard"
                previous = safe
            if candidate - previous >= min_scene_height:
                cuts.append(candidate)
                cut_kinds[candidate] = kind
                previous = candidate

        while source_height - previous > max_scene_height:
            target = previous + target_scene_height
            safe = self._choose_safe_boundary(
                target,
                previous + min_scene_height,
                min(previous + max_scene_height, source_height - min_scene_height),
                row_std,
                edge_density,
                foreground,
                protected,
            )
            if safe is None or safe <= previous:
                break
            cuts.append(safe)
            cut_kinds[safe] = "length_guard"
            previous = safe

        cuts = sorted({int(cut) for cut in cuts if 0 < cut < source_height})
        if cuts and source_height - cuts[-1] < min_scene_height:
            cuts.pop()

        boundaries = [0, *cuts, source_height]
        scenes = []
        rejected_blank_ranges = 0
        for raw_start, raw_end in zip(boundaries, boundaries[1:]):
            start, end = self._trim_quiet_edges(
                raw_start,
                raw_end,
                quiet,
                protected,
                min_scene_height,
            )
            if end - start < min_scene_height:
                rejected_blank_ranges += 1
                continue
            scene_gray = gray[start:end, :]
            scene_edges = edge_density[start:end]
            scene_foreground = foreground[start:end]
            mean_luminance = float(np.mean(scene_gray))
            contrast = float(np.std(scene_gray))
            scene_edge_density = float(np.mean(scene_edges))
            content_ratio = float(np.mean(scene_foreground))
            if contrast < 9.0 and scene_edge_density < 0.003 and content_ratio < 0.02:
                rejected_blank_ranges += 1
                continue
            dark_ratio = float(np.mean(scene_gray < 72))
            if mean_luminance < 96 or dark_ratio > 0.52:
                scene_type = "night"
            elif mean_luminance > 188 and dark_ratio < 0.20:
                scene_type = "bright"
            else:
                scene_type = "mixed"

            bubbles = []
            for bubble in bubble_candidates:
                bubble_start = int(bubble["y"])
                bubble_end = bubble_start + int(bubble["height"])
                if bubble_end <= start or bubble_start >= end:
                    continue
                local = dict(bubble)
                local["scene_y"] = max(0, bubble_start - start)
                bubbles.append(local)

            scenes.append({
                "start": int(start),
                "end": int(end),
                "height": int(end - start),
                "scene_type": scene_type,
                "mean_luminance": round(mean_luminance, 2),
                "contrast": round(contrast, 2),
                "edge_density": round(scene_edge_density, 5),
                "content_ratio": round(content_ratio, 5),
                "speech_bubbles": bubbles,
                "bubble_safe_boundaries": bool(
                    not protected[min(start, source_height - 1)]
                    and not protected[max(0, min(end - 1, source_height - 1))]
                ),
                "start_boundary": cut_kinds.get(raw_start, "strip_start"),
                "end_boundary": cut_kinds.get(raw_end, "strip_end"),
            })

        return scenes, {
            "bubble_candidates": bubble_candidates,
            "action_beat_candidates": action_debug,
            "rejected_blank_ranges": rejected_blank_ranges,
        }

    def _detect_action_beat_boundaries(
        self,
        gray: np.ndarray,
        edges: np.ndarray,
        row_mean: np.ndarray,
        row_std: np.ndarray,
        edge_density: np.ndarray,
        foreground: np.ndarray,
        row_saturation: np.ndarray,
    ):
        """Find internal shot changes inside action panels without relying on gutters."""
        height, width = gray.shape[:2]
        if height < 420:
            return [], []

        laplacian = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
        lap_norm = np.clip(
            laplacian / (float(np.percentile(laplacian, 97)) + 1.0),
            0.0,
            1.0,
        )
        edge_mask = (edges > 0).astype(np.float32)
        saturation_map = np.repeat(
            row_saturation.astype(np.float32)[:, None],
            width,
            axis=1,
        )
        saliency = lap_norm * 0.55 + edge_mask * 0.30 + saturation_map * 0.15
        row_energy = np.mean(saliency, axis=1)
        xs = np.arange(width, dtype=np.float32)
        row_weight = np.sum(saliency, axis=1)
        focus_x = np.full(height, width * 0.5, dtype=np.float32)
        active = row_weight > 1e-6
        focus_x[active] = (
            np.sum(saliency[active] * xs[None, :], axis=1) / row_weight[active]
        )

        span = max(48, min(150, int(width * 0.45)))
        gap = max(8, span // 5)
        smooth_window = max(9, min(41, (span // 3) | 1))
        features = np.vstack([
            self._smooth_rows(row_mean, smooth_window) / 255.0,
            self._smooth_rows(row_std, smooth_window) / 90.0,
            self._smooth_rows(edge_density, smooth_window) * 7.0,
            self._smooth_rows(foreground, smooth_window),
            self._smooth_rows(row_saturation, smooth_window),
            self._smooth_rows(row_energy, smooth_window) * 3.0,
            self._smooth_rows(focus_x, smooth_window) / max(1.0, float(width)),
        ]).T
        weights = np.array([0.55, 0.45, 0.70, 0.55, 0.85, 1.05, 1.15], dtype=np.float32)
        score = np.zeros(height, dtype=np.float32)
        for y in range(span, height - span):
            before = features[y - span:y - gap].mean(axis=0)
            after = features[y + gap:y + span].mean(axis=0)
            score[y] = float(np.abs(before - after).dot(weights))

        useful = score[span:height - span]
        if useful.size == 0:
            return [], []
        threshold = max(0.92, float(np.percentile(useful, 94)))
        local_radius = max(12, span // 4)
        candidates = []
        debug = []
        for y in range(span, height - span):
            value = float(score[y])
            if value < threshold:
                continue
            low = max(span, y - local_radius)
            high = min(height - span, y + local_radius + 1)
            if value < float(np.max(score[low:high])):
                continue
            cut = self._choose_safe_boundary(
                y,
                max(1, y - max(36, span // 2)),
                min(height - 1, y + max(37, span // 2 + 1)),
                row_std,
                edge_density,
                foreground,
                np.zeros(height, dtype=bool),
            )
            if cut is None:
                continue
            strength = 1.6 + min(2.2, value)
            candidates.append((cut, strength, "action_beat"))
            debug.append({
                "target_y": int(y),
                "cut": int(cut),
                "score": round(value, 3),
            })
        return candidates, debug

    @staticmethod
    def _detect_speech_bubble_candidates(
        gray: np.ndarray,
        edges: np.ndarray,
        scale_x: float,
    ) -> List[Dict]:
        height, width = gray.shape[:2]
        candidates = []
        masks = (
            ("light", (gray >= 208).astype(np.uint8) * 255),
            ("dark", (gray <= 48).astype(np.uint8) * 255),
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 7))
        for polarity, mask in masks:
            connected = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            count, _, stats, _ = cv2.connectedComponentsWithStats(connected, connectivity=8)
            for index in range(1, count):
                x, y, box_width, box_height, area = [int(v) for v in stats[index]]
                if box_width < width * 0.10 or box_width > width * 0.94:
                    continue
                if box_height < 24 or box_height > min(560, height * 0.30):
                    continue
                touches_edge = x <= 2 or y <= 2 or x + box_width >= width - 2
                if (
                    touches_edge
                    and box_width > width * 0.44
                    and box_height > height * 0.22
                ):
                    continue
                if area < max(260, int(width * box_height * 0.10)):
                    continue
                fill_ratio = area / float(max(1, box_width * box_height))
                if fill_ratio < 0.20:
                    continue
                roi_edges = float(np.mean(edges[y:y + box_height, x:x + box_width] > 0))
                roi_std = float(np.std(gray[y:y + box_height, x:x + box_width]))
                if roi_edges < 0.0025 and roi_std < 10.0:
                    continue
                candidates.append({
                    "x": int(round(x * scale_x)),
                    "y": y,
                    "width": int(round(box_width * scale_x)),
                    "height": box_height,
                    "polarity": polarity,
                    "confidence": round(min(0.98, 0.40 + fill_ratio * 0.35 + roi_edges * 3.0), 3),
                })

        kept = []
        for candidate in sorted(candidates, key=lambda item: item["confidence"], reverse=True):
            box = [candidate["x"], candidate["y"], candidate["width"], candidate["height"]]
            duplicate = False
            for existing in kept:
                other = [existing["x"], existing["y"], existing["width"], existing["height"]]
                if AdvancedStitcher._bbox_iou(box, other) > 0.48:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)
        return sorted(kept, key=lambda item: (item["y"], item["x"]))

    @staticmethod
    def _bbox_iou(a: Sequence[int], b: Sequence[int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x0, y0 = max(ax, bx), max(ay, by)
        x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        intersection = max(0, x1 - x0) * max(0, y1 - y0)
        union = aw * ah + bw * bh - intersection
        return intersection / float(max(1, union))

    @staticmethod
    def _boolean_runs(mask: np.ndarray) -> List[Tuple[int, int]]:
        runs = []
        start = None
        for index, enabled in enumerate(mask):
            if enabled and start is None:
                start = index
            elif not enabled and start is not None:
                runs.append((start, index))
                start = None
        if start is not None:
            runs.append((start, len(mask)))
        return runs

    @staticmethod
    def _smooth_rows(values: np.ndarray, window: int) -> np.ndarray:
        if window <= 1:
            return values.astype(np.float32)
        kernel = np.ones(window, dtype=np.float32) / float(window)
        return np.convolve(values.astype(np.float32), kernel, mode="same")

    @staticmethod
    def _choose_safe_boundary(
        target: int,
        low: int,
        high: int,
        row_std: np.ndarray,
        edge_density: np.ndarray,
        foreground: np.ndarray,
        protected: np.ndarray,
    ) -> Optional[int]:
        low = max(1, int(low))
        high = min(len(row_std) - 1, int(high))
        if high <= low:
            return None
        indices = np.arange(low, high, dtype=np.int32)
        safe = ~protected[indices]
        if not np.any(safe):
            return None
        indices = indices[safe]
        span = max(1.0, float(high - low))
        score = (
            np.minimum(1.0, row_std[indices] / 55.0) * 0.42
            + np.minimum(1.0, edge_density[indices] / 0.08) * 0.38
            + np.minimum(1.0, foreground[indices]) * 0.16
            + (np.abs(indices - int(target)) / span) * 0.04
        )
        return int(indices[int(np.argmin(score))])

    @staticmethod
    def _dedupe_boundaries(candidates, min_spacing: int):
        kept = []
        for candidate in sorted(candidates, key=lambda item: item[0]):
            if not kept or candidate[0] - kept[-1][0] >= min_spacing:
                kept.append(candidate)
            elif candidate[1] > kept[-1][1]:
                kept[-1] = candidate
        return kept

    @staticmethod
    def _trim_quiet_edges(
        start: int,
        end: int,
        quiet: np.ndarray,
        protected: np.ndarray,
        min_height: int,
        trim_limit: int = 180,
    ) -> Tuple[int, int]:
        trimmed_start = int(start)
        trimmed_end = int(end)
        start_limit = min(end - min_height, start + trim_limit)
        while (
            trimmed_start < start_limit
            and quiet[trimmed_start]
            and not protected[trimmed_start]
        ):
            trimmed_start += 1
        end_limit = max(trimmed_start + min_height, end - trim_limit)
        while (
            trimmed_end - 1 > end_limit
            and quiet[trimmed_end - 1]
            and not protected[trimmed_end - 1]
        ):
            trimmed_end -= 1
        return trimmed_start, trimmed_end

    def _prepare_output(self):
        self.stitched_dir.mkdir(parents=True, exist_ok=True)
        for directory in (
            self.parts_dir,
            self.sections_dir,
            self.panels_dir,
            self.video_scenes_dir,
        ):
            if directory.exists():
                shutil.rmtree(directory)
            directory.mkdir(parents=True, exist_ok=True)
        for name in ("complete_manga_strip.png", "stitch_manifest.json"):
            path = self.stitched_dir / name
            if path.exists():
                path.unlink()
        for old_part in self.stitched_dir.glob("stitched_part_*.png"):
            old_part.unlink()

    def _load_images(self, sources: Sequence[Path]):
        loaded = []
        for path in sources:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.shape[0] < 10 or image.shape[1] < 10:
                self.logger.warning("Skipping unreadable stitch source: %s", path)
                continue
            loaded.append((path, image))
        return loaded

    @staticmethod
    def _normalize_width(image: np.ndarray, target_width: int) -> np.ndarray:
        height, width = image.shape[:2]
        if width == target_width:
            return image
        scale = target_width / float(width)
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        target_height = max(1, int(round(height * scale)))
        return cv2.resize(image, (target_width, target_height), interpolation=interpolation)

    @staticmethod
    def _estimate_overlap(
        previous: Optional[np.ndarray],
        current: np.ndarray,
        max_overlap: int = 420,
        min_overlap: int = 24,
    ) -> Tuple[int, float]:
        if previous is None:
            return 0, 0.0
        height = min(max_overlap, previous.shape[0], current.shape[0])
        if height < min_overlap:
            return 0, 0.0

        prev_gray = cv2.cvtColor(previous[-height:, :], cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(current[:height, :], cv2.COLOR_BGR2GRAY)
        best_overlap = 0
        best_score = 0.0
        for overlap in range(height, min_overlap - 1, -4):
            a = prev_gray[height - overlap:height, :]
            b = curr_gray[:overlap, :]
            if float(a.std()) < 8.0 or float(b.std()) < 8.0:
                continue
            pixel_similarity = 1.0 - (float(np.mean(cv2.absdiff(a, b))) / 255.0)
            edge_a = cv2.Canny(a, 60, 160)
            edge_b = cv2.Canny(b, 60, 160)
            edge_similarity = 1.0 - (float(np.mean(cv2.absdiff(edge_a, edge_b))) / 255.0)
            score = (pixel_similarity * 0.65) + (edge_similarity * 0.35)
            if score > best_score:
                best_score = score
                best_overlap = overlap
            if score >= 0.94:
                return overlap, score
        return (best_overlap, best_score) if best_score >= 0.90 else (0, best_score)

    def _part_cuts(self, strip: np.ndarray, section_ends: Sequence[int]) -> List[int]:
        total_height = strip.shape[0]
        if total_height <= self.max_part_height:
            return [total_height]

        cuts = []
        start = 0
        boundaries = sorted({int(v) for v in section_ends if 0 < v < total_height})
        min_part_height = max(1600, int(self.max_part_height * 0.55))
        while total_height - start > self.max_part_height:
            ideal = start + self.max_part_height
            candidates = [
                value for value in boundaries
                if start + min_part_height <= value <= ideal
            ]
            cut = max(candidates) if candidates else self._safe_cut(strip, start, ideal)
            if cut <= start:
                cut = min(ideal, total_height)
            cuts.append(cut)
            start = cut
        if start < total_height:
            cuts.append(total_height)
        return cuts

    @staticmethod
    def _safe_cut(strip: np.ndarray, start: int, ideal: int) -> int:
        low = max(start + 1000, ideal - 900)
        high = min(strip.shape[0] - 1, ideal + 300)
        if high <= low:
            return ideal
        sample = strip[low:high, :]
        gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        brightness = np.mean(gray, axis=1) / 255.0
        edges = cv2.Canny(gray, 60, 160)
        edge_density = np.mean(edges > 0, axis=1)
        score = brightness - (edge_density * 2.5)
        return low + int(np.argmax(score))

    @staticmethod
    def _detect_content_ranges(strip: np.ndarray) -> List[Tuple[int, int]]:
        """Find useful vertical cuts directly from the completed strip.

        The ranges are non-overlapping and cover only content. Long continuous
        scenes are split at the quietest nearby row so downstream OCR never has
        to load an enormous image.
        """
        gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
        row_mean = np.mean(gray, axis=1)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.mean(edges > 0, axis=1)
        background = float(np.percentile(row_mean, 88))
        content = (np.abs(row_mean - background) > 9.0) | (edge_density > 0.010)
        kernel_size = max(3, min(31, strip.shape[0] // 2500))
        kernel = np.ones(kernel_size, dtype=np.uint8)
        content = np.convolve(content.astype(np.uint8), kernel, mode="same") > 0

        ranges = []
        start = None
        for index, has_content in enumerate(content):
            if has_content and start is None:
                start = index
            elif not has_content and start is not None:
                if index - start >= 80:
                    ranges.append((start, index))
                start = None
        if start is not None and len(content) - start >= 80:
            ranges.append((start, len(content)))

        merged = []
        for start, end in ranges:
            if merged and start - merged[-1][1] < 24:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))

        split_ranges = []
        for start, end in merged:
            split_ranges.extend(
                AdvancedStitcher._split_long_content_range(
                    start,
                    end,
                    row_mean,
                    edge_density,
                    background,
                )
            )

        filtered = []
        for start, end in split_ranges:
            candidate = gray[start:end, :]
            height = end - start
            if candidate.size == 0 or height < 140:
                continue
            white_ratio = float(np.mean(candidate > 242))
            contrast = float(candidate.std())
            candidate_edges = float(np.mean(edge_density[start:end]))
            dark_ratio = float(np.mean(candidate < 232))
            if white_ratio > 0.955 and candidate_edges < 0.006:
                continue
            if contrast < 14.0 and candidate_edges < 0.004:
                continue
            if dark_ratio < 0.018 and candidate_edges < 0.0035:
                continue
            filtered.append((int(start), int(end)))
        return filtered

    @staticmethod
    def _split_long_content_range(
        start: int,
        end: int,
        row_mean: np.ndarray,
        edge_density: np.ndarray,
        background: float,
        max_height: int = 3200,
        target_height: int = 2600,
    ) -> List[Tuple[int, int]]:
        ranges = []
        while end - start > max_height:
            target = start + target_height
            low = max(start + 900, target - 500)
            high = min(end - 900, target + 500)
            if high <= low:
                cut = min(start + max_height, end)
            else:
                brightness_delta = np.abs(row_mean[low:high] - background) / 255.0
                score = brightness_delta + (edge_density[low:high] * 3.0)
                cut = low + int(np.argmin(score))
            if cut <= start:
                cut = min(start + max_height, end)
            ranges.append((start, cut))
            start = cut
        if end > start:
            ranges.append((start, end))
        return ranges

    @staticmethod
    def _write_image(path: Path, image: np.ndarray):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_PNG_COMPRESSION, 4]):
            raise RuntimeError(f"Failed to write image: {path}")

    @staticmethod
    def _natural_key(value: str):
        return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]

    @staticmethod
    def _failure(error: str) -> Dict:
        return {
            "success": False,
            "format_detected": None,
            "output_files": [],
            "error": error,
        }
