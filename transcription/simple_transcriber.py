#!/usr/bin/env python3
"""
Simple real-time transcription with OpenAI Realtime API
Uses WebSocket connection with server-side VAD
"""

import os
import json
import signal
import sys
import time
from dotenv import load_dotenv
import websocket

# Import centralized config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    DEFAULT_TRANSCRIPTION_MODEL,
    DEFAULT_LANGUAGE,
    AUDIO_CONFIG,
    DEFAULT_VAD,
    API_ENDPOINTS,
    API_HEADERS,
    DISPLAY_CONFIG,
    get_transcription_session_config
)
from conversation import ConversationManager

# Load environment variables
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class SimpleTranscriber:
    def __init__(self, trigger_manager=None, speech_started_callback=None, speech_stopped_callback=None, use_conversation_manager=True):
        self.ws = None
        self.running = False
        self.connected = False  # Track connection state
        self.trigger_manager = trigger_manager
        self.speech_started_callback = speech_started_callback
        self.speech_stopped_callback = speech_stopped_callback
        self.use_conversation_manager = use_conversation_manager
        self.paused = False  # Add pause state
        
        # Initialize conversation manager if enabled
        if self.use_conversation_manager:
            from config import CONVERSATION_CONFIG
            self.conversation_manager = ConversationManager(
                on_complete_callback=self._process_complete_query,
                timeout_ms=CONVERSATION_CONFIG.get("timeout_ms", 2000),
                quick_response_ms=CONVERSATION_CONFIG.get("quick_response_ms", 500)
            )
        else:
            self.conversation_manager = None
        
    def on_open(self, ws):
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]
        
        self.connected = True  # Mark as connected
        
        print(f"{emojis['mic']} Connected to OpenAI Realtime API")
        print(f"{emojis['speaker']} Listening... (Press Ctrl+C to stop)")
        print(f"{colors['info']}Model: {DEFAULT_TRANSCRIPTION_MODEL}{colors['reset']}")
        print(f"{colors['info']}Language: {DEFAULT_LANGUAGE} (Portuguese){colors['reset']}\n")
        
        # Configure transcription session using centralized config
        session_update = get_transcription_session_config()
        ws.send(json.dumps(session_update))
        
    def on_message(self, ws, message):
        try:
            # Track last message time for health monitoring
            import time
            self._last_message_time = time.time()
            
            event = json.loads(message)
            event_type = event.get("type")
            
            colors = DISPLAY_CONFIG["colors"]
            emojis = DISPLAY_CONFIG["emojis"]
            
            # Debug: Print all events in verbose mode
            if os.getenv("DEBUG", "").lower() == "true":
                print(f"{colors['info']}[DEBUG] Event: {event_type}{colors['reset']}")
                print(f"{colors['info']}[DEBUG] Full event: {json.dumps(event, indent=2)}{colors['reset']}")
            
            # Handle transcription events
            if event_type == "conversation.item.input_audio_transcription.delta":
                # Skip partial transcriptions - only show final results
                pass
                
            elif event_type == "conversation.item.input_audio_transcription.completed":
                transcript = event.get("transcript", "")
                print(f"{colors['final']}[final] {transcript}{colors['reset']}\n")
                
                # Skip processing if paused
                if self.paused:
                    print(f"{colors['info']}[Transcription paused, ignoring]{colors['reset']}")
                    return
                
                # Process through conversation manager or directly
                if transcript:
                    if self.use_conversation_manager and self.conversation_manager:
                        # All transcriptions go through conversation manager
                        # Assistant phrases are already marked as complete in session.py
                        # so they will process quickly (500ms instead of 2000ms)
                        self.conversation_manager.on_transcription(transcript)
                    elif self.trigger_manager:
                        # Direct to trigger manager if no conversation manager
                        self.trigger_manager.process_transcription(transcript)
                
            elif event_type == "input_audio_buffer.speech_started":
                print(f"{emojis['speech']} Speech detected...")
                # Notify conversation manager
                if self.conversation_manager:
                    self.conversation_manager.on_speech_started()
                # Call the speech started callback if provided
                if self.speech_started_callback:
                    self.speech_started_callback()
                
            elif event_type == "input_audio_buffer.speech_stopped":
                print(f"{colors['info']}🔇 Speech stopped{colors['reset']}")
                # Notify conversation manager
                if self.conversation_manager:
                    self.conversation_manager.on_speech_stopped()
                # Call the speech stopped callback if provided
                if self.speech_stopped_callback:
                    self.speech_stopped_callback()
                
            elif event_type == "session.created":
                print(f"{colors['info']}✅ Session created successfully{colors['reset']}")
                
            elif event_type == "session.updated":
                print(f"{colors['info']}✅ Session updated successfully{colors['reset']}")
                
            elif event_type == "transcription_session.created":
                print(f"{colors['info']}✅ Transcription session created successfully{colors['reset']}")
                
            elif event_type == "transcription_session.updated":
                print(f"{colors['info']}✅ Transcription session updated successfully{colors['reset']}")
                
            elif event_type == "input_audio_buffer.committed":
                # Audio buffer was committed, transcription will follow
                pass
                
            elif event_type == "conversation.item.created":
                # New conversation item created
                pass
                
            elif event_type == "conversation.item.input_audio_transcription.failed":
                print(f"{colors['error']}❌ Transcription failed for last audio{colors['reset']}")
                
            elif event_type == "error":
                error_details = event.get("error", {})
                error_type = error_details.get("type", "unknown")
                error_code = error_details.get("code", "unknown")
                error_message = error_details.get("message", "Unknown error")
                error_param = error_details.get("param", "")
                
                print(f"{colors['error']}{emojis['error']} Error Details:{colors['reset']}")
                print(f"  Type: {error_type}")
                print(f"  Code: {error_code}")
                print(f"  Message: {error_message}")
                if error_param:
                    print(f"  Parameter: {error_param}")
                print(f"  Full event: {json.dumps(event, indent=2)}")
                
            elif os.getenv("DEBUG", "").lower() == "true":
                # Only print unknown events in debug mode
                print(f"{colors['info']}[DEBUG] Unhandled event type: {event_type}{colors['reset']}")
                print(f"{colors['info']}[DEBUG] Full event: {json.dumps(event, indent=2)}{colors['reset']}")
                
        except json.JSONDecodeError as e:
            colors = DISPLAY_CONFIG["colors"]
            emojis = DISPLAY_CONFIG["emojis"]
            print(f"{colors['error']}{emojis['error']} JSON decode error: {e}{colors['reset']}")
            print(f"Raw message: {message}")
            
    def on_error(self, ws, error):
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]
        print(f"{colors['error']}{emojis['error']} WebSocket error: {error}{colors['reset']}")
        
    def on_close(self, ws, close_status_code, close_msg):
        colors = DISPLAY_CONFIG["colors"]
        print(f"\n👋 Connection closed (Code: {close_status_code}, Message: {close_msg})")
        self.running = False
        self.connected = False
        
        
    def send_audio(self, audio_base64):
        """Send audio data to the transcription API"""
        # Check if we're still running and not paused
        if not self.running or not self.connected or self.paused:
            return
            
        # Use local reference to avoid race conditions
        ws_ref = self.ws
        if not ws_ref:
            return
            
        # Double-check we haven't been shut down
        if not self.running:
            return
            
        try:
            # Check WebSocket state safely
            if hasattr(ws_ref, 'sock') and ws_ref.sock:
                sock_ref = ws_ref.sock
                if hasattr(sock_ref, 'connected') and sock_ref.connected:
                    message = {
                        "type": "input_audio_buffer.append",
                        "audio": audio_base64
                    }
                    ws_ref.send(json.dumps(message))
                    
                    # Track audio sending for debugging
                    if not hasattr(self, '_audio_send_count'):
                        self._audio_send_count = 0
                        self._last_audio_log = 0
                        
                    self._audio_send_count += 1
                    
                    # Reduced audio logging (only log issues)
                    import time
                    current_time = time.time()
                    if current_time - self._last_audio_log > 30.0:
                        self._last_audio_log = current_time
                        self._audio_send_count = 0
                else:
                    # WebSocket not connected
                    self._log_connection_issue("Disconnected")
            else:
                # WebSocket has no socket
                self._log_connection_issue("No socket")
        except Exception as e:
            # Handle any errors gracefully
            if self.running:  # Only log if we're supposed to be running
                colors = DISPLAY_CONFIG["colors"]
                print(f"{colors['error']}[TRANSCRIBER] Error sending audio: {e}{colors['reset']}")
    
    def _log_connection_issue(self, state: str):
        """Log connection issues with rate limiting"""
        if not hasattr(self, '_last_connection_log'):
            self._last_connection_log = 0
            
        import time
        current_time = time.time()
        if current_time - self._last_connection_log > 2.0:
            colors = DISPLAY_CONFIG["colors"]
            print(f"{colors['error']}[TRANSCRIBER] Cannot send audio - WebSocket state: {state}{colors['reset']}")
            self._last_connection_log = current_time
        
    def connect(self):
        """Connect to OpenAI Realtime API"""
        if not OPENAI_API_KEY:
            colors = DISPLAY_CONFIG["colors"]
            emojis = DISPLAY_CONFIG["emojis"]
            print(f"{colors['error']}{emojis['error']} Please set OPENAI_API_KEY in .env file{colors['reset']}")
            return
            
        url = API_ENDPOINTS["transcription"]
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            **API_HEADERS
        }
        
        self.running = True
        
        # Initialize health monitoring
        import time
        self._last_message_time = time.time()
        
        # Start health monitor thread
        import threading
        self._health_thread = threading.Thread(target=self._health_monitor)
        self._health_thread.daemon = True
        self._health_thread.start()
        
        self.ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Run WebSocket
        self.ws.run_forever()
    
    def _health_monitor(self):
        """Monitor WebSocket health"""
        import time
        colors = DISPLAY_CONFIG["colors"]
        
        while self.running:
            # Use shorter sleep intervals for faster shutdown
            for _ in range(10):  # 10 x 1 second = 10 seconds total
                if not self.running:
                    return  # Exit immediately
                time.sleep(1)
            
            # Exit immediately if not running
            if not self.running:
                return
                
            if hasattr(self, '_last_message_time'):
                time_since_last_message = time.time() - self._last_message_time
                if time_since_last_message > 30:
                    print(f"{colors['error']}[HEALTH] Warning: No messages from OpenAI for {time_since_last_message:.1f} seconds{colors['reset']}")
                    
            # Check WebSocket state safely with try-except
            try:
                # Use local reference to avoid race conditions
                ws_ref = self.ws
                if ws_ref and hasattr(ws_ref, 'sock'):
                    sock_ref = ws_ref.sock
                    if sock_ref and hasattr(sock_ref, 'connected'):
                        if not sock_ref.connected:
                            print(f"{colors['error']}[HEALTH] WebSocket disconnected!{colors['reset']}")
            except Exception:
                # WebSocket might be closing, ignore errors
                pass
        
    def _process_complete_query(self, merged_text: str):
        """Process a complete query after conversation manager merges parts"""
        if self.trigger_manager and merged_text:
            self.trigger_manager.process_transcription(merged_text)
            
    def pause(self):
        """Pause transcription processing without closing connection"""
        if self.paused:
            return
            
        print("Pausing transcription...")
        self.paused = True
        
        # Stop conversation manager processing
        if self.conversation_manager:
            # Clear any pending timeouts
            self.conversation_manager.current_session = None
            
    def resume(self):
        """Resume transcription processing"""
        if not self.paused:
            return
            
        print("Resuming transcription...")
        self.paused = False
        
    def stop(self):
        """Stop transcription"""
        import threading
        
        # Set running to False first to stop health monitor
        self.running = False
        self.connected = False
        
        # Create a lock for thread-safe WebSocket access
        ws_lock = threading.Lock()
        
        # Store WebSocket reference safely
        with ws_lock:
            ws_to_close = self.ws
            self.ws = None  # Clear reference immediately
        
        # Wait for health monitor thread to exit properly
        if hasattr(self, '_health_thread') and self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=2.0)
            if self._health_thread.is_alive():
                print("Warning: Health monitor thread did not exit in time")
        
        # Now safely close WebSocket after health thread is done
        if ws_to_close:
            try:
                # Try graceful close first
                if hasattr(ws_to_close, 'close') and callable(ws_to_close.close):
                    ws_to_close.close()
                    # Give it time to close gracefully
                    time.sleep(0.1)
                    
                # Force cleanup if needed
                if hasattr(ws_to_close, 'sock') and ws_to_close.sock:
                    try:
                        ws_to_close.sock.close()
                    except (OSError, AttributeError):
                        # Socket already closed or doesn't exist
                        pass
            except Exception as e:
                print(f"Error closing WebSocket: {e}")
                
        # Shutdown conversation manager
        if self.conversation_manager:
            try:
                self.conversation_manager.shutdown()
            except Exception as e:
                print(f"Error shutting down conversation manager: {e}")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    colors = DISPLAY_CONFIG["colors"]
    emojis = DISPLAY_CONFIG["emojis"]
    print(f"\n\n{colors['error']}{emojis['stop']} Stopping transcription...{colors['reset']}")
    transcriber.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run transcriber
    transcriber = SimpleTranscriber()
    
    colors = DISPLAY_CONFIG["colors"]
    emojis = DISPLAY_CONFIG["emojis"]
    
    print(f"{emojis['rocket']} Starting Simple Transcriber")
    print("=" * 40)
    
    try:
        transcriber.connect()
    except Exception as e:
        print(f"{colors['error']}{emojis['error']} Failed to start: {e}{colors['reset']}")
        transcriber.stop()