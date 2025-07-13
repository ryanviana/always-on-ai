"""
Context manager with sliding window and summarization
"""

import time
import threading
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from collections import deque
import openai
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class ContextEntry:
    """Single entry in the context"""
    def __init__(self, text: str, timestamp: float, speaker: str = "user"):
        self.text = text
        self.timestamp = timestamp
        self.speaker = speaker
        self.datetime = datetime.fromtimestamp(timestamp)
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "timestamp": self.timestamp,
            "speaker": self.speaker,
            "datetime": self.datetime.isoformat()
        }
        
    def age_minutes(self) -> float:
        """Get age of entry in minutes"""
        return (time.time() - self.timestamp) / 60.0


class EnhancedContextManager:
    """Manages conversation context with sliding window and summarization"""
    
    def __init__(self, 
                 window_minutes: int = 5,
                 summary_model: str = "gpt-4.1-nano",
                 summary_interval_seconds: int = 60,
                 session_id: str = None):
        """
        Initialize context manager
        
        Args:
            window_minutes: Minutes to keep in raw format
            summary_model: Model to use for summarization
            summary_interval_seconds: Seconds between summarization attempts
            session_id: Unique identifier for this meeting session
        """
        self.window_minutes = window_minutes
        self.summary_model = summary_model
        self.summary_interval_seconds = summary_interval_seconds
        
        # Session management
        self.session_id = session_id or f"meeting_{int(time.time())}"
        self.session_start_time = time.time()
        
        # Storage
        self.recent_entries = deque()
        self.conversation_summary = ""
        self.summary_created_at = 0
        self.thread_lock = threading.RLock()
        
        # OpenAI client
        self.client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Background summarization
        self.summary_thread = None
        self.is_running = False
        self._last_summary_time = 0
        
        # Statistics
        self.total_entries_count = 0
        self.summaries_created_count = 0
        
    def start(self):
        """Start background summarization"""
        if not self.is_running:
            self.is_running = True
            self.summary_thread = threading.Thread(
                target=self._summary_background_worker, 
                daemon=True
            )
            self.summary_thread.start()
            print("Context manager started with background summarization")
            
    def stop(self):
        """Stop background summarization"""
        self.is_running = False
        if self.summary_thread:
            self.summary_thread.join(timeout=2.0)
            
    def add_transcription(self, text: str, timestamp: Optional[float] = None, speaker: str = "user"):
        """Add a new transcription to the context"""
        if not text.strip():
            return
            
        if timestamp is None:
            timestamp = time.time()
            
        with self.thread_lock:
            entry = ContextEntry(text, timestamp, speaker)
            self.recent_entries.append(entry)
            self.total_entries_count += 1
            
            # Clean up old entries that should be summarized
            self._move_expired_entries_to_summary()
            
    def get_full_context(self) -> Dict[str, Any]:
        """Get the complete context with summary and recent entries"""
        with self.thread_lock:
            # Get recent entries
            recent_entries_data = [entry.to_dict() for entry in self.recent_entries]
            
            # Format for display/use
            recent_conversation_text = "\n".join([
                f"[{entry['speaker']}] {entry['text']}" 
                for entry in recent_entries_data
            ])
            
            # Combine summary and recent
            if self.conversation_summary:
                formatted_context = f"=== Previous Conversation Summary ===\n{self.conversation_summary}\n\n=== Recent Conversation ({self.window_minutes} minutes) ===\n{recent_conversation_text}"
            else:
                formatted_context = recent_conversation_text
                
            return {
                "summary": self.conversation_summary,
                "recent": recent_entries_data,
                "formatted": formatted_context,
                "stats": {
                    "total_entries": self.total_entries_count,
                    "recent_count": len(recent_entries_data),
                    "summaries_created": self.summaries_created_count,
                    "summary_age_minutes": (time.time() - self.summary_created_at) / 60.0 if self.summary_created_at else 0
                }
            }
            
    def get_context_for_realtime(self) -> List[Dict[str, Any]]:
        """Get context formatted for OpenAI Realtime API"""
        context_data = self.get_full_context()
        messages = []
        
        # Add summary as system context if available
        if context_data["summary"]:
            messages.append({
                "role": "system",
                "content": f"Previous conversation summary:\n{context_data['summary']}"
            })
            
        # Add recent messages
        for entry in context_data["recent"]:
            role = "assistant" if entry["speaker"] == "assistant" else "user"
            messages.append({
                "role": role,
                "content": entry["text"]
            })
            
        return messages
            
    def get_openai_messages(self) -> List[Dict[str, Any]]:
        """Get context formatted for OpenAI Realtime API"""
        context_data = self.get_full_context()
        openai_messages = []
        
        # Add summary as system context if available
        if context_data["summary"]:
            openai_messages.append({
                "role": "system",
                "content": f"Previous conversation summary:\n{context_data['summary']}"
            })
            
        # Add recent messages
        for entry in context_data["recent"]:
            role = "assistant" if entry["speaker"] == "assistant" else "user"
            openai_messages.append({
                "role": role,
                "content": entry["text"]
            })
            
        return openai_messages
        
    def _move_expired_entries_to_summary(self):
        """Move entries older than window to summary queue"""
        # This is called within lock
        cutoff_time = time.time() - (self.window_minutes * 60)
        
        # Find entries that need to be moved
        expired_entries = []
        while self.recent_entries and self.recent_entries[0].timestamp < cutoff_time:
            expired_entries.append(self.recent_entries.popleft())
            
        # If we have entries to summarize, mark for next summarization
        if expired_entries:
            # For now, we'll trigger summarization in the background thread
            pass
            
    def _summary_background_worker(self):
        """Background worker for summarization"""
        while self.is_running:
            try:
                current_time = time.time()
                
                # Check if we should summarize
                if current_time - self._last_summary_time >= self.summary_interval_seconds:
                    # Check if there's content to summarize
                    should_create_summary = False
                    
                    with self.thread_lock:
                        # Check if we have old entries or the summary is stale
                        if self.recent_entries:
                            oldest_entry_age = self.recent_entries[0].age_minutes()
                            if oldest_entry_age > self.window_minutes * 1.5:
                                should_create_summary = True
                                
                    if should_create_summary:
                        # Run summarization
                        loop = None
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(self._create_summary())
                            
                            self._last_summary_time = current_time
                        finally:
                            # Always close the loop to prevent resource leaks
                            if loop and not loop.is_closed():
                                loop.close()
                        
                # Sleep briefly
                time.sleep(5.0)  # Check every 5 seconds
                
            except Exception as e:
                print(f"Error in summarization worker: {e}")
                time.sleep(10.0)  # Wait 10 seconds on error
                
    async def _create_summary(self):
        """Perform the actual summarization"""
        with self.thread_lock:
            # Get all content that needs summarization
            cutoff_time = time.time() - (self.window_minutes * 60)
            
            # Separate old and recent entries
            expired_entries = []
            remaining_recent_entries = deque()
            
            for entry in self.recent_entries:
                if entry.timestamp < cutoff_time:
                    expired_entries.append(entry)
                else:
                    remaining_recent_entries.append(entry)
                    
            self.recent_entries = remaining_recent_entries
            
            if not expired_entries and not self.conversation_summary:
                return  # Nothing to summarize
                
            # Build content to summarize
            content_to_summarize = []
            
            # Include existing summary if any
            if self.conversation_summary:
                content_to_summarize.append(f"Previous summary:\n{self.conversation_summary}")
                
            # Add old entries
            if expired_entries:
                expired_conversation_text = "\n".join([
                    f"[{entry.speaker}] {entry.text}" 
                    for entry in expired_entries
                ])
                content_to_summarize.append(f"New conversation to add:\n{expired_conversation_text}")
                
        if not content_to_summarize:
            return
            
        # Perform summarization
        try:
            summary_prompt = f"""You are a conversation summarizer. Create a concise summary of the following conversation in Portuguese.
Focus on key topics, decisions, questions asked, and important information shared.
Maintain context about what was discussed and any pending topics.

{chr(10).join(content_to_summarize)}

Provide a clear, concise summary in Portuguese that captures the essence of the conversation:"""

            response = await self.client.chat.completions.create(
                model=self.summary_model,
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            generated_summary = response.choices[0].message.content.strip()
            
            with self.thread_lock:
                self.conversation_summary = generated_summary
                self.summary_created_at = time.time()
                self.summaries_created_count += 1
                
            print(f"Context summarized: {len(expired_entries)} entries → {len(generated_summary)} chars")
            
        except Exception as e:
            print(f"Error performing summarization: {e}")
            
    def force_summary_creation(self):
        """Force immediate summarization"""
        self._last_summary_time = 0  # Reset timer to trigger immediately
        
    def clear_all_context(self):
        """Clear all context"""
        with self.thread_lock:
            self.recent_entries.clear()
            self.conversation_summary = ""
            self.summary_created_at = 0
            
    def get_stats(self) -> Dict[str, Any]:
        """Get context manager statistics"""
        with self.thread_lock:
            return {
                "session_id": self.session_id,
                "session_duration_minutes": (time.time() - self.session_start_time) / 60.0,
                "total_entries": self.total_entries_count,
                "current_recent_entries": len(self.recent_entries),
                "has_summary": bool(self.conversation_summary),
                "summaries_created": self.summaries_created_count,
                "summary_length": len(self.conversation_summary) if self.conversation_summary else 0,
                "oldest_entry_age_minutes": self.recent_entries[0].age_minutes() if self.recent_entries else 0,
                "newest_entry_age_minutes": self.recent_entries[-1].age_minutes() if self.recent_entries else 0
            }
    
    def get_meeting_summary(self) -> Dict[str, Any]:
        """Get complete meeting summary for session persistence"""
        with self.thread_lock:
            # Force summarization of all current content
            all_remaining_entries = list(self.recent_entries)
            
            # Create final meeting summary
            if all_remaining_entries or self.conversation_summary:
                final_content_parts = []
                
                # Include existing summary if any
                if self.conversation_summary:
                    final_content_parts.append(f"Previous summary:\n{self.conversation_summary}")
                    
                # Add all remaining entries
                if all_remaining_entries:
                    final_meeting_conversation = "\n".join([
                        f"[{entry.speaker}] {entry.text}" 
                        for entry in all_remaining_entries
                    ])
                    final_content_parts.append(f"Recent conversation:\n{final_meeting_conversation}")
                    
                complete_meeting_summary = "\n\n".join(final_content_parts) if final_content_parts else ""
                
                return {
                    "session_id": self.session_id,
                    "session_start_time": self.session_start_time,
                    "session_end_time": time.time(),
                    "session_duration_minutes": (time.time() - self.session_start_time) / 60.0,
                    "total_entries": self.total_entries_count,
                    "final_summary": complete_meeting_summary,
                    "all_entries": [entry.to_dict() for entry in all_remaining_entries],
                    "stats": self.get_stats()
                }
            else:
                return {
                    "session_id": self.session_id,
                    "session_start_time": self.session_start_time,
                    "session_end_time": time.time(),
                    "session_duration_minutes": (time.time() - self.session_start_time) / 60.0,
                    "total_entries": 0,
                    "final_summary": "",
                    "all_entries": [],
                    "stats": self.get_stats()
                }