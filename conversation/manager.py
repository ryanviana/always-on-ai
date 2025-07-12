"""
Conversation manager that handles multi-turn interactions - Simplified for transcription only
"""

import threading
import time
from typing import Optional, Callable, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from .session import ConversationSession, SessionState
from config import DISPLAY_CONFIG


class ConversationManager:
    """Manages conversation sessions and handles multi-turn interactions"""
    
    def __init__(self, 
                 on_complete_callback: Optional[Callable[[str], None]] = None,
                 timeout_ms: int = 2000,
                 quick_response_ms: int = 500):
        """
        Initialize conversation manager
        
        Args:
            on_complete_callback: Function to call when a complete query is ready
            timeout_ms: Maximum time to wait for follow-up input
            quick_response_ms: Time to wait before processing seemingly complete queries
        """
        self.on_complete_callback = on_complete_callback
        self.timeout_ms = timeout_ms
        self.quick_response_ms = quick_response_ms
        
        # Current session management
        self.current_session: Optional[ConversationSession] = None
        self._session_lock = threading.Lock()
        
        # Processing thread
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._wait_task = None
        
        # Stats
        self.sessions_created = 0
        self.sessions_merged = 0
        
    def on_transcription(self, text: str) -> None:
        """Handle a new transcription"""
        colors = DISPLAY_CONFIG["colors"]
        
        with self._session_lock:
            # Cancel any pending wait task
            if self._wait_task and not self._wait_task.done():
                self._wait_task.cancel()
                
            # Create new session if needed
            if not self.current_session or self.current_session.state != SessionState.WAITING_FOR_INPUT:
                self.current_session = ConversationSession(timeout_ms=self.timeout_ms)
                self.sessions_created += 1
                print(f"{colors['info']}[CONVERSATION] New session started{colors['reset']}")
                
            # Add transcription to current session
            self.current_session.add_transcription(text)
            
            # Check if this looks incomplete
            if self.current_session.transcriptions[-1]['is_incomplete']:
                print(f"{colors['info']}[CONVERSATION] Detected incomplete query: \"{text}\" - waiting for more...{colors['reset']}")
            
            # Log session state
            transcription_count = len(self.current_session.transcriptions)
            if transcription_count > 1:
                self.sessions_merged += 1
                print(f"{colors['info']}[CONVERSATION] Merging transcriptions ({transcription_count} parts): \"{self.current_session.merged_text}\"{colors['reset']}")
                
        # Schedule processing
        self._schedule_processing()
        
    def _schedule_processing(self) -> None:
        """Schedule processing of the current session"""
        if not self.current_session:
            return
            
        # Determine wait time based on session state
        if self.current_session.should_wait_for_more():
            # Wait longer for incomplete queries
            wait_time = self.timeout_ms / 1000.0
        else:
            # Quick response for seemingly complete queries
            wait_time = self.quick_response_ms / 1000.0
            
        # Submit wait task
        self._wait_task = self._executor.submit(self._wait_and_process, wait_time)
        
    def _wait_and_process(self, wait_time: float) -> None:
        """Wait for additional input then process"""
        colors = DISPLAY_CONFIG["colors"]
        
        # Store session reference
        session = self.current_session
        if not session:
            return
            
        # Wait for the specified time
        start_time = time.time()
        while time.time() - start_time < wait_time:
            # Check if session was updated (new transcription added)
            if session.last_activity > start_time:
                # Session was updated, abort this wait
                return
                
            time.sleep(0.05)  # Check every 50ms
            
        # Process the session
        with self._session_lock:
            # Make sure this is still the current session
            if self.current_session != session:
                return
                
            # Check confidence before processing
            confidence = session.get_confidence_score()
            merged_text = session.finalize()
            
            print(f"{colors['info']}[CONVERSATION] Processing complete query (confidence: {confidence:.2f}): \"{merged_text}\"{colors['reset']}")
            
            # Log session summary
            session_data = session.to_dict()
            if len(session_data['transcriptions']) > 1:
                print(f"{colors['info']}[CONVERSATION] Session summary:{colors['reset']}")
                for i, trans in enumerate(session_data['transcriptions']):
                    print(f"  Part {i+1}: \"{trans['text']}\" {'(incomplete)' if trans['is_incomplete'] else ''}")
                print(f"  Merged: \"{merged_text}\"")
                print(f"  Duration: {session_data['duration_ms']:.0f}ms")
                
            # Clear current session
            self.current_session = None
            
            # Just print the result for transcription-only mode
            if merged_text:
                print(f"{colors['final']}[MERGED TRANSCRIPTION] {merged_text}{colors['reset']}")
                
            # Trigger callback if provided
            if self.on_complete_callback and merged_text:
                self.on_complete_callback(merged_text)
                
    def on_speech_started(self) -> None:
        """Handle speech start event"""
        # Could use this to prepare for new input
        pass
        
    def on_speech_stopped(self) -> None:
        """Handle speech stop event"""
        # Could use this to trigger faster processing
        pass
        
    def get_stats(self) -> Dict[str, Any]:
        """Get conversation manager statistics"""
        return {
            'sessions_created': self.sessions_created,
            'sessions_merged': self.sessions_merged,
            'merge_rate': self.sessions_merged / max(1, self.sessions_created)
        }
        
    def shutdown(self) -> None:
        """Shutdown the conversation manager"""
        if self._wait_task and not self._wait_task.done():
            self._wait_task.cancel()
        self._executor.shutdown(wait=True)