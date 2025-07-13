"""
Connection coordinator for managing WebSocket lifecycle and mode transitions
"""

import threading
import time
import queue
from typing import Optional, Callable, Dict, Any
from enum import Enum
import base64


class ConnectionMode(Enum):
    """Connection modes"""
    TRANSCRIPTION = "transcription"
    ASSISTANT = "assistant"
    TRANSITIONING = "transitioning"
    DISCONNECTED = "disconnected"


class ConnectionCoordinator:
    """Coordinates WebSocket connections and handles mode transitions"""
    
    def __init__(self,
                 audio_manager,
                 context_manager,
                 on_mode_change: Optional[Callable[[ConnectionMode], None]] = None):
        """
        Initialize connection coordinator
        
        Args:
            audio_manager: AudioStreamManager instance
            context_manager: EnhancedContextManager instance
            on_mode_change: Callback when connection mode changes
        """
        self.audio_manager = audio_manager
        self.context_manager = context_manager
        self.on_mode_change = on_mode_change
        
        # Connection state
        self.current_mode = ConnectionMode.DISCONNECTED
        self.mode_lock = threading.RLock()
        
        # Audio buffering during transitions
        self.transition_buffer = queue.Queue(maxsize=100)
        self.buffering = False
        self.buffer_thread = None
        self.buffer_consumer = None  # Store reference to buffer consumer function
        
        # Current connections
        self.transcriber = None
        self.realtime_session = None
        
        # Transition handling
        self.transition_event = threading.Event()
        self.transition_complete = threading.Event()
        
        # Stats
        self.mode_changes = 0
        self.buffer_overflows = 0
        
    def set_transcriber(self, transcriber):
        """Set the transcriber instance"""
        self.transcriber = transcriber
        
    def set_realtime_session(self, realtime_session):
        """Set the realtime session manager"""
        self.realtime_session = realtime_session
        
    def get_current_mode(self) -> ConnectionMode:
        """Get current connection mode"""
        with self.mode_lock:
            return self.current_mode
            
    def initialize_transcription_mode(self):
        """Initialize connection in transcription mode"""
        with self.mode_lock:
            self.current_mode = ConnectionMode.TRANSCRIPTION
            print("Connection coordinator initialized in transcription mode")
            
        if self.on_mode_change:
            self.on_mode_change(ConnectionMode.TRANSCRIPTION)
            
    def start_assistant_mode(self) -> bool:
        """
        Transition from transcription to assistant mode
        
        Returns:
            True if transition successful, False otherwise
        """
        # Check if we can transition (early return without holding lock long)
        with self.mode_lock:
            if self.current_mode != ConnectionMode.TRANSCRIPTION:
                print(f"Cannot start assistant mode from {self.current_mode.value}")
                return False
                
            # Set transitioning state to prevent concurrent transitions
            print("Starting transition to assistant mode...")
            self.current_mode = ConnectionMode.TRANSITIONING
            self.mode_changes += 1
            
        # Notify mode change outside of lock to prevent deadlock
        if self.on_mode_change:
            try:
                self.on_mode_change(ConnectionMode.TRANSITIONING)
            except Exception as e:
                print(f"Error in mode change callback: {e}")
            
        try:
            # Start buffering audio
            self._start_audio_buffering()
            
            # CRITICAL: Remove transcriber audio consumer BEFORE stopping transcriber
            # This prevents trace trap from audio being sent to closed WebSocket
            if self.transcriber and hasattr(self.transcriber, 'send_audio'):
                print("Removing transcriber audio consumer...")
                try:
                    self.audio_manager.remove_consumer(self.transcriber.send_audio)
                except Exception as e:
                    print(f"Warning: Error removing transcriber consumer: {e}")
                # Give a moment for any in-flight audio to complete
                time.sleep(0.1)
            
            # Pause transcription instead of stopping to avoid crash
            if self.transcriber:
                print("Pausing transcription...")
                try:
                    # Use pause method to keep connection alive
                    self.transcriber.pause()
                    # Give a moment for pause to take effect
                    time.sleep(0.2)
                except Exception as e:
                    print(f"Error pausing transcriber: {e}")
                
            # Get current context for assistant
            context_messages = self.context_manager.get_context_for_realtime()
            
            # Start Realtime session with context
            if self.realtime_session:
                print("Starting Realtime session...")
                # Don't override audio_callback - let the session use what was configured
                success = self.realtime_session.start_session(
                    context_messages=context_messages
                )
                
                if not success:
                    raise Exception("Failed to start Realtime session")
                    
            # Stop buffering and flush to Realtime
            self._stop_audio_buffering(flush_to_realtime=True)
            
            # Update mode
            with self.mode_lock:
                self.current_mode = ConnectionMode.ASSISTANT
                
            if self.on_mode_change:
                self.on_mode_change(ConnectionMode.ASSISTANT)
                
            print("Successfully transitioned to assistant mode")
            return True
            
        except Exception as e:
            print(f"Error transitioning to assistant mode: {e}")
            
            # Rollback - ensure we clean up properly
            try:
                self._stop_audio_buffering(flush_to_realtime=False)
            except Exception as cleanup_error:
                print(f"Error during cleanup: {cleanup_error}")
            
            # Try to restart transcription with delay to avoid rapid reconnects
            if self.transcriber:
                def delayed_reconnect():
                    time.sleep(2.0)  # Wait before reconnecting
                    try:
                        self.transcriber.connect()
                        # Wait for connection and re-add consumer
                        timeout = 3.0
                        start_time = time.time()
                        while time.time() - start_time < timeout:
                            if hasattr(self.transcriber, 'connected') and self.transcriber.connected:
                                # Re-add audio consumer
                                if hasattr(self.transcriber, 'send_audio'):
                                    print("Re-adding transcriber audio consumer after error recovery...")
                                    self.audio_manager.add_consumer(self.transcriber.send_audio)
                                break
                            time.sleep(0.1)
                    except Exception as reconnect_error:
                        print(f"Failed to reconnect transcriber: {reconnect_error}")
                        
                threading.Thread(target=delayed_reconnect, daemon=True, name="TranscriberReconnect").start()
                
            with self.mode_lock:
                self.current_mode = ConnectionMode.TRANSCRIPTION
                
            if self.on_mode_change:
                try:
                    self.on_mode_change(ConnectionMode.TRANSCRIPTION)
                except Exception as callback_error:
                    print(f"Error in mode change callback: {callback_error}")
                
            return False
            
    def end_assistant_mode(self) -> bool:
        """
        Transition from assistant to transcription mode
        
        Returns:
            True if transition successful, False otherwise
        """
        with self.mode_lock:
            if self.current_mode != ConnectionMode.ASSISTANT:
                print(f"Not in assistant mode (current: {self.current_mode.value})")
                return False
                
            print("Ending assistant mode...")
            self.current_mode = ConnectionMode.TRANSITIONING
            
        if self.on_mode_change:
            self.on_mode_change(ConnectionMode.TRANSITIONING)
            
        try:
            # Start buffering audio
            self._start_audio_buffering()
            
            # Close Realtime session if still active
            if self.realtime_session and self.realtime_session.is_active():
                print("Closing Realtime session...")
                self.realtime_session.end_session()
                
                # Wait for clean shutdown
                time.sleep(0.5)
            else:
                print("Realtime session already closed")
                
            # Resume transcription (no need to restart)
            if self.transcriber:
                print("Resuming transcription...")
                self.transcriber.resume()
                
                # Re-add transcriber as audio consumer
                if hasattr(self.transcriber, 'send_audio'):
                    print("Re-adding transcriber audio consumer...")
                    self.audio_manager.add_consumer(self.transcriber.send_audio)
                
            # Stop buffering and discard (transcription will pick up new audio)
            self._stop_audio_buffering(flush_to_realtime=False)
            
            # Update mode
            with self.mode_lock:
                self.current_mode = ConnectionMode.TRANSCRIPTION
                
            if self.on_mode_change:
                self.on_mode_change(ConnectionMode.TRANSCRIPTION)
                
            print("Successfully returned to transcription mode")
            return True
            
        except Exception as e:
            print(f"Error ending assistant mode: {e}")
            
            with self.mode_lock:
                self.current_mode = ConnectionMode.ASSISTANT
                
            if self.on_mode_change:
                self.on_mode_change(ConnectionMode.ASSISTANT)
                
            return False
            
    def _start_audio_buffering(self):
        """Start buffering audio during transition"""
        self.buffering = True
        self.transition_buffer = queue.Queue(maxsize=100)
        
        # Create buffer consumer
        def buffer_audio(audio_base64):
            if self.buffering:
                try:
                    self.transition_buffer.put_nowait(audio_base64)
                except queue.Full:
                    self.buffer_overflows += 1
                    # Drop oldest to make room
                    try:
                        self.transition_buffer.get_nowait()
                        self.transition_buffer.put_nowait(audio_base64)
                    except (queue.Empty, queue.Full):
                        # Buffer is empty or still full, skip this audio chunk
                        pass
        
        # Store reference and add buffer as audio consumer
        self.buffer_consumer = buffer_audio
        self.audio_manager.add_consumer(self.buffer_consumer)
        
        print(f"Audio buffering started")
        
    def _stop_audio_buffering(self, flush_to_realtime: bool = False):
        """Stop buffering and optionally flush to Realtime"""
        self.buffering = False
        
        # Remove buffer consumer using stored reference
        if self.buffer_consumer:
            try:
                self.audio_manager.remove_consumer(self.buffer_consumer)
            except Exception as e:
                print(f"Error removing buffer consumer: {e}")
            finally:
                self.buffer_consumer = None
        
        # Small delay to ensure consumer is fully removed
        time.sleep(0.1)
        
        # Process buffered audio
        buffered_count = self.transition_buffer.qsize() if self.transition_buffer else 0
        print(f"Processing {buffered_count} buffered audio chunks")
        
        if flush_to_realtime and self.realtime_session:
            # Check if realtime session is actually connected before flushing
            if not self.realtime_session.is_active():
                print("Warning: Realtime session not active, discarding buffered audio")
                flush_to_realtime = False
            else:
                # Send buffered audio to Realtime session with rate limiting
                chunks_sent = 0
                max_chunks = 100  # Prevent excessive buffering
                
                while not self.transition_buffer.empty() and chunks_sent < max_chunks:
                    try:
                        audio_base64 = self.transition_buffer.get_nowait()
                        self.realtime_session.send_audio(audio_base64)
                        chunks_sent += 1
                    except queue.Empty:
                        break
                    except Exception as e:
                        print(f"Error flushing audio to Realtime: {e}")
                        break
                        
                if chunks_sent >= max_chunks:
                    print(f"Warning: Flushed maximum {max_chunks} chunks, discarding {self.transition_buffer.qsize()} remaining")
                    
        else:
            # Clear buffer
            while not self.transition_buffer.empty():
                try:
                    self.transition_buffer.get_nowait()
                except queue.Empty:
                    break
                    
        print(f"Audio buffering stopped")
        
    def _handle_realtime_audio(self, audio_data: bytes):
        """Handle audio from Realtime session"""
        # This would be called by Realtime session for audio output
        # Forward to audio output manager
        pass
        
    def handle_connection_error(self, mode: ConnectionMode, error: Exception):
        """Handle connection errors"""
        print(f"Connection error in {mode.value} mode: {error}")
        
        # Attempt recovery based on mode
        if mode == ConnectionMode.TRANSCRIPTION:
            # Try to reconnect transcription
            if self.transcriber:
                threading.Thread(
                    target=self._reconnect_transcription,
                    daemon=True
                ).start()
                
        elif mode == ConnectionMode.ASSISTANT:
            # Force transition back to transcription
            self.end_assistant_mode()
            
    def _reconnect_transcription(self):
        """Attempt to reconnect transcription"""
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                print(f"Reconnection attempt {attempt + 1}/{max_retries}")
                self.transcriber.connect()
                
                with self.mode_lock:
                    self.current_mode = ConnectionMode.TRANSCRIPTION
                    
                if self.on_mode_change:
                    self.on_mode_change(ConnectionMode.TRANSCRIPTION)
                    
                print("Transcription reconnected successfully")
                return
                
            except Exception as e:
                print(f"Reconnection failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    
        print("Failed to reconnect transcription after all attempts")
        
        with self.mode_lock:
            self.current_mode = ConnectionMode.DISCONNECTED
            
        if self.on_mode_change:
            self.on_mode_change(ConnectionMode.DISCONNECTED)
            
    def get_stats(self) -> Dict[str, Any]:
        """Get coordinator statistics"""
        return {
            "current_mode": self.current_mode.value,
            "mode_changes": self.mode_changes,
            "buffer_overflows": self.buffer_overflows,
            "buffering_active": self.buffering,
            "buffer_size": self.transition_buffer.qsize() if self.transition_buffer else 0
        }
        
    def shutdown(self):
        """Shutdown the coordinator"""
        print("Shutting down connection coordinator...")
        
        # Stop buffering first if active
        if self.buffering:
            try:
                self._stop_audio_buffering(flush_to_realtime=False)
            except Exception as e:
                print(f"Error stopping audio buffering: {e}")
        
        # End any active sessions
        if self.current_mode == ConnectionMode.ASSISTANT:
            try:
                self.end_assistant_mode()
            except Exception as e:
                print(f"Error ending assistant mode: {e}")
            
        # Stop any active connections with error handling
        if self.transcriber:
            try:
                self.transcriber.stop()
            except Exception as e:
                print(f"Error stopping transcriber: {e}")
            
        if self.realtime_session:
            try:
                self.realtime_session.shutdown()
            except Exception as e:
                print(f"Error shutting down realtime session: {e}")
            
        with self.mode_lock:
            self.current_mode = ConnectionMode.DISCONNECTED