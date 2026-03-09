import requests
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DashboardClient:
    """
    Client for sending updates to the live dashboard FastAPI server.
    """
    def __init__(self, url: str = "http://localhost:8000/update"):
        self.url = url
        self.active = True

    def send_update(self, data: Dict[str, Any]):
        """Send a JSON payload to the dashboard server."""
        if not self.active:
            return
            
        try:
            requests.post(self.url, json=data, timeout=0.5)
        except Exception:
            # Silently fail if dashboard is not running
            pass

    def update_progress(self, manga: str, chapter: str, progress: float):
        self.send_update({
            "manga": manga,
            "chapter": chapter,
            "progress": round(progress, 1)
        })

    def send_log(self, message: str, level: str = "info"):
        self.send_update({
            "log": message,
            "type": level
        })

    def update_stats(self, images: int, panels: int):
        self.send_update({
            "images": images,
            "panels": panels
        })

    def send_preview(self, base64_image: str):
        """Send a base64 encoded image for live preview."""
        self.send_update({
            "preview": f"data:image/png;base64,{base64_image}"
        })
