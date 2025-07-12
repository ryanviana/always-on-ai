"""
Conversation session management for multi-turn interactions - Simplified for transcription
"""

import time
import uuid
from typing import List, Optional, Dict, Any
from enum import Enum
import re


class SessionState(Enum):
    """Conversation session states"""
    WAITING_FOR_INPUT = "waiting_for_input"
    PROCESSING = "processing"
    COMPLETE = "complete"
    TIMEOUT = "timeout"


class ConversationSession:
    """Manages a single conversation session with multi-turn support"""
    
    def __init__(self, session_id: Optional[str] = None, timeout_ms: int = 2000):
        self.session_id = session_id or str(uuid.uuid4())
        self.created_at = time.time()
        self.last_activity = time.time()
        self.timeout_ms = timeout_ms
        self.state = SessionState.WAITING_FOR_INPUT
        
        # Transcription management
        self.transcriptions: List[Dict[str, Any]] = []
        self.merged_text = ""
        
        # Incomplete query detection patterns for Portuguese
        self.incomplete_patterns = [
            # Common conversation starters (with or without punctuation)
            r'^(ei|oi|olá|alô|escuta|olha|veja|me diga|me fala|você pode)$',
            # Questions without content
            r'^(o que|quem|quando|onde|como|qual|quanto|por que)\s*[,!.]?\s*$',
            # Hanging prepositions
            r'\s+(de|do|da|dos|das|para|pra|com|em|no|na|nos|nas)\s*$',
            # Commands without object
            r'^(pesquisa|pesquisar|busca|buscar|procura|procurar|encontra|encontrar|acha|achar)\s*[,!.]?\s*$',
            # Incomplete verb phrases
            r'^(é|são|foi|foram|está|estão|tem|têm)\s*[,!.]?\s*$',
        ]
        
        # Complete sentence indicators
        self.complete_indicators = [
            r'\?$',  # Questions with question mark
            r'[.!]$',  # Sentences with proper ending
            r'(por favor|obrigado|obrigada)$',  # Polite endings
        ]
        
    def add_transcription(self, text: str) -> None:
        """Add a new transcription to the session"""
        self.last_activity = time.time()
        
        transcription_data = {
            'text': text,
            'timestamp': time.time(),
            'is_incomplete': self._is_incomplete(text)
        }
        
        self.transcriptions.append(transcription_data)
        self._update_merged_text()
        
    def _is_incomplete(self, text: str) -> bool:
        """Detect if a transcription seems incomplete"""
        text_lower = text.lower().strip()
        
        # Normalize for comparison
        text_normalized = re.sub(r'[,!.]+', '', text_lower).strip()
        
        # Check incomplete patterns first (they're more specific)
        for pattern in self.incomplete_patterns:
            if re.search(pattern, text_normalized, re.IGNORECASE):
                return True
                
        # Then check if it matches complete indicators
        for pattern in self.complete_indicators:
            if re.search(pattern, text_lower):
                return False
                
        # Additional heuristics
        words = text_lower.split()
        
        # Very short utterances are often incomplete
        if len(words) <= 2:
            return True
            
        # Check if it's just a name or greeting
        greetings = {'oi', 'olá', 'ei', 'alô', 'bom dia', 'boa tarde', 'boa noite'}
        if text_lower in greetings:
            return True
            
        return False
        
    def _update_merged_text(self) -> None:
        """Merge all transcriptions into a single text"""
        texts = [t['text'] for t in self.transcriptions]
        
        # Smart merging logic
        merged_parts = []
        for i, text in enumerate(texts):
            # Remove trailing punctuation from all but the last text
            if i < len(texts) - 1:
                text = re.sub(r'[,!.]+\s*$', '', text)
                
            merged_parts.append(text)
            
        # Join with comma-space, handling existing punctuation
        result = []
        for i, part in enumerate(merged_parts):
            if i == 0:
                result.append(part)
            else:
                # Add comma if previous part doesn't end with punctuation
                if result and not re.search(r'[,!.?]\s*$', result[-1]):
                    result.append(', ')
                else:
                    result.append(' ')
                result.append(part)
                
        self.merged_text = ''.join(result).strip()
        # Clean up multiple spaces and fix comma spacing
        self.merged_text = re.sub(r'\s+', ' ', self.merged_text)
        self.merged_text = re.sub(r'\s*,\s*', ', ', self.merged_text)
        
    def should_wait_for_more(self) -> bool:
        """Determine if we should wait for more input"""
        if not self.transcriptions:
            return True
            
        # Check if session has timed out
        if self.is_timeout():
            return False
            
        # Get the last transcription
        last_transcription = self.transcriptions[-1]
        
        # If the last input was incomplete, wait for more
        if last_transcription['is_incomplete']:
            return True
            
        # If we have multiple transcriptions and they're coming quickly, wait
        if len(self.transcriptions) > 1:
            time_since_last = time.time() - last_transcription['timestamp']
            if time_since_last < 0.5:  # Less than 500ms since last input
                return True
                
        return False
        
    def is_timeout(self) -> bool:
        """Check if the session has timed out"""
        time_since_activity = (time.time() - self.last_activity) * 1000
        return time_since_activity > self.timeout_ms
        
    def get_confidence_score(self) -> float:
        """Get confidence that the accumulated text is complete"""
        if not self.transcriptions:
            return 0.0
            
        # Start with base confidence
        confidence = 0.5
        
        # Increase confidence based on various factors
        last_text = self.transcriptions[-1]['text']
        
        # Check for complete sentence indicators
        if any(re.search(pattern, last_text.lower()) for pattern in self.complete_indicators):
            confidence += 0.3
            
        # Check for incomplete indicators
        if self.transcriptions[-1]['is_incomplete']:
            confidence -= 0.3
            
        # Multiple transcriptions that form a coherent query
        if len(self.transcriptions) > 1:
            # Check if the merged text forms a complete thought
            if self._is_complete_thought(self.merged_text):
                confidence += 0.2
                
        # Timeout increases confidence that we have everything
        if self.is_timeout():
            confidence += 0.1
            
        return max(0.0, min(1.0, confidence))
        
    def _is_complete_thought(self, text: str) -> bool:
        """Check if the text forms a complete thought"""
        text_lower = text.lower().strip()
        
        # Must have a verb and object/complement for most queries
        has_verb = any(verb in text_lower for verb in [
            'é', 'foi', 'são', 'foram', 'está', 'estão',
            'pesquisa', 'busca', 'procura', 'encontra',
            'diga', 'fala', 'mostre', 'quanto', 'qual'
        ])
        
        # Must have substantial content (more than just verb)
        words = text_lower.split()
        has_content = len(words) > 3
        
        return has_verb and has_content
        
    def finalize(self) -> str:
        """Finalize the session and return the merged text"""
        self.state = SessionState.COMPLETE
        return self.merged_text
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for logging"""
        return {
            'session_id': self.session_id,
            'state': self.state.value,
            'transcriptions': self.transcriptions,
            'merged_text': self.merged_text,
            'duration_ms': (time.time() - self.created_at) * 1000,
            'confidence': self.get_confidence_score()
        }