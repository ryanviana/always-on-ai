#!/usr/bin/env python3
"""
Realtime Conversation Manager for speech-to-speech conversations
Uses OpenAI Realtime API in conversation mode
"""

import os
import json
import threading
import time
import base64
from typing import Optional, Callable, Dict, Any
from dotenv import load_dotenv
import websocket

# Import centralized config
from config import (
    API_ENDPOINTS,
    API_HEADERS,
    ASSISTANT_MODE_CONFIG,
    DISPLAY_CONFIG,
    get_assistant_session_config
)
from logging_config import get_logger
from events import event_bus, EventTypes

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class RealtimeConversationManager:
    """Manages real-time speech-to-speech conversations with OpenAI Realtime API"""
    
    def __init__(self, audio_callback: Optional[Callable[[str], None]] = None,
                 conversation_ended_callback: Optional[Callable[[], None]] = None):
        self.logger = get_logger(__name__)
        self.ws = None
        self.running = False
        self.connected = False
        self.session_active = False
        
        # Callbacks
        self.audio_callback = audio_callback  # For sending audio to the API
        self.conversation_ended_callback = conversation_ended_callback  # When conversation ends
        
        # Session management
        self.session_start_time = None
        self.last_activity_time = None
        self.conversation_context = None
        
        # Audio handling
        self.audio_output_queue = []
        self.is_receiving_audio = False
        
        # Timeout management
        self.timeout_thread = None
        self.timeout_lock = threading.Lock()
        
    def start_conversation(self, context: Optional[str] = None, 
                          wake_phrase: Optional[str] = None) -> bool:
        """Start a new conversation session"""
        if self.session_active:
            self.logger.warning("Conversation already active")
            return False
            
        self.logger.info("🗣️ Starting Assistant Mode conversation")
        
        try:
            # Store context for injection
            self.conversation_context = context
            
            # Connect to OpenAI Realtime API
            if not self._connect():
                return False
                
            # Start session
            self.session_active = True
            self.session_start_time = time.time()
            self.last_activity_time = time.time()
            
            # Start timeout monitoring
            self._start_timeout_monitoring()
            
            # Emit conversation start event
            event_bus.emit(EventTypes.CONVERSATION_START, {
                "wake_phrase": wake_phrase,
                "context_length": len(context) if context else 0
            }, source="RealtimeConversationManager")
            
            self.logger.info("✅ Assistant Mode conversation started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start conversation: {e}", exc_info=True)
            self.session_active = False
            return False
            
    def stop_conversation(self, reason: str = "manual"):
        """Stop the current conversation session"""
        if not self.session_active:
            return
            
        self.logger.info(f"🛑 Stopping Assistant Mode conversation - {reason}")
        
        try:
            # Stop timeout monitoring
            self._stop_timeout_monitoring()
            
            # Mark session as inactive
            self.session_active = False
            
            # Calculate session duration
            duration = time.time() - self.session_start_time if self.session_start_time else 0
            
            # Disconnect WebSocket
            self._disconnect()
            
            # Emit conversation end event
            event_bus.emit(EventTypes.CONVERSATION_END, {
                "reason": reason,
                "duration": duration
            }, source="RealtimeConversationManager")
            
            # Call callback if provided
            if self.conversation_ended_callback:
                self.conversation_ended_callback()
                
            self.logger.info(f"✅ Assistant Mode conversation ended ({duration:.1f}s)")
            
        except Exception as e:
            self.logger.error(f"Error stopping conversation: {e}", exc_info=True)
            
    def send_audio(self, audio_base64: str):
        """Send audio data to the conversation API"""
        if not self.session_active or not self.connected:
            return
            
        try:
            # Update last activity time
            self.last_activity_time = time.time()
            
            # Send audio to OpenAI
            message = {
                "type": "input_audio_buffer.append",
                "audio": audio_base64
            }
            
            if self.ws:
                self.ws.send(json.dumps(message))
                
        except Exception as e:
            self.logger.error(f"Error sending audio: {e}", exc_info=True)
            
    def _connect(self) -> bool:
        """Connect to OpenAI Realtime API"""
        if not OPENAI_API_KEY:
            self.logger.error("OPENAI_API_KEY not found")
            return False
            
        url = API_ENDPOINTS["conversation"]
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            **API_HEADERS
        }
        
        self.running = True
        
        try:
            self.ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket in a separate thread
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait for connection
            start_time = time.time()
            while time.time() - start_time < 10.0:  # 10 second timeout
                if self.connected:
                    return True
                time.sleep(0.1)
                
            self.logger.error("Connection timeout")
            return False
            
        except Exception as e:
            self.logger.error(f"Connection error: {e}", exc_info=True)
            return False
            
    def _disconnect(self):
        """Disconnect from OpenAI Realtime API"""
        self.running = False
        self.connected = False
        
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")
            finally:
                self.ws = None
                
    def _on_open(self, ws):
        """WebSocket connection opened"""
        colors = DISPLAY_CONFIG["colors"]
        
        self.connected = True
        self.logger.info("🔗 Connected to OpenAI Realtime API for conversation")
        print(f"{colors['info']}🗣️ Assistant Mode active - listening...{colors['reset']}")
        
        # Configure conversation session
        session_config = get_assistant_session_config()
        
        # Inject context if available
        if self.conversation_context:
            instructions = session_config["session"]["instructions"]
            context_injection = f"\n\nContexto da conversa anterior:\n{self.conversation_context}"
            session_config["session"]["instructions"] = instructions + context_injection
            
        ws.send(json.dumps(session_config))
        
    def _on_message(self, ws, message):
        """Handle WebSocket messages from OpenAI"""
        try:
            event = json.loads(message)
            event_type = event.get("type")
            
            colors = DISPLAY_CONFIG["colors"]
            
            # Update activity time for any message
            self.last_activity_time = time.time()
            
            # Debug logging
            if os.getenv("DEBUG", "").lower() == "true":
                self.logger.debug(f"[CONVERSATION] Event: {event_type}")
                
            # Handle different event types
            if event_type == "session.created":
                self.logger.info("✅ Conversation session created")
                
            elif event_type == "session.updated":
                self.logger.info("✅ Conversation session updated")
                
            elif event_type == "input_audio_buffer.speech_started":
                self.logger.debug("🎤 User speech started")
                
            elif event_type == "input_audio_buffer.speech_stopped":
                self.logger.debug("🎤 User speech stopped")
                
            elif event_type == "response.created":
                self.logger.debug("🤖 Assistant response started")
                
            elif event_type == "response.audio.delta":
                # Assistant is speaking - audio output
                audio_delta = event.get("delta", "")
                if audio_delta:
                    self.audio_output_queue.append(audio_delta)
                    # Note: Audio playback will be handled by audio system
                    
            elif event_type == "response.audio.done":
                self.logger.debug("🔊 Assistant speech completed")
                
            elif event_type == "response.done":
                response = event.get("response", {})
                output = response.get("output", [])
                
                # Check for text output (for logging)
                for item in output:
                    if item.get("type") == "message":
                        content = item.get("content", [])
                        for part in content:
                            if part.get("type") == "text":
                                text = part.get("text", "")
                                if text:
                                    self.logger.info(f"🤖 Assistant: {text}")
                                    
                # Check if this response contains end phrases
                self._check_for_end_phrases(output)
                
            elif event_type == "error":
                error_details = event.get("error", {})
                self.logger.error(f"❌ Conversation error: {error_details}")
                self.stop_conversation("error")
                
            elif os.getenv("DEBUG", "").lower() == "true":
                self.logger.debug(f"[CONVERSATION] Unhandled event: {event_type}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
        except Exception as e:
            self.logger.error(f"Message handling error: {e}", exc_info=True)
            
    def _on_error(self, ws, error):
        """WebSocket error occurred"""
        colors = DISPLAY_CONFIG["colors"]
        self.logger.error(f"WebSocket error: {error}")
        print(f"{colors['error']}❌ Conversation error: {error}{colors['reset']}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed"""
        colors = DISPLAY_CONFIG["colors"]
        self.logger.info(f"Conversation connection closed (Code: {close_status_code})")
        print(f"{colors['info']}👋 Assistant Mode ended{colors['reset']}")
        
        self.running = False
        self.connected = False
        
        if self.session_active:
            self.stop_conversation("connection_closed")
            
    def _check_for_end_phrases(self, output):
        """Check if the response contains conversation end phrases"""
        end_phrases = ASSISTANT_MODE_CONFIG.get("end_phrases", [])
        
        for item in output:
            if item.get("type") == "message":
                content = item.get("content", [])
                for part in content:
                    if part.get("type") == "text":
                        text = part.get("text", "").lower()
                        
                        # Check for end phrases
                        for phrase in end_phrases:
                            if phrase.lower() in text:
                                self.logger.info(f"🔚 End phrase detected: {phrase}")
                                self.stop_conversation("end_phrase_detected")
                                return
                                
    def _start_timeout_monitoring(self):
        """Start timeout monitoring thread"""
        with self.timeout_lock:
            if self.timeout_thread is None or not self.timeout_thread.is_alive():
                self.timeout_thread = threading.Thread(target=self._timeout_monitor)
                self.timeout_thread.daemon = True
                self.timeout_thread.start()
                
    def _stop_timeout_monitoring(self):
        """Stop timeout monitoring"""
        with self.timeout_lock:
            if self.timeout_thread:
                # Thread will stop automatically when session_active becomes False
                pass
                
    def _timeout_monitor(self):
        """Monitor for session timeouts"""
        while self.session_active:
            try:
                current_time = time.time()
                
                # Check session timeout
                session_timeout = ASSISTANT_MODE_CONFIG.get("session_timeout", 300)
                if self.session_start_time and (current_time - self.session_start_time) > session_timeout:
                    self.logger.info("⏰ Session timeout reached")
                    self.stop_conversation("session_timeout")
                    break
                    
                # Check idle timeout
                idle_timeout = ASSISTANT_MODE_CONFIG.get("idle_timeout", 30)
                if self.last_activity_time and (current_time - self.last_activity_time) > idle_timeout:
                    self.logger.info("💤 Idle timeout reached")
                    self.stop_conversation("idle_timeout")
                    break
                    
                # Sleep for 1 second before next check
                time.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"Timeout monitor error: {e}", exc_info=True)
                break
                
    def is_active(self) -> bool:
        """Check if conversation is currently active"""
        return self.session_active and self.connected
        
    def get_audio_queue(self) -> list:
        """Get and clear the audio output queue"""
        queue = self.audio_output_queue.copy()
        self.audio_output_queue.clear()
        return queue