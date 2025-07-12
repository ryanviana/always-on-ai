"""
Transcription buffer to store conversation context
"""

import time
import threading
from collections import deque
from typing import List, Dict, Tuple


class TranscriptionBuffer:
    """Thread-safe circular buffer for storing transcriptions with timestamps"""
    
    def __init__(self, duration_seconds: int = 60):
        self.duration_seconds = duration_seconds
        self.buffer = deque()
        self.lock = threading.Lock()
        
    def add(self, text: str, timestamp: float = None):
        """Add a transcription to the buffer"""
        if timestamp is None:
            timestamp = time.time()
            
        with self.lock:
            self.buffer.append({
                "text": text,
                "timestamp": timestamp
            })
            self._cleanup_old_entries()
            
    def get_context(self, duration_seconds: int = None) -> str:
        """Get conversation context for the specified duration"""
        if duration_seconds is None:
            duration_seconds = self.duration_seconds
            
        current_time = time.time()
        cutoff_time = current_time - duration_seconds
        
        with self.lock:
            # Get entries within the time window
            context_entries = []
            for entry in self.buffer:
                if entry["timestamp"] >= cutoff_time:
                    context_entries.append(entry["text"])
                    
            return " ".join(context_entries)
            
    def get_entries(self, duration_seconds: int = None) -> List[Dict]:
        """Get all entries with timestamps for the specified duration"""
        if duration_seconds is None:
            duration_seconds = self.duration_seconds
            
        current_time = time.time()
        cutoff_time = current_time - duration_seconds
        
        with self.lock:
            return [
                entry.copy() 
                for entry in self.buffer 
                if entry["timestamp"] >= cutoff_time
            ]
            
    def _cleanup_old_entries(self):
        """Remove entries older than the buffer duration"""
        current_time = time.time()
        cutoff_time = current_time - self.duration_seconds
        
        # Remove old entries from the left side of deque
        while self.buffer and self.buffer[0]["timestamp"] < cutoff_time:
            self.buffer.popleft()
            
    def clear(self):
        """Clear all entries from the buffer"""
        with self.lock:
            self.buffer.clear()
            
    def __len__(self):
        """Get the number of entries in the buffer"""
        with self.lock:
            return len(self.buffer)