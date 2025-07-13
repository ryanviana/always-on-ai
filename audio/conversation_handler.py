#!/usr/bin/env python3
"""
Conversation Audio Handler - Manages audio routing for conversation mode
"""

import threading
import time
from typing import Optional, Callable, List
from core.logging_config import get_logger
from events import event_bus, EventTypes
from config import DISPLAY_CONFIG


class ConversationAudioHandler:
    """Handles audio routing and management for conversation mode"""
    
    def __init__(self, audio_stream_manager, transcriber):
        self.logger = get_logger(__name__)
        self.audio_stream_manager = audio_stream_manager
        self.transcriber = transcriber
        
        # Conversation state
        self.conversation_active = False
        self.conversation_manager = None
        
        # Audio state tracking
        self.transcription_consumers = []  # Store original consumers during conversation
        self.conversation_consumers = []   # Active conversation consumers
        
        # Thread safety
        self.state_lock = threading.Lock()
        
        # Audio output handling
        self.audio_output_handler = None
        
        self.logger.info("🎵 ConversationAudioHandler initialized")
        
    def start_conversation_mode(self, conversation_manager) -> bool:
        """Switch audio routing to conversation mode"""
        with self.state_lock:
            if self.conversation_active:
                self.logger.warning("Conversation mode already active")
                return False
                
            try:
                colors = DISPLAY_CONFIG["colors"]
                self.logger.info("🔄 Switching to conversation mode audio routing")
                print(f"{colors['info']}🔄 Switching to Assistant Mode...{colors['reset']}")
                
                # Store the conversation manager
                self.conversation_manager = conversation_manager
                
                # Pause transcription processing (but keep audio flowing)
                if self.transcriber:
                    self.transcriber.pause()
                    self.logger.debug("Transcriber paused for conversation mode")
                
                # Store current audio consumers
                with self.audio_stream_manager.consumers_lock:
                    self.transcription_consumers = self.audio_stream_manager.consumers.copy()
                    self.audio_stream_manager.consumers.clear()
                    
                # Add conversation consumer
                conversation_consumer = self._create_conversation_consumer()
                self.audio_stream_manager.add_consumer(conversation_consumer)
                self.conversation_consumers = [conversation_consumer]
                
                # Set conversation active
                self.conversation_active = True
                
                # Emit audio mode switch event
                event_bus.emit(EventTypes.CONVERSATION_AUDIO_INPUT, {
                    "mode": "conversation",
                    "transcription_consumers_stored": len(self.transcription_consumers)
                }, source="ConversationAudioHandler")
                
                self.logger.info("✅ Audio routing switched to conversation mode")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to start conversation mode: {e}", exc_info=True)
                # Restore original state on error
                self._restore_transcription_mode()
                return False
                
    def stop_conversation_mode(self) -> bool:
        """Switch audio routing back to transcription mode"""
        with self.state_lock:
            if not self.conversation_active:
                self.logger.debug("Conversation mode not active")
                return True
                
            try:
                colors = DISPLAY_CONFIG["colors"]
                self.logger.info("🔄 Switching back to transcription mode audio routing")
                print(f"{colors['info']}🔄 Returning to transcription mode...{colors['reset']}")
                
                return self._restore_transcription_mode()
                
            except Exception as e:
                self.logger.error(f"Failed to stop conversation mode: {e}", exc_info=True)
                return False
                
    def _restore_transcription_mode(self) -> bool:
        """Internal method to restore transcription mode"""
        try:
            # Remove conversation consumers
            for consumer in self.conversation_consumers:
                self.audio_stream_manager.remove_consumer(consumer)
            self.conversation_consumers.clear()
            
            # Restore transcription consumers
            with self.audio_stream_manager.consumers_lock:
                for consumer in self.transcription_consumers:
                    self.audio_stream_manager.consumers.append(consumer)
                    # Remove from failed consumers if it was there
                    self.audio_stream_manager.failed_consumers.discard(consumer)
            
            # Resume transcription processing
            if self.transcriber:
                self.transcriber.resume()
                self.logger.debug("Transcriber resumed for transcription mode")
            
            # Clear conversation state
            self.conversation_active = False
            self.conversation_manager = None
            self.transcription_consumers.clear()
            
            # Emit audio mode switch event
            event_bus.emit(EventTypes.CONVERSATION_AUDIO_INPUT, {
                "mode": "transcription",
                "consumers_restored": len(self.transcription_consumers)
            }, source="ConversationAudioHandler")
            
            self.logger.info("✅ Audio routing restored to transcription mode")
            return True
            
        except Exception as e:
            self.logger.error(f"Error restoring transcription mode: {e}", exc_info=True)
            return False
            
    def _create_conversation_consumer(self) -> Callable[[str], None]:
        """Create audio consumer function for conversation mode"""
        def conversation_audio_consumer(audio_base64: str):
            """Audio consumer that sends audio to conversation manager"""
            try:
                if self.conversation_manager and self.conversation_active:
                    # Send audio to conversation manager
                    self.conversation_manager.send_audio(audio_base64)
                    
                    # Emit audio input event (optional, for monitoring)
                    if hasattr(self, '_last_audio_event_time'):
                        current_time = time.time()
                        if current_time - self._last_audio_event_time > 5.0:  # Rate limit events
                            event_bus.emit(EventTypes.CONVERSATION_AUDIO_INPUT, {
                                "audio_length": len(audio_base64)
                            }, source="ConversationAudioHandler")
                            self._last_audio_event_time = current_time
                    else:
                        self._last_audio_event_time = time.time()
                        
            except Exception as e:
                self.logger.error(f"Error in conversation audio consumer: {e}")
                # Don't raise exception to avoid being marked as failed consumer
                
        return conversation_audio_consumer
        
    def handle_conversation_audio_output(self, audio_queue: List[str]):
        """Handle audio output from conversation (for future audio playback)"""
        if not audio_queue:
            return
            
        try:
            # For now, just log that we received audio
            # In a full implementation, this would handle audio playback
            total_audio = len(audio_queue)
            self.logger.debug(f"🔊 Received {total_audio} audio chunks from assistant")
            
            # Emit audio output event
            event_bus.emit(EventTypes.CONVERSATION_AUDIO_OUTPUT, {
                "chunks_received": total_audio
            }, source="ConversationAudioHandler")
            
            # TODO: Implement actual audio playback
            # This would involve:
            # 1. Decoding base64 audio chunks
            # 2. Concatenating audio data
            # 3. Playing through audio output device
            # 4. Managing playback timing and feedback prevention
            
        except Exception as e:
            self.logger.error(f"Error handling conversation audio output: {e}", exc_info=True)
            
    def is_conversation_active(self) -> bool:
        """Check if conversation mode is currently active"""
        with self.state_lock:
            return self.conversation_active
            
    def get_conversation_manager(self):
        """Get the current conversation manager"""
        with self.state_lock:
            return self.conversation_manager
            
    def get_status(self) -> dict:
        """Get current status of audio handler"""
        with self.state_lock:
            return {
                "conversation_active": self.conversation_active,
                "transcription_consumers_stored": len(self.transcription_consumers),
                "conversation_consumers_active": len(self.conversation_consumers),
                "has_conversation_manager": self.conversation_manager is not None
            }
            
    def emergency_restore(self):
        """Emergency restore to transcription mode (for error recovery)"""
        self.logger.warning("🚨 Emergency restore to transcription mode")
        try:
            with self.state_lock:
                if self.conversation_active:
                    self._restore_transcription_mode()
        except Exception as e:
            self.logger.error(f"Emergency restore failed: {e}", exc_info=True)