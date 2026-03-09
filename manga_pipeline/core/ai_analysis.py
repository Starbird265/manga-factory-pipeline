import os
import google.generativeai as genai
from PIL import Image
from typing import Optional, Dict, Any, List
import logging
import json
import base64
from io import BytesIO
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

class AIAnalysis:
    """
    AI-driven context analysis for manga panels.
    Supports Google Gemini (Cloud) and Ollama (Local).
    """
    def __init__(self, api_key: Optional[str] = None, model_name: str = None, provider: str = "auto"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.provider = provider
        self.model_name = model_name
        
        # Auto-detection logic
        if self.provider == "auto":
            if self.api_key:
                self.provider = "gemini"
            else:
                self.provider = "ollama"
        
        # Default models
        if not self.model_name:
            if self.provider == "gemini":
                self.model_name = "gemini-1.5-flash"
            else:
                # Default to the requested large model, or fallback to a smaller one
                self.model_name = "gpt-oss:120b" 

        if self.provider == "gemini":
            if self.api_key:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                logger.info(f"AI Provider: Gemini ({self.model_name})")
            else:
                self.model = None
                logger.warning("GEMINI_API_KEY not found. Fallback to Ollama if possible or disable.")
        else:
            # Ollama setup (no object needed, we use HTTP)
            self.ollama_url = "http://localhost:11434/api/generate" # or /api/chat
            logger.info(f"AI Provider: Ollama ({self.model_name})")

    def _call_ollama(self, prompt: str, image: Optional[Image.Image] = None, json_mode: bool = False) -> str:
        """Helper to call Ollama API"""
        try:
            url = "http://localhost:11434/api/generate"
            
            data = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            }
            
            if json_mode:
                data["format"] = "json"

            if image:
                # Convert PIL image to base64
                buffered = BytesIO()
                image.save(buffered, format="PNG") # specific format
                img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
                data["images"] = [img_str]

            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=json_data, headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("response", "")
                
        except Exception as e:
            logger.error(f"Ollama API call failed: {e}")
            return ""

    def analyze_panel(self, image_path: str) -> Dict[str, Any]:
        """Describe characters, actions, and emotions in a panel."""
        
        prompt = """
        Analyze this manga panel and provide a JSON response with:
        {
            "characters": ["list of character descriptions"],
            "actions": ["list of actions happening"],
            "emotions": ["list of emotions expressed"],
            "text": "transcribed text (if any)",
            "style": "visual style description"
        }
        Respond ONLY with valid JSON.
        """

        try:
            img = Image.open(image_path)
            
            if self.provider == "gemini" and self.model:
                response = self.model.generate_content([prompt, img])
                text = response.text
            elif self.provider == "ollama":
                # Note: This requires a VLM for image analysis. 
                # If gpt-oss:120b is text-only, this part will fail to see the image but usually accepts the request.
                text = self._call_ollama(prompt, image=img, json_mode=True)
            else:
                return {}

            # Clean JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            return json.loads(text) if text else {}
        except Exception as e:
            logger.error(f"Panel analysis failed: {e}")
            return {}

    def get_contextual_translation(self, text: str, panel_context: Dict[str, Any]) -> str:
        """Translate text using visual context for better accuracy."""
        
        prompt = f"""
        Translate this manga dialogue from its source language to English.
        Context: {json.dumps(panel_context)}
        Dialogue: "{text}"
        Provide ONLY the English translation.
        """

        try:
            if self.provider == "gemini" and self.model:
                response = self.model.generate_content(prompt)
                return response.text.strip()
            elif self.provider == "ollama":
                return self._call_ollama(prompt).strip()
            else:
                return text
        except Exception as e:
            logger.error(f"Contextual translation failed: {e}")
            return text

    def detect_and_track_characters(self, image_paths: List[str]) -> Dict[str, Any]:
        """Identify and track characters across multiple panels."""
        return {"status": "experimental", "message": "Character tracking requires additional training."}
