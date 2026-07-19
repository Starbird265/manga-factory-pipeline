#!/usr/bin/env python3

"""
AI-Enhanced Script Generation Module for Manga Factory
Uses Google's Gemini API for advanced script generation with context awareness,
emotion analysis, character consistency, and narrative flow optimization.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import time
import re
from datetime import datetime
import hashlib


try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

import urllib.request
import urllib.error

class AIScriptGenerator:
    """AI-powered script generator using Gemini API or local Ollama"""
    
    def __init__(self, api_key: Optional[str] = None, model_name: str = None, 
                 logger: Optional[logging.Logger] = None, provider: str = "auto"):
        """
        Initialize AI Script Generator
        
        Args:
            api_key: Gemini API key
            model_name: Model name (gpt-oss:120b or gemini-1.5-flash)
            logger: Logger instance
            provider: 'auto', 'gemini', or 'ollama'
        """
        self.logger = logger or self._setup_logger()
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.provider = provider
        
        # Auto-detect provider
        if self.provider == "auto":
            if self.api_key and GEMINI_AVAILABLE:
                self.provider = "gemini"
            else:
                self.provider = "ollama"

        # Set default model based on provider
        if not model_name:
            if self.provider == "gemini":
                self.model_name = "gemini-1.5-flash"
            else:
                self.model_name = "gpt-oss:120b"
        else:
            self.model_name = model_name

        self.model = None
        self.ollama_available = False
        
        # Performance settings (Gemini specific)
        self.generation_config = {
            'temperature': 0.7,
            'top_p': 0.8,
            'top_k': 40,
            'max_output_tokens': 4096,
        }
        
        # Strict context window management
        self.target_context_tokens = 30000 
        self.min_context_tokens = 10000   
        self.max_context_tokens = 40000 
        self.reserved_tokens = 4096       
        self.base_prompt_tokens = 5000     
        self.available_tokens = self.target_context_tokens - self.reserved_tokens - self.base_prompt_tokens
        
        # Safety settings (Gemini specific)
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
        
        # Initialize API
        self._initialize_api()
        
        # Memory system
        self.memory_dir = Path.home() / '.manga_factory_memory'
        self.memory_dir.mkdir(exist_ok=True)
        self.series_memory = {}
        
        # Per-chapter memory files
        self.chapter_memory_dir = self.memory_dir / 'chapters'
        self.chapter_memory_dir.mkdir(exist_ok=True)
        
    def _setup_logger(self) -> logging.Logger:
        """Setup basic logger"""
        logger = logging.getLogger('ai_script_generator')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
        
    def _initialize_api(self):
        """Initialize AI Provider"""
        if self.provider == "gemini":
            if not GEMINI_AVAILABLE:
                self.logger.warning("Gemini API not available (module missing). Switching to Ollama if possible.")
                self.provider = "ollama" # Fallback
                self.model_name = "gpt-oss:120b"
                return

            if not self.api_key:
                self.logger.warning("No Gemini API key found. Switching to Ollama.")
                self.provider = "ollama"
                self.model_name = "gpt-oss:120b"
                return
                
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(
                    model_name=self.model_name,
                    generation_config=self.generation_config,
                    safety_settings=self.safety_settings
                )
                self.logger.info(f"✅ Gemini API initialized with model: {self.model_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize Gemini API: {e}")
                self.model = None
        else:
            # Ollama initialization
            self.logger.info(f"✅ Ollama Provider initialized with model: {self.model_name}")
            try:
                urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
                self.ollama_available = True
            except Exception as e:
                self.logger.warning(f"Ollama server might not be running: {e}")

    def is_available(self) -> bool:
        """Check if AI script generation is available"""
        if self.provider == "gemini":
            return self.model is not None
        return self.ollama_available
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text (rough approximation)"""
        # More accurate estimation: ~3.5 chars per token for most content
        return max(1, len(text) // 3)
    
    def _create_chapter_memory_file(self, series_id: str, chapter_title: str, chapter_data: Dict):
        """Create a new memory file for each chapter"""
        try:
            chapter_num = chapter_data.get('id', len(os.listdir(self.chapter_memory_dir)) + 1)
            filename = f"{series_id}_ch{chapter_num:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = self.chapter_memory_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chapter_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Created chapter memory file: {filename}")
            return str(filepath)
            
        except Exception as e:
            self.logger.warning(f"Failed to create chapter memory file: {e}")
            return None
    
    def _get_recent_chapters_within_token_limit(self, series_id: str, target_tokens: int = 15000) -> Dict:
        """Get recent chapters that fit within token limit"""
        try:
            memory = self._load_series_memory(series_id)
            if not memory.get('chapters'):
                return {}
            
            # Start with most recent chapters and work backwards
            recent_chapters = memory['chapters'][-10:]  # Start with last 10
            selected_chapters = []
            current_tokens = 0
            
            for chapter in reversed(recent_chapters):
                chapter_text = json.dumps(chapter, separators=(',', ':'))
                chapter_tokens = self._estimate_tokens(chapter_text)
                
                if current_tokens + chapter_tokens <= target_tokens:
                    selected_chapters.insert(0, chapter)  # Insert at beginning to maintain order
                    current_tokens += chapter_tokens
                else:
                    break
            
            self.logger.info(f"Selected {len(selected_chapters)} recent chapters, ~{current_tokens} tokens")
            
            return {
                'chapters': selected_chapters,
                'characters': memory.get('characters', {}),
                'estimated_tokens': current_tokens
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to get recent chapters: {e}")
            return {}
    
    def _get_series_id(self, series_context: str, chapter_title: str = "") -> str:
        """Generate a unique series ID for memory storage"""
        if not series_context:
            return "unknown_series"
        
        # Create a hash of the series context for consistent ID
        series_text = series_context.lower().strip()
        series_hash = hashlib.md5(series_text.encode()).hexdigest()[:8]
        
        # Clean series context for readable filename
        series_clean = re.sub(r'[^\w\s-]', '', series_text)
        series_clean = re.sub(r'\s+', '_', series_clean)[:30]
        
        return f"{series_clean}_{series_hash}"
    
    def _load_series_memory(self, series_id: str) -> Dict:
        """Load existing memory for a manga series"""
        memory_file = self.memory_dir / f"{series_id}_memory.json"
        
        if memory_file.exists():
            try:
                with open(memory_file, 'r', encoding='utf-8') as f:
                    memory = json.load(f)
                    self.logger.info(f"Loaded series memory: {len(memory.get('characters', {}))} characters, {len(memory.get('chapters', []))} chapters")
                    return memory
            except Exception as e:
                self.logger.warning(f"Failed to load series memory: {e}")
        
        # Initialize new memory structure
        return {
            'series_id': series_id,
            'characters': {},  # character_name: {traits, relationships, first_seen}
            'locations': {},   # location_name: {description, first_seen}
            'plot_points': [], # major events and story developments
            'chapters': [],    # processed chapters with summaries
            'terminology': {}, # special terms, abilities, concepts
            'relationships': {},  # character relationships
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
    
    def _save_series_memory(self, series_id: str, memory: Dict):
        """Save updated memory for a manga series"""
        try:
            memory['last_updated'] = datetime.now().isoformat()
            memory_file = self.memory_dir / f"{series_id}_memory.json"
            
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, indent=2, ensure_ascii=False)
                
            self.logger.info(f"Saved series memory to {memory_file}")
            
        except Exception as e:
            self.logger.warning(f"Failed to save series memory: {e}")
    
    def _extract_story_elements(self, panel_data: List[Dict], enhanced_script: str) -> Dict:
        """Extract characters, locations, and plot elements from the script"""
        story_elements = {
            'characters': set(),
            'locations': set(),
            'plot_points': [],
            'terminology': set()
        }
        
        # Simple extraction patterns (can be enhanced)
        text_content = ' '.join([panel['raw_text'] for panel in panel_data if panel.get('raw_text')])
        enhanced_content = enhanced_script
        
        # Extract potential character names (capitalized words that appear multiple times)
        words = re.findall(r'\b[A-Z][a-z]+\b', text_content + ' ' + enhanced_content)
        word_counts = {}
        for word in words:
            if len(word) > 2 and word not in ['Panel', 'Chapter', 'The', 'And', 'But', 'This', 'That']:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        # Characters are names that appear multiple times
        for word, count in word_counts.items():
            if count >= 2:
                story_elements['characters'].add(word)
        
        # Extract dialogue for plot points
        dialogue_lines = re.findall(r'\[.*?\]\s*(.+)', enhanced_content)
        if len(dialogue_lines) > 0:
            story_elements['plot_points'] = dialogue_lines[:3]  # Key dialogue lines
        
        return story_elements
    
    def _create_chapter_summary(self, panel_data: List[Dict], enhanced_script: str) -> Dict:
        """Create a compact JSON summary of the chapter"""
        # Extract key dialogue and actions from enhanced script
        dialogue_lines = re.findall(r'\[.*?\]\s*(.+)', enhanced_script)
        
        # Get most important dialogue (first and last few lines)
        key_dialogue = []
        if dialogue_lines:
            # First 2 and last 2 dialogue lines
            key_dialogue.extend(dialogue_lines[:2])
            if len(dialogue_lines) > 4:
                key_dialogue.extend(dialogue_lines[-2:])
        
        # Extract character interactions
        character_interactions = []
        current_speakers = []
        
        for line in dialogue_lines[:10]:  # Analyze first 10 lines for interactions
            # Simple heuristic: if line contains pronouns or names, it's interaction
            if any(word in line.lower() for word in ['you', 'your', 'me', 'my', 'us', 'we']):
                character_interactions.append(line[:100])  # Truncate to save space
        
        return {
            'panels_count': len(panel_data),
            'key_dialogue': key_dialogue[:4],  # Max 4 key lines
            'character_interactions': character_interactions[:3],  # Max 3 interactions
            'text_length': len(enhanced_script),
            'has_action': any(word in enhanced_script.lower() for word in ['fight', 'run', 'attack', 'move', 'go']),
            'has_emotion': '[' in enhanced_script,  # Has emotion tags
            'dialogue_count': len(dialogue_lines)
        }
    
    def _update_series_memory(self, series_id: str, chapter_title: str, 
                            story_elements: Dict, panel_data: List[Dict], enhanced_script: str = ""):
        """Update series memory with smart JSON summarization"""
        memory = self._load_series_memory(series_id)
        
        # Update characters with smart tracking
        for character in story_elements['characters']:
            if character not in memory['characters']:
                memory['characters'][character] = {
                    'first_chapter': len(memory['chapters']) + 1,
                    'appearances': 1,
                    'last_seen': len(memory['chapters']) + 1,
                    'key_traits': []  # Will be filled by AI analysis
                }
            else:
                memory['characters'][character]['appearances'] += 1
                memory['characters'][character]['last_seen'] = len(memory['chapters']) + 1
        
        # Create compact chapter summary
        chapter_summary = {
            'id': len(memory['chapters']) + 1,
            'title': chapter_title or f"Chapter {len(memory['chapters']) + 1}",
            'summary': self._create_chapter_summary(panel_data, enhanced_script),
            'characters': list(story_elements['characters']),
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        memory['chapters'].append(chapter_summary)
        
        # Intelligent memory management - keep recent + important chapters
        if len(memory['chapters']) > 30:
            # Keep last 20 chapters + 10 most important older chapters
            recent_chapters = memory['chapters'][-20:]
            older_chapters = memory['chapters'][:-20]
            
            # Score older chapters by importance (character introductions, dialogue volume, etc.)
            scored_chapters = []
            for ch in older_chapters:
                score = 0
                score += len(ch.get('characters', [])) * 2  # Character introductions
                score += ch['summary'].get('dialogue_count', 0) * 0.1  # Dialogue volume
                score += 5 if ch['summary'].get('has_action', False) else 0  # Action scenes
                scored_chapters.append((score, ch))
            
            # Keep top 10 important older chapters
            scored_chapters.sort(key=lambda x: x[0], reverse=True)
            important_older = [ch for _, ch in scored_chapters[:10]]
            
            memory['chapters'] = important_older + recent_chapters
        
        self._save_series_memory(series_id, memory)
        return memory
    
    def _create_smart_context_summary(self, series_memory: Dict, max_tokens: int = 8000) -> str:
        """Create a token-limited JSON summary of series history for AI context"""
        if not series_memory or not series_memory.get('chapters'):
            return ""
        
        # Create ultra-compact series summary with token awareness
        context_summary = {
            'total_chapters': len(series_memory['chapters']),
            'main_characters': {},
            'recent_events': [],
            'series_progression': []
        }
        
        # Main characters (top 6 by appearances for token efficiency)
        characters = series_memory.get('characters', {})
        sorted_chars = sorted(characters.items(), key=lambda x: x[1].get('appearances', 0), reverse=True)
        for name, info in sorted_chars[:6]:  # Reduced to 6 for token efficiency
            context_summary['main_characters'][name] = {
                'app': info.get('appearances', 0),  # Shortened keys
                'first': info.get('first_chapter', 1),
                'last': info.get('last_seen', 1)
            }
        
        # Recent events from last 3 chapters (token optimized)
        recent_chapters = series_memory['chapters'][-3:]
        for ch in recent_chapters:
            if ch['summary'].get('key_dialogue'):
                context_summary['recent_events'].append({
                    'ch': ch['id'],
                    'key': ch['summary']['key_dialogue'][0][:30] + "..." if ch['summary']['key_dialogue'] else ""  # Shortened
                })
        
        # Series progression markers (every 10th chapter for efficiency)
        all_chapters = series_memory['chapters']
        for i in range(0, len(all_chapters), max(10, len(all_chapters)//5)):  # Adaptive sampling
            ch = all_chapters[i]
            context_summary['series_progression'].append({
                'ch': ch['id'],
                'c': len(ch.get('characters', [])),  # Shortened key
                'act': ch['summary'].get('has_action', False)  # Shortened key
            })
        
        # Convert to compact JSON string
        json_summary = json.dumps(context_summary, separators=(',', ':'))  # No spaces for compactness
        
        # Log size for context window management
        char_count = len(json_summary)
        estimated_tokens = char_count // 4  # Rough estimate: 4 chars per token
        self.logger.debug(f"Series summary: {char_count} chars, ~{estimated_tokens} tokens")
        
        return json_summary
    
    def generate_enhanced_script(self, transcript_files: List[Path], 
                               chapter_title: str = "", 
                               series_context: str = "",
                               character_info: Dict[str, str] = None,
                               style_preferences: Dict[str, any] = None) -> Tuple[str, Dict[str, any]]:
        """
        Generate an enhanced script using AI analysis
        
        Args:
            transcript_files: List of OCR transcript files
            chapter_title: Title of the chapter
            series_context: Background context about the series
            character_info: Dictionary of character names and descriptions
            style_preferences: Style preferences for script generation
            
        Returns:
            Tuple of (enhanced_script, metadata)
        """
        if not self.is_available():
            self.logger.warning("AI script generation not available - using fallback")
            return self._fallback_script_generation(transcript_files)
        
        try:
            self.logger.info("Starting AI-enhanced script generation with series memory")
            start_time = time.time()
            
            # Load and process transcript data
            panel_data = self._load_panel_transcripts(transcript_files)
            if not panel_data:
                return self._fallback_script_generation(transcript_files)
            
            # Load series memory with strict token limits
            series_id = self._get_series_id(series_context, chapter_title)
            if series_context:
                # Get recent chapters within token budget (15k tokens max for memory)
                series_memory = self._get_recent_chapters_within_token_limit(series_id, 15000)
                self.logger.info(f"Loaded series memory: ~{series_memory.get('estimated_tokens', 0)} tokens")
            else:
                series_memory = {}
            
            # Prepare context for AI with memory
            context = self._prepare_context(
                panel_data, chapter_title, series_context, 
                character_info or {}, style_preferences or {}, series_memory
            )
            
            # Generate enhanced script
            enhanced_script = self._generate_with_ai(context, panel_data)
            
            # Extract story elements from the enhanced script
            story_elements = self._extract_story_elements(panel_data, enhanced_script)
            
            # Update series memory with new information and create per-chapter file
            if series_context:
                updated_memory = self._update_series_memory(series_id, chapter_title, story_elements, panel_data, enhanced_script)
                
                # Create individual chapter memory file
                latest_chapter = updated_memory['chapters'][-1] if updated_memory['chapters'] else {}
                chapter_file = self._create_chapter_memory_file(series_id, chapter_title, {
                    'series_id': series_id,
                    'chapter': latest_chapter,
                    'characters_in_chapter': list(story_elements['characters']),
                    'enhanced_script_preview': enhanced_script[:500] + '...' if len(enhanced_script) > 500 else enhanced_script,
                    'processing_metadata': {
                        'timestamp': datetime.now().isoformat(),
                        'panel_count': len(panel_data),
                        'script_length': len(enhanced_script)
                    }
                })
                
                self.logger.info(f"Updated series memory: {len(updated_memory['characters'])} characters tracked")
                self.logger.info(f"Created chapter file: {chapter_file}")
            
            # Post-process and format
            final_script = self._format_final_script(enhanced_script, panel_data, series_memory)
            
            # Generate metadata
            metadata = {
                'generation_time': time.time() - start_time,
                'model_used': self.model_name,
                'panel_count': len(panel_data),
                'ai_enhanced': True,
                'timestamp': datetime.now().isoformat(),
                'features': ['emotion_analysis', 'narrative_flow', 'character_consistency', 'series_memory'],
                'series_continuity': {
                    'series_id': series_id if series_context else None,
                    'characters_tracked': len(series_memory.get('characters', {})) if series_memory else 0,
                    'chapters_processed': len(series_memory.get('chapters', [])) if series_memory else 0,
                    'memory_enabled': bool(series_context and series_memory)
                }
            }
            
            self.logger.info(f"AI script generation completed in {metadata['generation_time']:.2f}s")
            return final_script, metadata
            
        except Exception as e:
            self.logger.error(f"AI script generation failed: {e}")
            return self._fallback_script_generation(transcript_files)
    
    def _load_panel_transcripts(self, transcript_files: List[Path]) -> List[Dict]:
        """Load and organize panel transcript data"""
        panel_data = []
        
        def natural_sort_key(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'([0-9]+)', str(text))]
        
        # Sort files naturally
        transcript_files.sort(key=lambda x: natural_sort_key(x.name))
        
        for idx, file_path in enumerate(transcript_files):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                panel_data.append({
                    'panel_id': file_path.stem,
                    'panel_number': idx + 1,
                    'raw_text': content,
                    'file_path': str(file_path),
                    'has_text': bool(content)
                })
                
            except Exception as e:
                self.logger.warning(f"Could not read {file_path}: {e}")
                # Add placeholder for missing/broken files
                panel_data.append({
                    'panel_id': file_path.stem,
                    'panel_number': idx + 1,
                    'raw_text': f"[Error reading panel: {e}]",
                    'file_path': str(file_path),
                    'has_text': False
                })
        
        self.logger.info(f"Loaded {len(panel_data)} panels for AI processing")
        return panel_data
    
    def _prepare_context(self, panel_data: List[Dict], chapter_title: str, 
                        series_context: str, character_info: Dict[str, str], 
                        style_preferences: Dict[str, any], series_memory: Dict = None) -> str:
        """Prepare advanced context prompt with few-shot learning, structured reasoning, and series memory"""
        
        context_parts = [
            "# MANGA OCR ENHANCEMENT SPECIALIST",
            "You are a world-class manga/webtoon script editor specializing in OCR text enhancement and dialogue improvement.",
            "",
            "## 🎯 PRIMARY OBJECTIVE",
            "Transform raw OCR-extracted manga text into clean, readable scripts while preserving 100% of the original content and meaning.",
            "",
            "## 📋 CORE RESPONSIBILITIES",
            "1. **OCR Error Correction**: Fix technical OCR mistakes (character recognition errors)",
            "2. **Dialogue Enhancement**: Add emotion tags and improve readability",
            "3. **Format Standardization**: Clean up spacing, punctuation, and structure",
            "4. **Content Preservation**: Maintain all original story elements exactly as intended",
            "",
            "## ⚠️ CRITICAL CONSTRAINTS",
            "- **NEVER** alter story content, character names, or plot points",
            "- **ONLY** fix obvious OCR errors (l→I, 0→O, rn→m, cl→d, etc.)",
            "- **PRESERVE** all original dialogue meaning and intent",
            "- **MAINTAIN** exact panel structure and dialogue sequence",
            "- **ADD** emotion tags based on dialogue context, not assumptions",
            "",
            "## 🎭 EMOTION TAG GUIDELINES",
            "Use these tags based on dialogue analysis:",
            "- [excited] - Enthusiasm, joy, high energy",
            "- [angry] - Frustration, rage, confrontation",
            "- [sad] - Sorrow, disappointment, melancholy",
            "- [surprised] - Shock, amazement, unexpected reactions",
            "- [confused] - Questions, uncertainty, bewilderment",
            "- [determined] - Resolve, focus, strong intention",
            "- [worried] - Concern, anxiety, fear",
            "- [calm] - Peace, serenity, composed speech",
            "- [shouting] - Loud, urgent, demanding attention",
            "- [whispering] - Quiet, secretive, intimate",
            "",
            "## 📚 FEW-SHOT LEARNING EXAMPLES",
            "",
            "### Example 1: OCR Error Correction",
            "**RAW OCR:** `HeIIo! l'm so gIad to see you agaln!`",
            "**ENHANCED:** `[excited] Hello! I'm so glad to see you again!`",
            "*Analysis: Fixed l→I, II→ll, corrected spacing, added emotion tag based on enthusiasm*",
            "",
            "### Example 2: Punctuation & Emotion",
            "**RAW OCR:** `what are you doing here why did you come`",
            "**ENHANCED:** `[confused] What are you doing here? Why did you come?`",
            "*Analysis: Added punctuation, capitalized, emotion tag based on questioning tone*",
            "",
            "### Example 3: Character Name Preservation",
            "**RAW OCR:** `Narut0, you'rn the best!`",
            "**ENHANCED:** `[excited] Naruto, you're the best!`",
            "*Analysis: Fixed 0→o in name, rn→re in contraction, maintained character identity*",
            "",
            "### Example 4: Preserve Unclear Text",
            "**RAW OCR:** `I... I don't kn0w ab0ut th@t...`",
            "**ENHANCED:** `[uncertain] I... I don't know about that...`",
            "*Analysis: Fixed obvious errors (0→o, @→a), kept hesitation markers, added emotion*",
            "",
            "## 🧠 THINKING PROCESS",
            "For each panel, follow this reasoning chain:",
            "1. **Analyze**: What OCR errors are obvious? (character substitutions, spacing issues)",
            "2. **Preserve**: What content must remain exactly as intended? (names, story elements)",
            "3. **Enhance**: What emotion does this dialogue convey? (tone, context, punctuation)",
            "4. **Format**: How can readability be improved without changing meaning?",
            "5. **Verify**: Does the enhanced version maintain the original intent?",
            ""
        ]
        
        # Add series context if provided
        if series_context:
            context_parts.extend([
                "## 📚 SERIES CONTEXT:",
                series_context,
                ""
            ])
        
        # Add series memory with smart JSON summarization
        if series_memory and series_memory.get('chapters'):
            # Create compact JSON summary of entire series
            smart_summary = self._create_smart_context_summary(series_memory)
            
            context_parts.extend([
                "## 🧠 SERIES MEMORY & CONTINUITY (JSON Format)",
                "*Analyze this complete series history for perfect continuity*",
                "",
                "### 📊 SERIES ANALYSIS (Compact JSON):",
                "```json",
                smart_summary,
                "```",
                "",
                "### 📝 KEY INSTRUCTIONS FOR SERIES CONTINUITY:",
                "1. **Character Consistency**: Use exact names from main_characters list",
                "2. **Story Progression**: Consider recent_events for plot continuity",
                "3. **Character Development**: Respect appearance history and relationships",
                "4. **Dialogue Style**: Maintain established character speech patterns",
                "5. **Plot Coherence**: Ensure current chapter fits series progression",
                "",
                "**CRITICAL**: This chapter follows the established story. Maintain all character names, relationships, and plot elements exactly as shown in the JSON summary.",
                ""
            ])
        
        # Add character information if provided
        if character_info:
            context_parts.extend([
                "## Character Information:",
            ])
            for name, description in character_info.items():
                context_parts.append(f"- {name}: {description}")
            context_parts.append("")
        
        # Add chapter title if provided
        if chapter_title:
            context_parts.extend([
                f"## Chapter: {chapter_title}",
                ""
            ])
        
        # Add style preferences
        style_prefs = style_preferences or {}
        if style_prefs:
            context_parts.extend([
                "## Style Preferences:",
            ])
            if style_prefs.get('emotion_detail', 'medium') == 'high':
                context_parts.append("- Use detailed emotion tags and descriptions")
            elif style_prefs.get('emotion_detail', 'medium') == 'low':
                context_parts.append("- Use minimal emotion tags")
            else:
                context_parts.append("- Use moderate emotion tags")
                
            if style_prefs.get('scene_descriptions', True):
                context_parts.append("- Include scene descriptions where appropriate")
            else:
                context_parts.append("- Minimal scene descriptions")
                
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def _call_ollama(self, prompt: str) -> str:
        """Helper to call Ollama API"""
        try:
            url = "http://localhost:11434/api/generate"
            
            data = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            }
            
            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=json_data, headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("response", "")
                
        except Exception as e:
            self.logger.error(f"Ollama API call failed: {e}")
            raise

    def _generate_with_ai(self, context: str, panel_data: List[Dict]) -> str:
        """Generate enhanced script using AI"""
        
        # Prepare the full prompt
        prompt_parts = [
            context,
            "## Raw OCR Data to Enhance:",
            ""
        ]
        
        # Add panel data
        for panel in panel_data:
            if panel['has_text'] and panel['raw_text']:
                prompt_parts.extend([
                    f"[Panel {panel['panel_number']}]",
                    panel['raw_text'],
                    ""
                ])
        
        prompt_parts.extend([
            "",
            "## Instructions:",
            "Please clean up and enhance this OCR-extracted manga script by:",
            "1. Fixing obvious OCR errors and typos (e.g., 'l' -> 'I', '0' -> 'O', 'rn' -> 'm')",
            "2. Correcting punctuation and capitalization",
            "3. Adding emotion tags [like this] based on dialogue tone",
            "4. Improving formatting while preserving all original content",
            "5. Keeping all character names, dialogue, and story elements exactly as extracted",
            "6. Maintaining the original [Panel X] structure",
            "",
            "IMPORTANT: Do not change the story, characters, or dialogue content. Only clean up OCR errors and add emotion tags.",
            "Provide the cleaned script with proper formatting, keeping the [Panel X] markers."
        ])
        
        full_prompt = "\n".join(prompt_parts)
        
        try:
            # Generate with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if self.provider == "gemini":
                        response = self.model.generate_content(full_prompt)
                        if response.text:
                            return response.text.strip()
                        else:
                            self.logger.warning(f"Empty response from Gemini API (attempt {attempt + 1})")
                    else:
                        # Ollama provider
                        response_text = self._call_ollama(full_prompt)
                        if response_text:
                            return response_text.strip()
                        else:
                            self.logger.warning(f"Empty response from Ollama API (attempt {attempt + 1})")
                        
                except Exception as e:
                    self.logger.warning(f"API call failed (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                    
            raise Exception("All API attempts failed")
            
        except Exception as e:
            self.logger.error(f"AI generation failed: {e}")
            raise
    
    def _format_final_script(self, ai_enhanced_script: str, panel_data: List[Dict], 
                            series_memory: Dict = None) -> str:
        """Format the final script with metadata, structure, and series memory info"""
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        header = [
            "# MANGA FACTORY - AI ENHANCED SCRIPT WITH SERIES MEMORY",
            "# " + "="*60,
            f"# Generated: {timestamp}",
            f"# AI Model: {self.model_name}",
            f"# Panels Processed: {len(panel_data)}",
            f"# Enhancement Features: OCR correction, emotion analysis, series continuity",
        ]
        
        # Add series memory info to header
        if series_memory:
            char_count = len(series_memory.get('characters', {}))
            chapter_count = len(series_memory.get('chapters', []))
            header.extend([
                f"# Series Continuity: {char_count} characters tracked, {chapter_count} chapters processed",
                f"# Memory System: Active for consistent character and plot tracking"
            ])
        else:
            header.append("# Series Continuity: Standalone chapter (no series memory)")
        
        header.extend([
            "# " + "="*60,
            "",
        ])
        
        # Clean and structure the AI output
        script_lines = ai_enhanced_script.split('\n')
        cleaned_lines = []
        
        for line in script_lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1]:  # Preserve single empty lines
                cleaned_lines.append("")
        
        final_script = "\n".join(header + cleaned_lines)
        return final_script
    
    def _fallback_script_generation(self, transcript_files: List[Path]) -> Tuple[str, Dict[str, any]]:
        """Fallback script generation when AI is not available"""
        self.logger.info("Using fallback script generation (no AI enhancement)")
        
        def natural_sort_key(text):
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'([0-9]+)', str(text))]
        
        transcript_files.sort(key=lambda x: natural_sort_key(x.name))
        
        script_lines = [
            "# MANGA FACTORY - BASIC SCRIPT",
            "# " + "="*50,
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Panels: {len(transcript_files)}",
            f"# Mode: Fallback (AI unavailable)",
            "# " + "="*50,
            "",
        ]
        
        processed_count = 0
        for transcript_file in transcript_files:
            try:
                with open(transcript_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                
                if content:
                    script_lines.append(f"[Panel {transcript_file.stem}]")
                    script_lines.append(content)
                    script_lines.append("")
                    processed_count += 1
                    
            except Exception as e:
                self.logger.warning(f"Could not read {transcript_file}: {e}")
                script_lines.append(f"[Panel {transcript_file.stem} - Error]")
                script_lines.append(f"Error: {str(e)}")
                script_lines.append("")
        
        metadata = {
            'generation_time': 0.1,
            'model_used': 'fallback',
            'panel_count': processed_count,
            'ai_enhanced': False,
            'timestamp': datetime.now().isoformat(),
            'features': ['basic_formatting']
        }
        
        return "\n".join(script_lines), metadata


def view_series_memory(series_context: str = None, series_id: str = None):
    """View the memory for a specific manga series"""
    generator = AIScriptGenerator()
    
    if not series_id and not series_context:
        print("❌ Please provide either series_context or series_id")
        return
    
    if not series_id:
        series_id = generator._get_series_id(series_context)
    
    memory = generator._load_series_memory(series_id)
    
    print(f"📚 Series Memory for: {series_id}")
    print("=" * 50)
    
    if memory.get('characters'):
        print(f"👥 Characters ({len(memory['characters'])}):")  
        for char_name, char_info in memory['characters'].items():
            appearances = char_info.get('appearances', 1)
            first_seen = char_info.get('first_seen', 'Unknown')
            print(f"  - {char_name}: {appearances} appearances, first seen in {first_seen}")
        print()
    
    if memory.get('chapters'):
        print(f"📖 Processed Chapters ({len(memory['chapters'])}):")  
        for chapter in memory['chapters'][-5:]:  # Show last 5
            title = chapter.get('title', 'Unknown')
            panels = chapter.get('panels', 0)
            date = chapter.get('processed_date', 'Unknown')[:10]
            print(f"  - {title}: {panels} panels, processed on {date}")
        print()
    
    if memory.get('created_at'):
        created = memory['created_at'][:10]
        updated = memory.get('last_updated', 'Unknown')[:10]
        print(f"📅 Memory created: {created}, last updated: {updated}")

def list_all_series_memories():
    """List all stored series memories"""
    generator = AIScriptGenerator()
    
    memory_files = list(generator.memory_dir.glob("*_memory.json"))
    
    if not memory_files:
        print("📁 No series memories found")
        return
    
    print(f"📚 Found {len(memory_files)} series memories:")
    print("=" * 50)
    
    for memory_file in memory_files:
        try:
            with open(memory_file, 'r') as f:
                memory = json.load(f)
                
            series_id = memory_file.stem.replace('_memory', '')
            char_count = len(memory.get('characters', {}))
            chapter_count = len(memory.get('chapters', []))
            last_updated = memory.get('last_updated', 'Unknown')[:10]
            
            print(f"  📖 {series_id}")
            print(f"     👥 {char_count} characters, 📜 {chapter_count} chapters")
            print(f"     📅 Last updated: {last_updated}")
            print()
            
        except Exception as e:
            print(f"  ❌ Error reading {memory_file.name}: {e}")

def test_json_summarization():
    """Test the JSON summarization system"""
    print("🧪 Testing Smart JSON Summarization System")
    print("=" * 60)
    
    generator = AIScriptGenerator()
    
    # Create mock series memory
    mock_memory = {
        'characters': {
            'Naruto': {'appearances': 15, 'first_chapter': 1, 'last_seen': 15},
            'Sasuke': {'appearances': 12, 'first_chapter': 2, 'last_seen': 14},
            'Sakura': {'appearances': 8, 'first_chapter': 1, 'last_seen': 13}
        },
        'chapters': []
    }
    
    # Add mock chapters
    for i in range(1, 16):
        mock_memory['chapters'].append({
            'id': i,
            'title': f'Chapter {i}: Test Chapter',
            'characters': ['Naruto'] if i % 3 == 0 else ['Naruto', 'Sasuke'],
            'summary': {
                'panels_count': 20 + i,
                'key_dialogue': [f'Important line {i}', f'Key moment {i}'],
                'has_action': i % 2 == 0,
                'dialogue_count': 15 + i
            },
            'date': '2024-01-01'
        })
    
    # Test smart summarization
    json_summary = generator._create_smart_context_summary(mock_memory)
    
    print("📊 Generated JSON Summary:")
    print("-" * 40)
    print(json_summary)
    print("-" * 40)
    
    # Analyze size
    char_count = len(json_summary)
    estimated_tokens = char_count // 4
    
    print(f"📈 Summary Statistics:")
    print(f"   Characters: {char_count}")
    print(f"   Estimated Tokens: {estimated_tokens}")
    print(f"   Compression Ratio: {char_count / (len(str(mock_memory)) * 0.7):.2f}x smaller")
    print(f"   Memory Efficiency: ✅ Excellent" if estimated_tokens < 1000 else f"   Memory Usage: ⚠️ High")
    
    # Test with large series
    print(f"\n🗺 Testing with Large Series (100 chapters):")
    large_memory = mock_memory.copy()
    large_memory['chapters'] = mock_memory['chapters'] * 7  # 105 chapters
    
    large_summary = generator._create_smart_context_summary(large_memory)
    large_chars = len(large_summary)
    large_tokens = large_chars // 4
    
    print(f"   Large Series Summary: {large_chars} chars, ~{large_tokens} tokens")
    print(f"   Context Window Usage: {(large_tokens/30000)*100:.1f}% of 30K limit")
    print(f"   Scalability: ✅ Good" if large_tokens < 5000 else f"   Scalability: ⚠️ Needs optimization")
    
    return True

def test_ai_script_generation():
    """Test function for AI script generation"""
    print("🧪 Testing AI Script Generation")
    
    # Initialize generator
    generator = AIScriptGenerator()
    
    if not generator.is_available():
        print("❌ AI Script Generation not available")
        print("   Set GEMINI_API_KEY environment variable")
        return False
    
    print("✅ AI Script Generation available")
    
    # Create test data
    test_transcripts = []
    test_dir = Path("/tmp/test_ai_script")
    test_dir.mkdir(exist_ok=True)
    
    # Create sample transcript files
    sample_panels = [
        "Hey! What are you doing here?",
        "I... I was just looking for my friend.",
        "Your friend? What does he look like?",
        "He's tall with dark hair... Have you seen him?",
        "No, I haven't. But you shouldn't be here alone."
    ]
    
    for i, text in enumerate(sample_panels, 1):
        file_path = test_dir / f"panel_{i:03d}.txt"
        with open(file_path, 'w') as f:
            f.write(text)
        test_transcripts.append(file_path)
    
    try:
        # Test AI script generation
        enhanced_script, metadata = generator.generate_enhanced_script(
            test_transcripts,
            chapter_title="Test Chapter",
            series_context="A mystery adventure manga about finding lost friends",
            character_info={"Main Character": "A brave student searching for their friend"},
            style_preferences={"emotion_detail": "medium", "scene_descriptions": True}
        )
        
        print(f"✅ Script generated successfully")
        print(f"📊 Generation time: {metadata['generation_time']:.2f}s")
        print(f"🤖 Model used: {metadata['model_used']}")
        print(f"📖 Panels processed: {metadata['panel_count']}")
        
        # Show sample of generated script
        print("\n📜 Sample of generated script:")
        print("-" * 50)
        print(enhanced_script[:500] + "..." if len(enhanced_script) > 500 else enhanced_script)
        print("-" * 50)
        
        # Cleanup
        for file_path in test_transcripts:
            file_path.unlink()
        test_dir.rmdir()
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    # Run test if executed directly
    test_ai_script_generation()
