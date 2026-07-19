#!/usr/bin/env python3
"""Structured manga dialogue, scene, and speaker extraction.

The extractor is intentionally conservative: it records confidence and leaves
speakers as Unknown when the image does not provide enough evidence. Per-series
character context is stored outside individual chapters so later chapters can
reuse the same manga's speaker memory without mixing it with another series.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import pytesseract


try:
    import easyocr  # type: ignore

    EASYOCR_AVAILABLE = True
except Exception:
    easyocr = None
    EASYOCR_AVAILABLE = False


LOGGER = logging.getLogger(__name__)
_CONTEXT_LOCKS: Dict[str, threading.RLock] = {}
_CONTEXT_LOCKS_GUARD = threading.Lock()


def _context_lock(context_dir: Path) -> threading.RLock:
    key = str(Path(context_dir).resolve())
    with _CONTEXT_LOCKS_GUARD:
        if key not in _CONTEXT_LOCKS:
            _CONTEXT_LOCKS[key] = threading.RLock()
        return _CONTEXT_LOCKS[key]


def _natural_sort_key(text: str) -> List[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _norm_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "", name.lower())
    return cleaned[:64]


def _clip_bbox(bbox: Sequence[int], width: int, height: int, pad: int = 0) -> List[int]:
    x, y, w, h = [int(v) for v in bbox]
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(width, x + w + pad)
    y1 = min(height, y + h + pad)
    return [x0, y0, max(0, x1 - x0), max(0, y1 - y0)]


def _bbox_center(bbox: Sequence[int]) -> Tuple[float, float]:
    x, y, w, h = bbox
    return float(x) + float(w) * 0.5, float(y) + float(h) * 0.5


@dataclass
class TextBlock:
    text: str
    raw_text: str
    bbox: List[int]
    confidence: float
    engine: str
    block_type: str = "dialogue"
    box_style: str = "mixed"
    name_hint: Optional[str] = None
    speaker: str = "Unknown"
    speaker_id: Optional[str] = None
    speaker_confidence: float = 0.0
    speaker_reason: str = "unassigned"

    def as_dict(self, block_id: str) -> Dict[str, Any]:
        return {
            "id": block_id,
            "text": self.text,
            "raw_text": self.raw_text,
            "type": self.block_type,
            "speaker": self.speaker,
            "speaker_id": self.speaker_id,
            "speaker_confidence": round(float(self.speaker_confidence), 3),
            "speaker_reason": self.speaker_reason,
            "name_hint": self.name_hint,
            "bbox": [int(v) for v in self.bbox],
            "box_style": self.box_style,
            "ocr_engine": self.engine,
            "ocr_confidence": round(float(self.confidence), 2),
        }


@dataclass
class FaceCandidate:
    bbox: List[int]
    confidence: float
    signature: List[float]
    profile_id: Optional[str] = None
    display_name: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "bbox": [int(v) for v in self.bbox],
            "confidence": round(float(self.confidence), 3),
            "profile_id": self.profile_id,
            "display_name": self.display_name,
        }


@dataclass
class PanelAnalysis:
    panel_name: str
    panel_path: str
    size: Tuple[int, int]
    scene: Dict[str, Any]
    text_blocks: List[TextBlock] = field(default_factory=list)
    faces: List[FaceCandidate] = field(default_factory=list)


class SeriesCharacterContext:
    """Per-series character memory backed by JSON on disk."""

    def __init__(self, context_dir: Path, series_name: str, logger: Optional[logging.Logger] = None):
        self.context_dir = Path(context_dir)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.context_dir / "character_profiles.json"
        self.series_name = series_name
        self.logger = logger or LOGGER
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.alias_index: Dict[str, str] = {}
        self.next_index = 1
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
            self.next_index = int(payload.get("next_index", 1))
            self._rebuild_alias_index()
        except Exception as exc:
            self.logger.warning(f"Character context could not be loaded: {exc}")
            self.profiles = {}
            self.alias_index = {}
            self.next_index = 1

    def save(self) -> None:
        payload = {
            "series_name": self.series_name,
            "updated_at": _now(),
            "next_index": self.next_index,
            "profile_count": len(self.profiles),
            "profiles": self.profiles,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _rebuild_alias_index(self) -> None:
        self.alias_index = {}
        for profile_id, profile in self.profiles.items():
            aliases = profile.get("aliases", [])
            display = profile.get("display_name")
            for alias in list(aliases) + ([display] if display else []):
                key = _norm_name(str(alias))
                if key:
                    self.alias_index[key] = profile_id

    def _new_profile_id(self) -> str:
        while True:
            profile_id = f"Character_{self.next_index:02d}"
            self.next_index += 1
            if profile_id not in self.profiles:
                return profile_id

    def _create_profile(
        self,
        chapter_name: str,
        preferred_name: Optional[str] = None,
        signature: Optional[Sequence[float]] = None,
    ) -> str:
        profile_id = self._new_profile_id()
        display_name = preferred_name.strip() if preferred_name and preferred_name.strip() else profile_id
        aliases = [display_name] if preferred_name else []
        self.profiles[profile_id] = {
            "id": profile_id,
            "display_name": display_name,
            "aliases": aliases,
            "first_seen_chapter": chapter_name,
            "last_seen_chapter": chapter_name,
            "observations": 0,
            "named_observations": 1 if preferred_name else 0,
            "dialogue_count": 0,
            "dialogue_samples": [],
            "face_signatures": [],
            "scene_counts": {},
            "notes": "Named by OCR label." if preferred_name else "Unnamed recurring visual speaker.",
        }
        if signature:
            self._add_signature(profile_id, signature)
        self._rebuild_alias_index()
        return profile_id

    def profile_for_name(self, name: str, chapter_name: str) -> str:
        key = _norm_name(name)
        if key and key in self.alias_index:
            profile_id = self.alias_index[key]
            self._touch(profile_id, chapter_name)
            return profile_id
        return self._create_profile(chapter_name, preferred_name=name)

    def public_name(self, profile_id: Optional[str]) -> str:
        if not profile_id or profile_id not in self.profiles:
            return "Unknown"
        return str(self.profiles[profile_id].get("display_name") or profile_id)

    def match_face(self, signature: Optional[Sequence[float]], max_distance: float = 0.18) -> Tuple[Optional[str], float]:
        if not signature:
            return None, 0.0
        best_id = None
        best_dist = 999.0
        for profile_id, profile in self.profiles.items():
            signatures = profile.get("face_signatures") or []
            if not signatures:
                continue
            distances = [self._signature_distance(signature, stored) for stored in signatures]
            if distances:
                dist = min(distances)
                if dist < best_dist:
                    best_id = profile_id
                    best_dist = dist
        if best_id and best_dist <= max_distance:
            return best_id, max(0.0, min(1.0, 1.0 - (best_dist / max_distance)))
        return None, 0.0

    def match_or_create_face(
        self,
        signature: Optional[Sequence[float]],
        chapter_name: str,
        preferred_name: Optional[str] = None,
    ) -> Tuple[str, float, str]:
        profile_id = self.profile_for_name(preferred_name, chapter_name) if preferred_name else None
        matched_id, confidence = self.match_face(signature)

        if matched_id and profile_id and matched_id != profile_id:
            self.merge_profiles(profile_id, matched_id)
            matched_id = profile_id

        if matched_id:
            if preferred_name:
                self.add_alias(matched_id, preferred_name)
            if signature:
                self._add_signature(matched_id, signature)
            self._touch(matched_id, chapter_name)
            return matched_id, max(confidence, 0.62 if preferred_name else confidence), "matched_face"

        if profile_id:
            if signature:
                self._add_signature(profile_id, signature)
            self._touch(profile_id, chapter_name)
            return profile_id, 0.9, "explicit_name"

        profile_id = self._create_profile(chapter_name, signature=signature)
        return profile_id, 0.42, "new_visual_profile"

    def merge_profiles(self, keeper_id: str, duplicate_id: str) -> None:
        if keeper_id == duplicate_id or keeper_id not in self.profiles or duplicate_id not in self.profiles:
            return
        keeper = self.profiles[keeper_id]
        duplicate = self.profiles.pop(duplicate_id)
        for alias in duplicate.get("aliases", []):
            self.add_alias(keeper_id, alias)
        for signature in duplicate.get("face_signatures", []):
            self._add_signature(keeper_id, signature)
        keeper["observations"] = int(keeper.get("observations", 0)) + int(duplicate.get("observations", 0))
        keeper["dialogue_count"] = int(keeper.get("dialogue_count", 0)) + int(duplicate.get("dialogue_count", 0))
        samples = list(keeper.get("dialogue_samples", [])) + list(duplicate.get("dialogue_samples", []))
        keeper["dialogue_samples"] = samples[-20:]
        self._rebuild_alias_index()

    def add_alias(self, profile_id: str, name: str) -> None:
        if profile_id not in self.profiles:
            return
        cleaned = name.strip()
        if not cleaned:
            return
        aliases = list(self.profiles[profile_id].get("aliases", []))
        if cleaned not in aliases:
            aliases.append(cleaned)
        self.profiles[profile_id]["aliases"] = aliases[-12:]
        display = self.profiles[profile_id].get("display_name")
        if display == profile_id:
            self.profiles[profile_id]["display_name"] = cleaned
            self.profiles[profile_id]["notes"] = "Named by OCR label after visual tracking."
        self.profiles[profile_id]["named_observations"] = int(self.profiles[profile_id].get("named_observations", 0)) + 1
        self._rebuild_alias_index()

    def observe_dialogue(
        self,
        profile_id: Optional[str],
        text: str,
        chapter_name: str,
        panel_name: str,
        scene_label: str,
    ) -> None:
        if not profile_id or profile_id not in self.profiles:
            return
        profile = self.profiles[profile_id]
        self._touch(profile_id, chapter_name)
        profile["dialogue_count"] = int(profile.get("dialogue_count", 0)) + 1
        sample = {"chapter": chapter_name, "panel": panel_name, "text": text[:240]}
        samples = list(profile.get("dialogue_samples", []))
        if sample not in samples:
            samples.append(sample)
        profile["dialogue_samples"] = samples[-20:]
        scene_counts = dict(profile.get("scene_counts", {}))
        scene_counts[scene_label] = int(scene_counts.get(scene_label, 0)) + 1
        profile["scene_counts"] = scene_counts

    def observe_face(self, profile_id: Optional[str], signature: Optional[Sequence[float]], chapter_name: str) -> None:
        if not profile_id or profile_id not in self.profiles:
            return
        self._touch(profile_id, chapter_name)
        if signature:
            self._add_signature(profile_id, signature)

    def _touch(self, profile_id: str, chapter_name: str) -> None:
        if profile_id not in self.profiles:
            return
        profile = self.profiles[profile_id]
        profile["last_seen_chapter"] = chapter_name
        profile["observations"] = int(profile.get("observations", 0)) + 1

    def _add_signature(self, profile_id: str, signature: Sequence[float]) -> None:
        if profile_id not in self.profiles or not signature:
            return
        rounded = [round(float(v), 5) for v in signature]
        signatures = list(self.profiles[profile_id].get("face_signatures", []))
        if not signatures:
            signatures.append(rounded)
        else:
            distances = [self._signature_distance(rounded, stored) for stored in signatures]
            if min(distances) > 0.04:
                signatures.append(rounded)
        self.profiles[profile_id]["face_signatures"] = signatures[-16:]

    @staticmethod
    def _signature_distance(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 999.0
        av = np.asarray(a, dtype=np.float32)
        bv = np.asarray(b, dtype=np.float32)
        denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
        if denom <= 1e-8:
            return 999.0
        return float(1.0 - (np.dot(av, bv) / denom))

    def chapter_snapshot(self) -> Dict[str, Any]:
        profiles = []
        for profile_id in sorted(self.profiles, key=_natural_sort_key):
            profile = dict(self.profiles[profile_id])
            profile["face_signature_count"] = len(profile.get("face_signatures", []))
            profile.pop("face_signatures", None)
            profiles.append(profile)
        return {
            "series_name": self.series_name,
            "context_path": str(self.path),
            "profile_count": len(profiles),
            "named_profile_count": sum(
                1 for profile in profiles if profile.get("display_name") != profile.get("id")
            ),
            "profiles": profiles,
        }


class DialogueExtractor:
    """Extract OCR dialogue blocks and map them to per-series speakers."""

    _easyocr_readers: Dict[str, Any] = {}

    def __init__(
        self,
        chapter_dir: str | Path,
        logger: Optional[logging.Logger] = None,
        ocr_lang: str = "eng",
        confidence_threshold: int = 40,
        use_easyocr: bool = False,
        max_workers: Optional[int] = None,
        series_context_dir: Optional[str | Path] = None,
    ):
        self.chapter_dir = Path(chapter_dir)
        self.logger = logger or LOGGER
        self.ocr_lang = ocr_lang
        self.confidence_threshold = max(18, min(85, int(confidence_threshold)))
        self.use_easyocr = bool(use_easyocr and EASYOCR_AVAILABLE)
        self.max_workers = max_workers or max(1, min(4, (os.cpu_count() or 2)))
        self.panels_dir = self.chapter_dir / "panels"
        self.text_dir = self.chapter_dir / "03_text"
        self.transcripts_dir = self.text_dir / "transcripts"
        self.dialogue_dir = self.text_dir / "dialogue"
        self.script_dir = self.chapter_dir / "script"
        self.series_root = self.chapter_dir.parent
        self.series_name = self.series_root.name
        self.context_dir = Path(series_context_dir) if series_context_dir else self.series_root / "series_context"
        self.face_cascade = self._load_face_cascade()

    def process_chapter(self, max_panels: Optional[int] = None) -> Dict[str, Any]:
        panel_files = self._panel_files()
        if max_panels:
            panel_files = panel_files[:max_panels]
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.dialogue_dir.mkdir(parents=True, exist_ok=True)
        self.script_dir.mkdir(parents=True, exist_ok=True)

        if not panel_files:
            return {"success": False, "error": "No panel images found", "text_files": []}

        self._clear_previous_outputs()
        self.logger.info(f"Structured dialogue extraction started for {len(panel_files)} panels")

        analyses: List[PanelAnalysis] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._analyze_panel, path): path for path in panel_files}
            for future in as_completed(futures):
                panel_path = futures[future]
                try:
                    analyses.append(future.result())
                except Exception as exc:
                    self.logger.warning(f"Dialogue OCR failed for {panel_path.name}: {exc}")

        analyses.sort(key=lambda item: _natural_sort_key(item.panel_name))
        # OCR remains parallel. Only profile matching and persistence are
        # serialized per manga so simultaneous chapters cannot lose context.
        with _context_lock(self.context_dir):
            return self._finalize_chapter(analyses)

    def _finalize_chapter(self, analyses: List[PanelAnalysis]) -> Dict[str, Any]:
        context = SeriesCharacterContext(self.context_dir, self.series_name, logger=self.logger)

        text_files: List[Path] = []
        chapter_panels: List[Dict[str, Any]] = []
        total_blocks = 0
        speaker_counts: Dict[str, int] = {}
        dark_panels = 0

        for analysis in analyses:
            if analysis.scene.get("is_dark"):
                dark_panels += 1
            self._assign_speakers(analysis, context)
            panel_payload = self._panel_payload(analysis)
            panel_json_path = self.dialogue_dir / f"{Path(analysis.panel_name).stem}.json"
            panel_json_path.write_text(json.dumps(panel_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            transcript_path = self._write_transcript(analysis)
            if transcript_path:
                text_files.append(transcript_path)
            chapter_panels.append(panel_payload)
            for block in analysis.text_blocks:
                total_blocks += 1
                speaker_counts[block.speaker] = int(speaker_counts.get(block.speaker, 0)) + 1
                if block.speaker_id:
                    context.observe_dialogue(
                        block.speaker_id,
                        block.text,
                        self.chapter_dir.name,
                        analysis.panel_name,
                        str(analysis.scene.get("label", "unknown")),
                    )
            for face in analysis.faces:
                if face.profile_id:
                    context.observe_face(face.profile_id, face.signature, self.chapter_dir.name)

        context.save()
        characters = context.chapter_snapshot()
        characters_path = self.script_dir / "characters.json"
        characters_path.write_text(json.dumps(characters, ensure_ascii=False, indent=2), encoding="utf-8")

        payload = {
            "chapter": self.chapter_dir.name,
            "series": self.series_name,
            "generated_at": _now(),
            "series_context_path": str(context.path),
            "stats": {
                "panels": len(chapter_panels),
                "text_blocks": total_blocks,
                "text_panels": len(text_files),
                "dark_panels": dark_panels,
                "speakers": speaker_counts,
                "character_profiles": characters.get("profile_count", 0),
                "named_character_profiles": characters.get("named_profile_count", 0),
            },
            "characters": characters,
            "panels": chapter_panels,
        }
        chapter_path = self.script_dir / "chapter_dialogue.json"
        chapter_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self.logger.info(
            "Structured dialogue extraction complete: "
            f"{total_blocks} text blocks, {characters.get('profile_count', 0)} character profiles"
        )
        return {
            "success": True,
            "text_files": text_files,
            "dialogue_json": chapter_path,
            "characters_json": characters_path,
            "series_context": context.path,
            "stats": payload["stats"],
        }

    def _panel_files(self) -> List[Path]:
        files: List[Path] = []
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            files.extend(self.panels_dir.glob(pattern))
        return sorted(files, key=lambda path: _natural_sort_key(path.name))

    def _clear_previous_outputs(self) -> None:
        for directory in (self.transcripts_dir, self.dialogue_dir):
            for path in directory.glob("*"):
                if path.is_file() and path.suffix.lower() in {".txt", ".json"}:
                    path.unlink()

    def _analyze_panel(self, panel_path: Path) -> PanelAnalysis:
        img = cv2.imread(str(panel_path))
        if img is None:
            raise ValueError(f"Unreadable panel image: {panel_path}")
        height, width = img.shape[:2]
        scene = self._scene_profile(img)
        text_blocks = self._extract_text_blocks(img, scene)
        faces = self._detect_faces(img)
        return PanelAnalysis(
            panel_name=panel_path.name,
            panel_path=str(panel_path),
            size=(width, height),
            scene=scene,
            text_blocks=text_blocks,
            faces=faces,
        )

    def _scene_profile(self, img: np.ndarray) -> Dict[str, Any]:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        std = float(np.std(gray))
        dark_ratio = float(np.mean(gray < 70))
        light_ratio = float(np.mean(gray > 210))
        edge_density = float(np.mean(cv2.Canny(gray, 60, 140) > 0))
        is_dark = dark_ratio > 0.38 or mean < 96
        if is_dark and light_ratio < 0.2:
            label = "night_or_black_background"
        elif edge_density > 0.12:
            label = "action_or_high_detail"
        elif light_ratio > 0.55:
            label = "bright_dialogue"
        else:
            label = "mixed_scene"
        return {
            "label": label,
            "is_dark": bool(is_dark),
            "mean_luminance": round(mean, 2),
            "contrast": round(std, 2),
            "dark_pixel_ratio": round(dark_ratio, 4),
            "light_pixel_ratio": round(light_ratio, 4),
            "edge_density": round(edge_density, 4),
        }

    def _extract_text_blocks(self, img: np.ndarray, scene: Dict[str, Any]) -> List[TextBlock]:
        variants = self._ocr_variants(img, scene)
        all_blocks: List[TextBlock] = []
        best_score = -1.0
        best_blocks: List[TextBlock] = []

        for engine_name, variant in variants:
            blocks = self._tesseract_blocks(variant, engine_name, img.shape[:2])
            score = sum(max(1, len(block.text)) * max(1.0, block.confidence) for block in blocks)
            if score > best_score:
                best_score = score
                best_blocks = blocks

        all_blocks.extend(best_blocks)

        if self.use_easyocr and (not all_blocks or best_score < 250):
            all_blocks.extend(self._easyocr_blocks(img))

        blocks = self._dedupe_blocks(all_blocks)
        height, width = img.shape[:2]
        for block in blocks:
            self._split_name_hint(block)
            block.box_style = self._box_style(img, block.bbox, scene)
            block.block_type = self._classify_block(block, width, height)
        blocks.sort(key=lambda block: (block.bbox[1], block.bbox[0]))
        return blocks

    def _ocr_variants(self, img: np.ndarray, scene: Dict[str, Any]) -> List[Tuple[str, np.ndarray]]:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        max_side = 2200
        if max(h, w) > max_side:
            scale = max_side / float(max(h, w))
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        blur = cv2.medianBlur(gray, 3)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(blur)
        _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )
        variants = [
            ("tesseract:clahe", clahe),
            ("tesseract:otsu", otsu),
            ("tesseract:adaptive", adaptive),
        ]
        if scene.get("is_dark"):
            inverted = 255 - gray
            inv_clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(inverted)
            inv_adaptive = cv2.adaptiveThreshold(
                inv_clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7
            )
            variants.insert(0, ("tesseract:dark_inverted", inv_clahe))
            variants.insert(1, ("tesseract:dark_adaptive", inv_adaptive))
        return variants

    def _tesseract_blocks(self, img: np.ndarray, engine_name: str, original_shape: Tuple[int, int]) -> List[TextBlock]:
        config = f"--psm 6 --oem 3 -l {self.ocr_lang}"
        try:
            data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            self.logger.debug(f"Tesseract variant failed ({engine_name}): {exc}")
            return []

        image_h, image_w = img.shape[:2]
        original_h, original_w = original_shape
        sx = float(original_w) / max(1, image_w)
        sy = float(original_h) / max(1, image_h)
        words: List[Dict[str, Any]] = []
        for i, raw in enumerate(data.get("text", [])):
            text = self._clean_text(str(raw))
            conf = _safe_float(data.get("conf", [0])[i], -1.0)
            if conf < max(8, self.confidence_threshold - 22) or self._is_noise(text):
                continue
            x = int(_safe_int(data["left"][i]) * sx)
            y = int(_safe_int(data["top"][i]) * sy)
            w = max(1, int(_safe_int(data["width"][i]) * sx))
            h = max(1, int(_safe_int(data["height"][i]) * sy))
            words.append(
                {
                    "text": text,
                    "conf": conf,
                    "bbox": [x, y, w, h],
                    "line_key": (
                        _safe_int(data.get("block_num", [0])[i]),
                        _safe_int(data.get("par_num", [0])[i]),
                        _safe_int(data.get("line_num", [0])[i]),
                    ),
                }
            )
        return self._merge_words(words, engine_name)

    def _merge_words(self, words: List[Dict[str, Any]], engine_name: str) -> List[TextBlock]:
        if not words:
            return []
        lines: List[Dict[str, Any]] = []
        grouped: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
        for word in words:
            grouped.setdefault(word["line_key"], []).append(word)
        for line_words in grouped.values():
            line_words.sort(key=lambda item: item["bbox"][0])
            text = self._clean_text(" ".join(item["text"] for item in line_words))
            if self._is_noise(text):
                continue
            xs = [item["bbox"][0] for item in line_words]
            ys = [item["bbox"][1] for item in line_words]
            x2s = [item["bbox"][0] + item["bbox"][2] for item in line_words]
            y2s = [item["bbox"][1] + item["bbox"][3] for item in line_words]
            conf = float(np.mean([item["conf"] for item in line_words]))
            lines.append({"text": text, "bbox": [min(xs), min(ys), max(x2s) - min(xs), max(y2s) - min(ys)], "conf": conf})

        lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        if not lines:
            return []

        blocks: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for line in lines:
            if current is None:
                current = {"lines": [line], "bbox": line["bbox"][:], "conf": [line["conf"]]}
                continue
            cb = current["bbox"]
            lb = line["bbox"]
            y_gap = lb[1] - (cb[1] + cb[3])
            x_overlap = max(0, min(cb[0] + cb[2], lb[0] + lb[2]) - max(cb[0], lb[0]))
            overlap_ratio = x_overlap / float(max(1, min(cb[2], lb[2])))
            close_x = abs((cb[0] + cb[2] * 0.5) - (lb[0] + lb[2] * 0.5)) < max(80, cb[2] * 0.7)
            if y_gap <= max(24, cb[3] * 0.85) and (overlap_ratio > 0.15 or close_x):
                current["lines"].append(line)
                current["conf"].append(line["conf"])
                x0 = min(cb[0], lb[0])
                y0 = min(cb[1], lb[1])
                x1 = max(cb[0] + cb[2], lb[0] + lb[2])
                y1 = max(cb[1] + cb[3], lb[1] + lb[3])
                current["bbox"] = [x0, y0, x1 - x0, y1 - y0]
            else:
                blocks.append(current)
                current = {"lines": [line], "bbox": line["bbox"][:], "conf": [line["conf"]]}
        if current:
            blocks.append(current)

        text_blocks = []
        for block in blocks:
            text = self._clean_text(" ".join(line["text"] for line in block["lines"]))
            if self._is_noise(text):
                continue
            text_blocks.append(
                TextBlock(
                    text=text,
                    raw_text=text,
                    bbox=[int(v) for v in block["bbox"]],
                    confidence=float(np.mean(block["conf"])),
                    engine=engine_name,
                )
            )
        return text_blocks

    def _easyocr_blocks(self, img: np.ndarray) -> List[TextBlock]:
        reader = self._get_easyocr_reader()
        if reader is None:
            return []
        try:
            results = reader.readtext(img, detail=1, paragraph=False)
        except Exception as exc:
            self.logger.debug(f"EasyOCR dialogue fallback failed: {exc}")
            return []
        blocks = []
        for bbox, text, confidence in results:
            text = self._clean_text(str(text))
            if confidence < 0.35 or self._is_noise(text):
                continue
            pts = np.asarray(bbox, dtype=np.float32)
            x0, y0 = pts.min(axis=0)
            x1, y1 = pts.max(axis=0)
            blocks.append(
                TextBlock(
                    text=text,
                    raw_text=text,
                    bbox=[int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0))],
                    confidence=float(confidence) * 100.0,
                    engine="easyocr",
                )
            )
        return blocks

    def _get_easyocr_reader(self) -> Any:
        if not self.use_easyocr or not EASYOCR_AVAILABLE:
            return None
        lang_map = {"eng": "en", "jpn": "ja", "kor": "ko"}
        lang = lang_map.get(self.ocr_lang, "en")
        if lang not in self._easyocr_readers:
            self._easyocr_readers[lang] = easyocr.Reader([lang], gpu=False, verbose=False)
        return self._easyocr_readers[lang]

    def _dedupe_blocks(self, blocks: List[TextBlock]) -> List[TextBlock]:
        kept: List[TextBlock] = []
        for block in sorted(blocks, key=lambda item: (-item.confidence, item.bbox[1], item.bbox[0])):
            duplicate = False
            for existing in kept:
                if self._text_similarity(block.text, existing.text) > 0.86 and self._bbox_iou(block.bbox, existing.bbox) > 0.18:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(block)
        return sorted(kept, key=lambda item: (item.bbox[1], item.bbox[0]))

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        aa = set(re.findall(r"[a-z0-9]+", a.lower()))
        bb = set(re.findall(r"[a-z0-9]+", b.lower()))
        if not aa or not bb:
            return 0.0
        return len(aa & bb) / float(len(aa | bb))

    @staticmethod
    def _bbox_iou(a: Sequence[int], b: Sequence[int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix0, iy0 = max(ax, bx), max(ay, by)
        ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
        iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
        inter = iw * ih
        union = aw * ah + bw * bh - inter
        return inter / float(max(1, union))

    def _split_name_hint(self, block: TextBlock) -> None:
        match = re.match(r"^\s*([A-Z][A-Za-z0-9 ._'()-]{1,28})\s*[:\-]\s*(.{2,})$", block.text)
        if not match:
            return
        name, speech = match.groups()
        if len(name.split()) > 4:
            return
        block.name_hint = name.strip()
        block.text = self._clean_text(speech)

    def _classify_block(self, block: TextBlock, width: int, height: int) -> str:
        text = block.text.strip()
        if not text:
            return "unknown"
        alpha = re.sub(r"[^A-Za-z]", "", text)
        words = re.findall(r"[A-Za-z0-9]+", text)
        x, y, w, h = block.bbox
        near_edge = y < height * 0.12 or y + h > height * 0.88
        short_loud = len(words) <= 4 and text.upper() == text and len(alpha) >= 2
        if block.name_hint:
            return "dialogue"
        if short_loud and any(mark in text for mark in ("!", "-", ".")) or (short_loud and len(alpha) <= 10):
            return "sfx"
        if near_edge and len(words) >= 4 and block.box_style in {"dark_caption", "mixed"}:
            return "narration"
        return "dialogue"

    def _box_style(self, img: np.ndarray, bbox: Sequence[int], scene: Dict[str, Any]) -> str:
        height, width = img.shape[:2]
        x, y, w, h = _clip_bbox(bbox, width, height, pad=8)
        if w <= 0 or h <= 0:
            return "mixed"
        roi = img[y : y + h, x : x + w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        dark_ratio = float(np.mean(gray < 80))
        light_ratio = float(np.mean(gray > 210))
        if mean > 185 and light_ratio > 0.35:
            return "light_bubble"
        if scene.get("is_dark") and dark_ratio > 0.45:
            return "dark_caption"
        if dark_ratio > 0.35 and light_ratio > 0.2:
            return "high_contrast_bubble"
        return "mixed"

    def _detect_faces(self, img: np.ndarray) -> List[FaceCandidate]:
        if self.face_cascade is None:
            return []
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        min_side = max(24, min(w, h) // 16)
        try:
            detections = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=3,
                minSize=(min_side, min_side),
            )
        except Exception:
            return []
        faces: List[FaceCandidate] = []
        for x, y, fw, fh in detections:
            if fw * fh < (w * h) * 0.002:
                continue
            bbox = [int(x), int(y), int(fw), int(fh)]
            signature = self._face_signature(img, bbox)
            faces.append(FaceCandidate(bbox=bbox, confidence=0.55, signature=signature))
        faces.sort(key=lambda face: face.bbox[2] * face.bbox[3], reverse=True)
        return faces[:8]

    def _face_signature(self, img: np.ndarray, bbox: Sequence[int]) -> List[float]:
        height, width = img.shape[:2]
        x, y, w, h = _clip_bbox(bbox, width, height, pad=max(4, int(min(bbox[2], bbox[3]) * 0.15)))
        roi = img[y : y + h, x : x + w]
        if roi.size == 0:
            return []
        resized = cv2.resize(roi, (48, 48), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        hist_h = cv2.calcHist([hsv], [0], None, [12], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [8], [0, 256]).flatten()
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        hist_v = cv2.calcHist([gray], [0], None, [8], [0, 256]).flatten()
        features = np.concatenate([hist_h, hist_s, hist_v]).astype(np.float32)
        denom = float(np.linalg.norm(features))
        if denom > 1e-8:
            features /= denom
        return [float(v) for v in features]

    def _assign_speakers(self, analysis: PanelAnalysis, context: SeriesCharacterContext) -> None:
        for face in analysis.faces:
            matched_id, confidence = context.match_face(face.signature)
            if matched_id:
                face.profile_id = matched_id
                face.display_name = context.public_name(matched_id)
                face.confidence = max(face.confidence, confidence)

        for block in analysis.text_blocks:
            if block.block_type == "sfx":
                block.speaker = "SFX"
                block.speaker_reason = "sound_effect"
                block.speaker_confidence = 1.0
                continue
            if block.block_type == "narration":
                block.speaker = "Narrator"
                block.speaker_reason = "caption_or_edge_text"
                block.speaker_confidence = 0.82
                continue

            nearest = self._nearest_face(block, analysis.faces, analysis.size)
            if block.name_hint:
                if nearest:
                    profile_id, confidence, reason = context.match_or_create_face(
                        nearest.signature,
                        self.chapter_dir.name,
                        preferred_name=block.name_hint,
                    )
                    nearest.profile_id = profile_id
                    nearest.display_name = context.public_name(profile_id)
                else:
                    profile_id = context.profile_for_name(block.name_hint, self.chapter_dir.name)
                    confidence = 0.88
                    reason = "explicit_name_no_face"
                block.speaker_id = profile_id
                block.speaker = context.public_name(profile_id)
                block.speaker_confidence = confidence
                block.speaker_reason = reason
                continue

            if nearest:
                if nearest.profile_id:
                    profile_id = nearest.profile_id
                    confidence = 0.56
                    reason = "nearest_known_face"
                else:
                    profile_id, confidence, reason = context.match_or_create_face(
                        nearest.signature,
                        self.chapter_dir.name,
                    )
                    nearest.profile_id = profile_id
                    nearest.display_name = context.public_name(profile_id)
                block.speaker_id = profile_id
                block.speaker = context.public_name(profile_id)
                block.speaker_confidence = min(0.72, max(confidence, 0.42))
                block.speaker_reason = reason
                continue

            block.speaker = "Unknown"
            block.speaker_reason = "no_name_or_face_match"
            block.speaker_confidence = 0.0

    def _nearest_face(
        self,
        block: TextBlock,
        faces: Sequence[FaceCandidate],
        size: Tuple[int, int],
    ) -> Optional[FaceCandidate]:
        if not faces:
            return None
        width, height = size
        diag = math.hypot(width, height)
        bx, by = _bbox_center(block.bbox)
        best: Optional[FaceCandidate] = None
        best_score = 999.0
        for face in faces:
            fx, fy = _bbox_center(face.bbox)
            distance = math.hypot(bx - fx, by - fy)
            if fy > by:
                distance *= 1.12
            face_area = face.bbox[2] * face.bbox[3]
            size_bonus = min(0.18, face_area / float(max(1, width * height)) * 6.0)
            score = (distance / max(1.0, diag)) - size_bonus
            if score < best_score:
                best_score = score
                best = face
        if best is not None and best_score <= 0.42:
            return best
        return None

    def _panel_payload(self, analysis: PanelAnalysis) -> Dict[str, Any]:
        return {
            "panel": analysis.panel_name,
            "panel_path": analysis.panel_path,
            "size": {"width": int(analysis.size[0]), "height": int(analysis.size[1])},
            "scene": analysis.scene,
            "faces": [face.as_dict() for face in analysis.faces],
            "text_boxes": [
                block.as_dict(f"{Path(analysis.panel_name).stem}_b{idx:03d}")
                for idx, block in enumerate(analysis.text_blocks, start=1)
            ],
        }

    def _write_transcript(self, analysis: PanelAnalysis) -> Optional[Path]:
        if not analysis.text_blocks:
            return None
        lines = []
        for block in analysis.text_blocks:
            if block.speaker in {"Narrator", "SFX", "Unknown"}:
                prefix = block.speaker
            else:
                prefix = block.speaker
            lines.append(f"{prefix}: {block.text}")
        transcript_path = self.transcripts_dir / f"{Path(analysis.panel_name).stem}.txt"
        transcript_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return transcript_path

    @staticmethod
    def _load_face_cascade() -> Optional[Any]:
        try:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(str(cascade_path))
            if cascade.empty():
                return None
            return cascade
        except Exception:
            return None

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.replace("|", "I")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"([!?.,])\1{3,}", r"\1\1\1", text)
        return text.strip(" \t\r\n\"'`")

    @staticmethod
    def _is_noise(text: str) -> bool:
        if not text:
            return True
        alnum = re.sub(r"[^A-Za-z0-9]", "", text)
        if len(alnum) <= 1:
            return True
        if len(text) <= 3 and not re.search(r"[A-Za-z]{2}", text):
            return True
        if len(alnum) / max(1, len(text)) < 0.25 and len(text) < 10:
            return True
        junk = sum(1 for char in text if char in "_~=+{}[]<>")
        return junk / max(1, len(text)) > 0.35
