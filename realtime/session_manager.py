"""
Realtime session manager for speech-to-speech conversations with OpenAI
"""

import json
import threading
import time
import asyncio
import websocket
from typing import Optional, Dict, Any, List, Callable
import os
from dotenv import load_dotenv
import sys

# Import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VAD_CONFIG, AUDIO_DEVICE_CONFIG, DEFAULT_CONVERSATION_VAD
from events import event_bus, EventTypes
from logging_config import get_logger
from .tool_execution_manager import ToolExecutionManager
from .tools.registry import ToolRegistry

load_dotenv()


class RealtimeSessionManager:
    """Manages OpenAI Realtime API sessions for speech-to-speech conversations"""
    
    def __init__(self,
                 audio_callback: Optional[Callable[[bytes], None]] = None,
                 on_session_end: Optional[Callable[[], None]] = None,
                 vad_mode: str = "server_vad"):
        """
        Initialize Realtime session manager
        
        Args:
            audio_callback: Function to call with audio output from assistant
            on_session_end: Function to call when session ends
            vad_mode: Voice activity detection mode ('server_vad' or 'semantic_vad')
        """
        self.logger = get_logger(__name__)
        self.audio_callback = audio_callback
        self.on_session_end = on_session_end
        self.vad_mode = vad_mode
        
        # Session state
        self.ws = None
        self.session_id = None
        self.connected = False
        self.session_active = False
        self.session_ending = False  # Prevent multiple concurrent end attempts
        
        # Configuration
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = "gpt-4o-realtime-preview-2025-06-03"
        self.voice = "alloy"
        
        # Tool management
        self.tool_registry = ToolRegistry()
        self.tool_execution_manager = ToolExecutionManager(self.tool_registry, logger=self.logger)
        
        # Session tracking
        self.session_start_time = 0
        self.messages_sent = 0
        self.messages_received = 0
        
        # End phrases detection
        self.end_phrases = [
            "obrigado bot", "obrigada bot", "thank you bot", "thanks bot",
            "tchau bot", "bye bot", "até logo bot", "goodbye bot",
            "encerrar conversa", "end conversation", "terminar sessão"
        ]
        
        # Response handling
        self.current_response_id = None
        self.response_buffer = {}
        
        # Track assistant speaking state
        self.assistant_speaking = False
        self._audio_handler = None  # Will be set externally
        self._current_response_paused = False  # Track if we've paused for current response
        
        # Track goodbye state for natural conversation ending
        self._user_said_goodbye = False
        self._goodbye_timer = None
        self._session_end_timer = None  # Track pending session end timers
        
        # Reconnection handling
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._reconnect_timer = None
        
        # Connection error tracking
        self._connection_error = None
        
        # Heartbeat tracking
        self._heartbeat_timer = None
        self._heartbeat_interval = 30.0  # Send ping every 30 seconds
        self._last_pong_time = None
        
        self.logger.debug("RealtimeSessionManager initialized with audio_handler=None")
        
    @property
    def audio_handler(self):
        """Get the audio handler"""
        return self._audio_handler
        
    @audio_handler.setter
    def audio_handler(self, handler):
        """Set the audio handler with logging"""
        self.logger.debug(f"Setting audio_handler in RealtimeSessionManager: {type(handler).__name__ if handler else 'None'}")
        self._audio_handler = handler
        
    def register_tool(self, name: str, tool_instance):
        """Register a tool for use in conversations"""
        self.tool_registry.register(tool_instance, name)
        
    def start_session(self, 
                     context_messages: List[Dict[str, Any]] = None,
                     audio_callback: Optional[Callable[[bytes], None]] = None) -> bool:
        """
        Start a new Realtime session
        
        Args:
            context_messages: Previous conversation context
            audio_callback: Override default audio callback
            
        Returns:
            True if session started successfully
        """
        if self.session_active:
            self.logger.warning("Session already active")
            return False
            
        if audio_callback:
            self.audio_callback = audio_callback
            
        # Reset response tracking flag for new session
        self._current_response_paused = False
        
        # Reset goodbye tracking
        self._user_said_goodbye = False
        self.session_ending = False
        if self._goodbye_timer:
            self._goodbye_timer.cancel()
            self._goodbye_timer = None
        if self._session_end_timer:
            self._session_end_timer.cancel()
            self._session_end_timer = None
        
        self.logger.debug(f"Starting session - audio_handler connected: {self.audio_handler is not None}")
        
        # Validate API key
        if not self.api_key:
            self.logger.error("No API key provided")
            return False
            
        try:
            # Connect to Realtime API with model parameter
            url = f"wss://api.openai.com/v1/realtime?model={self.model}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self.logger.info("Connecting to OpenAI Realtime API", extra={"extra_data": {"model": self.model, "url": url}})
            
            # Reset connection state
            self.connected = False
            self._connection_error = None
            
            self.ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=lambda ws: self._on_open(ws, context_messages),
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket in separate thread
            self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True, name="RealtimeWSThread")
            self.ws_thread.start()
            
            # Wait for connection with proper timeout
            timeout = 10.0  # Increased from 5.0
            start = time.time()
            check_interval = 0.1
            last_log = 0
            
            while time.time() - start < timeout:
                # Check if connected
                if self.connected:
                    self.logger.info(f"Connected successfully after {time.time() - start:.2f}s")
                    break
                    
                # Check for connection error
                if self._connection_error:
                    self.logger.error(f"Connection failed: {self._connection_error}")
                    break
                    
                # Check if thread died
                if not self.ws_thread.is_alive():
                    self.logger.error("WebSocket thread died during connection")
                    break
                
                # Log progress every 2 seconds
                elapsed = time.time() - start
                if elapsed - last_log > 2.0:
                    self.logger.debug(f"Still connecting... ({elapsed:.1f}s elapsed)")
                    last_log = elapsed
                    
                time.sleep(check_interval)
                
            if not self.connected:
                self.logger.error(f"Failed to connect to Realtime API after {time.time() - start:.2f}s")
                # Clean up the failed connection
                if self.ws:
                    try:
                        self.ws.close()
                    except Exception as e:
                        print(f"[REALTIME ERROR] Error closing WebSocket: {e}")
                    self.ws = None
                return False
                
            self.session_active = True
            self.session_start_time = time.time()
            self.logger.info("Realtime session started successfully")
            
            # Note: Session start event will be emitted when we receive the session ID
            
            return True
            
        except Exception as e:
            print(f"Error starting Realtime session: {e}")
            return False
            
    def _on_open(self, ws, context_messages: List[Dict[str, Any]] = None):
        """Handle WebSocket connection open"""
        # Check if we're still supposed to be connecting
        if not self.ws or ws != self.ws:
            print("[REALTIME WARNING] Ignoring late connection - session already cleaned up")
            return
            
        self.connected = True
        print("[REALTIME] Successfully connected to OpenAI Realtime API")
        
        # Start heartbeat
        self._start_heartbeat()
        
        # Configure session
        vad_config = VAD_CONFIG.get(self.vad_mode, DEFAULT_CONVERSATION_VAD).copy()
        vad_config["create_response"] = True
        vad_config["interrupt_response"] = True
        
        print(f"[SESSION_CONFIG] VAD mode: {self.vad_mode}")
        print(f"[SESSION_CONFIG] VAD config: {vad_config}")
        
        session_config = {
            "type": "session.update",
            "session": {
                "model": self.model,
                "voice": self.voice,
                "instructions": """You are a helpful Portuguese-speaking AI assistant in a voice conversation.
                
Key behaviors:
- Respond naturally in Portuguese (Brazilian) unless the user speaks another language
- Keep responses concise and conversational for voice interaction
- Listen for phrases like "obrigado bot" or "tchau bot" to end the conversation
- Be helpful, friendly, and maintain context throughout the conversation

CRITICAL TOOL USAGE RULES:
- You MUST use tools when the user asks for information that requires them
- When a user asks you to search, check weather, do calculations, or get the time, you MUST call the appropriate tool
- Do NOT pretend to search or say you're searching without actually calling the search tool
- Do NOT make up information - always use tools to get real data
- If a tool is needed, call it IMMEDIATELY - don't say you're going to do it, just do it

Examples of REQUIRED tool usage:
- "pesquise o preço de carros" → MUST call search tool with query "preço de carros"
- "qual é o clima hoje" → MUST call weather tool
- "que horas são" → MUST call datetime tool
- "quanto é 25 x 4" → MUST call calculator tool

When the user says goodbye or thanks you to end the conversation, acknowledge it politely and indicate the conversation is ending.""",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": vad_config,
                "tools": self.tool_execution_manager.get_tool_schemas(),
                "temperature": 0.6,  # Lower temperature for more consistent tool usage
                "tool_choice": "auto",  # Let the model decide when to use tools
                "modalities": ["audio", "text"]  # Always support both audio and text
            }
        }
        
        tool_schemas = self.tool_execution_manager.get_tool_schemas()
        print(f"[SESSION_CONFIG] Tools count: {len(tool_schemas)}")
        if tool_schemas:
            tool_names = [schema.get('name', 'unknown') for schema in tool_schemas]
            print(f"[SESSION_CONFIG] Registered tools: {tool_names}")
            # Debug: Print full schema for datetime tool
            for schema in tool_schemas:
                if schema.get('name') == 'datetime':
                    print(f"[DEBUG] DateTime tool schema: {json.dumps(schema, indent=2)}")
        print(f"[SESSION_CONFIG] Temperature: 0.6, Tool choice: auto, Modalities: audio+text")
        
        # Debug: Print the full session config being sent
        print(f"[DEBUG] Full session config tools: {json.dumps(session_config['session']['tools'][:1], indent=2)}...")
        
        ws.send(json.dumps(session_config))
        
        # Send context if provided
        if context_messages:
            self._send_context(context_messages, trigger_response=True)
            
    def _send_context(self, context_messages: List[Dict[str, Any]], trigger_response: bool = False):
        """Send conversation context to the session"""
        # Convert context to conversation items
        for message in context_messages:
            if message.get("role") == "system":
                # Add as conversation context
                context_item = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "system",
                        "content": [{
                            "type": "input_text",
                            "text": message["content"]
                        }]
                    }
                }
            else:
                # Add as conversation history
                context_item = {
                    "type": "conversation.item.create", 
                    "item": {
                        "type": "message",
                        "role": message.get("role", "user"),
                        "content": [{
                            "type": "input_text",
                            "text": message["content"]
                        }]
                    }
                }
                
            self.ws.send(json.dumps(context_item))
            
        print(f"Sent {len(context_messages)} context messages")
        
        # Optionally trigger a response after sending context
        if trigger_response:
            self.ws.send(json.dumps({"type": "response.create"}))
            print("Triggered response generation after context")
        
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            event = json.loads(message)
            event_type = event.get("type")
            
            # Update heartbeat tracking on any message
            self._last_pong_time = time.time()
            
            # Log all events for debugging (except high-frequency ones)
            if event_type not in ["response.audio.delta", "input_audio_buffer.append"]:
                self.logger.debug(f"[EVENT] Received: {event_type}")
                if event_type.startswith("response.") and event_type != "response.audio.delta":
                    print(f"[RESPONSE_EVENT] {event_type}")
            
            # Handle different event types
            if event_type == "session.created":
                self.session_id = event["session"]["id"]
                self.logger.info(f"Session created: {self.session_id}")
                
                # Update tool execution manager with session ID
                self.tool_execution_manager.set_session_id(self.session_id)
                
                # Now emit the session start event with the actual session ID
                self.logger.debug(f"Emitting ASSISTANT_SESSION_START event for session {self.session_id}")
                event_bus.emit(EventTypes.ASSISTANT_SESSION_START, {
                    "session_id": self.session_id,
                    "model": self.model,
                    "voice": self.voice,
                    "vad_mode": self.vad_mode
                }, source="RealtimeSessionManager")
                
            elif event_type == "conversation.item.created":
                # New conversation item
                item = event.get("item", {})
                item_type = item.get("type", "unknown")
                item_role = item.get("role", "unknown")
                item_id = item.get("id", "unknown")
                
                print(f"[CONVERSATION] Item created - type: {item_type}, role: {item_role}, id: {item_id}")
                
                # Log message content for debugging
                if item_type == "message":
                    content = item.get("content", [])
                    for content_item in content:
                        if content_item.get("type") == "text":
                            text = content_item.get("text", "")
                            if text:
                                print(f"[CONVERSATION] {item_role}: {text}")
                        elif content_item.get("type") == "audio":
                            print(f"[CONVERSATION] {item_role}: [audio content]")
                
                if item_type == "message" and item_role == "assistant":
                    self.messages_received += 1
                elif item_type == "function_call":
                    func_name = item.get("name", "unknown")
                    call_id = item.get("call_id", "unknown")
                    arguments = item.get("arguments", "{}")
                    print(f"[CONVERSATION] Function call item created: {func_name} (call_id: {call_id})")
                    self.logger.info(f"[CONVERSATION] Function call item: {func_name}")
                    
                    # Don't execute here - wait for response.done which has complete arguments
                    print(f"[FUNCTION_CALL] Will execute {func_name} when response completes")
                    
            elif event_type == "response.audio.start":
                # Assistant started speaking
                self.assistant_speaking = True
                print(f"[AUDIO] response.audio.start - Assistant starting to speak")
                
                # Emit assistant speaking start event
                event_bus.emit(EventTypes.ASSISTANT_SPEAKING_START, {
                    "session_id": self.session_id
                }, source="RealtimeSessionManager")
                
                print(f"[AUDIO] audio_handler present: {self.audio_handler is not None}")
                if self.audio_handler:
                    print(f"[AUDIO] audio_handler type: {type(self.audio_handler).__name__}")
                    print(f"[AUDIO] has pause_input: {hasattr(self.audio_handler, 'pause_input')}")
                    try:
                        print("[AUDIO] >>> Calling pause_input() to prevent feedback <<<")
                        # Temporarily remove microphone input to prevent feedback
                        self.audio_handler.pause_input()
                        print("[AUDIO] ✓ pause_input() completed")
                    except Exception as e:
                        print(f"[ERROR] Failed to pause input: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("[WARNING] audio_handler is None, cannot pause input")
                
            elif event_type == "response.created":
                # Response creation started
                response_obj = event.get("response", {})
                response_id = response_obj.get("id", "unknown")
                print(f"[RESPONSE] Response created: {response_id}")
                self.logger.info(f"[RESPONSE] Response created with id: {response_id}")
                
                # Log what triggered this response
                metadata = response_obj.get("metadata", {})
                if metadata:
                    print(f"[RESPONSE] Metadata: {metadata}")
                
            elif event_type == "response.done":
                # Response completed
                response = event.get("response", {})
                response_id = response.get("id", "unknown")
                status = response.get("status", "unknown")
                output_count = len(response.get("output", []))
                print(f"[RESPONSE] Response done: {response_id}, status: {status}, outputs: {output_count}")
                self.logger.info(f"[RESPONSE] Response completed - id: {response_id}, status: {status}, outputs: {output_count}")
                
                # Check response outputs
                outputs = response.get("output", [])
                has_function_call = False
                for output in outputs:
                    output_type = output.get("type")
                    if output_type == "function_call":
                        func_name = output.get("name", "unknown")
                        call_id = output.get("call_id", "unknown")
                        arguments = output.get("arguments", "{}")
                        print(f"[RESPONSE] Response contains function call: {func_name} (call_id: {call_id})")
                        self.logger.info(f"[RESPONSE] Function call in response: {func_name}")
                        has_function_call = True
                        
                        # Execute the function if we haven't already
                        if func_name != "unknown" and call_id != "unknown":
                            print(f"[FUNCTION_CALL] Executing function from response.done: {func_name}")
                            self._execute_tool_async(call_id, func_name, arguments)
                    elif output_type == "message":
                        # Log message content to see what model said instead of calling function
                        content = output.get("content", [])
                        for item in content:
                            if item.get("type") == "text":
                                text = item.get("text", "")
                                print(f"[RESPONSE_TEXT] Model said: {text[:200]}..." if len(text) > 200 else f"[RESPONSE_TEXT] Model said: {text}")
                                self.logger.info(f"[RESPONSE_TEXT] {text}")
                
                if not has_function_call and outputs:
                    self.logger.warning("[NO_FUNCTION_CALL] Response completed without function call despite tools being available")
                    
            elif event_type == "response.audio.delta":
                # Audio chunk from assistant
                
                # Pause microphone on first audio chunk if not already paused
                if not self._current_response_paused and self.audio_handler:
                    print("[AUDIO] response.audio.delta - First audio chunk, pausing microphone")
                    try:
                        self.audio_handler.pause_input()
                        self._current_response_paused = True
                        self.assistant_speaking = True
                        print("[AUDIO] ✓ Microphone paused on first audio chunk")
                    except Exception as e:
                        print(f"[ERROR] Failed to pause on audio delta: {e}")
                
                if self.audio_callback:
                    audio_b64 = event.get("delta", "")
                    if audio_b64:
                        import base64
                        audio_data = base64.b64decode(audio_b64)
                        self.audio_callback(audio_data)
                        
            elif event_type == "response.audio_transcript.done":
                # Assistant's speech transcription
                transcript = event.get("transcript", "")
                if transcript:
                    print(f"Assistant: {transcript}")
                    
                    # Log if assistant mentions tools but doesn't call them
                    assistant_lower = transcript.lower()
                    tool_words = ["pesquisando", "buscando", "procurando", "searching", "looking", "verificando", "consultando", "calculando"]
                    if any(word in assistant_lower for word in tool_words):
                        self.logger.warning(f"[TOOL_HALLUCINATION] Assistant said it's using tools but no function call detected: '{transcript}'")
                        print(f"[WARNING] Assistant claims to be using tools but no function call detected!")
                        print(f"[WARNING] Full transcript: {transcript}")
                    
                    # Check for end phrases (is_user=False for assistant)
                    if self._check_end_phrases(transcript, is_user=False):
                        print(f"[SESSION] Assistant goodbye detected in: '{transcript}'")
                        self._schedule_session_end(delay=2.0, reason="assistant_goodbye")
                        
            elif event_type == "response.audio.done":
                # Assistant finished speaking
                self.assistant_speaking = False
                print("[DEBUG] response.audio.done - assistant_speaking set to False")
                # Reset the pause flag for next response
                self._current_response_paused = False
                print(f"[DEBUG] response.audio.done received - audio_handler: {self.audio_handler is not None}")
                print(f"[DEBUG] Reset pause flag for next response")
                
                # Emit assistant speaking end event
                event_bus.emit(EventTypes.ASSISTANT_SPEAKING_END, {
                    "session_id": self.session_id
                }, source="RealtimeSessionManager")
                if self.audio_handler:
                    print("[DEBUG] Assistant finished speaking, scheduling microphone resume")
                    # Resume microphone input after a longer delay to prevent echo
                    # Increased from 0.5s to 2.5s to allow audio to fully play out and echo to dissipate
                    threading.Timer(2.5, self._resume_audio_input).start()
                else:
                    print("[WARNING] audio_handler is None, cannot resume input")
                        
            elif event_type == "input_audio_buffer.speech_started":
                # User started speaking
                print("User speaking...")
                
                # Cancel goodbye timer if user starts speaking again
                if self._goodbye_timer:
                    self._goodbye_timer.cancel()
                    self._goodbye_timer = None
                
            elif event_type == "input_audio_buffer.speech_stopped": 
                # User stopped speaking
                print("User stopped speaking")
                
                # If user said goodbye and stops speaking, start a longer timeout
                if self._user_said_goodbye and not self._goodbye_timer:
                    print("[DEBUG] Starting goodbye timeout (60s)")
                    # Much longer timeout - 60 seconds instead of 10
                    self._goodbye_timer = threading.Timer(60.0, self._check_goodbye_timeout)
                    self._goodbye_timer.start()
                
            elif event_type == "conversation.item.input_audio_transcription.completed":
                # User's speech transcription
                transcript = event.get("transcript", "")
                if transcript:
                    print(f"User: {transcript}")
                    self.messages_sent += 1
                else:
                    # Log that we got an empty transcript
                    print("[DEBUG] Received input_audio_transcription.completed with empty transcript")
                    
                    # Log if user is likely asking for a tool
                    transcript_lower = transcript.lower()
                    tool_keywords = {
                        "search": ["pesquise", "busque", "procure", "search", "find"],
                        "weather": ["clima", "tempo", "weather", "temperatura"],
                        "calculator": ["calcule", "quanto é", "calculate", "math"],
                        "datetime": ["que horas", "que dia", "what time", "what date"]
                    }
                    
                    # Just log if user is likely asking for a tool (for debugging)
                    for tool, keywords in tool_keywords.items():
                        if any(keyword in transcript_lower for keyword in keywords):
                            self.logger.info(f"[TOOL_DETECTION] User likely asking for {tool} tool: '{transcript}'")
                            print(f"[TOOL_DETECTION] User likely asking for {tool} tool")
                            break
                    
                    # Check user speech for end phrases (is_user=True)
                    if self._check_end_phrases(transcript, is_user=True):
                        print(f"[SESSION] User goodbye detected in: '{transcript}'")
                        # Schedule session end after a brief delay to allow assistant's response
                        self._schedule_session_end(delay=5.0, reason="user_goodbye")
                    
                    # Reset goodbye flag if user continues conversation
                    elif self._user_said_goodbye and not any(word in transcript.lower() for word in ["tchau", "bye", "adeus"]):
                        print("[DEBUG] User continued conversation, resetting goodbye flag")
                        self._user_said_goodbye = False
                        
            elif event_type == "response.function_call_arguments.start":
                # Tool call starting
                call_id = event.get("call_id")
                tool_name = event.get("name")
                print(f"[FUNCTION_CALL] Starting function call: {tool_name} (call_id: {call_id})")
                self.logger.info(f"[FUNCTION_CALL] Model starting function call: {tool_name}")
                self.response_buffer[call_id] = {
                    "tool_name": tool_name,
                    "arguments": ""
                }
                
            elif event_type == "response.function_call_arguments.delta":
                # Tool call arguments chunk
                call_id = event.get("call_id")
                if call_id in self.response_buffer:
                    self.response_buffer[call_id]["arguments"] += event.get("delta", "")
                    
            elif event_type == "response.function_call_arguments.done":
                # Tool call complete
                call_id = event.get("call_id")
                if call_id in self.response_buffer:
                    tool_data = self.response_buffer[call_id]
                    print(f"[FUNCTION_CALL] Completing function call: {tool_data['tool_name']}")
                    self.logger.info(f"[FUNCTION_CALL] Function call complete, executing: {tool_data['tool_name']}")
                    self._execute_tool_async(call_id, tool_data["tool_name"], tool_data["arguments"])
                    del self.response_buffer[call_id]
                else:
                    # Try to get the function info from the event itself
                    print(f"[WARNING] Function call completed but call_id {call_id} not in buffer")
                    self.logger.warning(f"Function call completed but call_id {call_id} not in buffer")
                    
                    # Check if we can get the function details from response.done later
                    print(f"[DEBUG] Will check for function details in response.done event")
                    
            elif event_type == "error":
                error = event.get("error", {})
                error_type = error.get("type", "unknown")
                error_message = error.get("message", "No message")
                error_code = error.get("code", "No code")
                print(f"[ERROR] {error_message}")
                print(f"[ERROR_DETAILS] Type: {error_type}, Code: {error_code}")
                self.logger.error(f"Realtime API error - Type: {error_type}, Code: {error_code}, Message: {error_message}")
                
        except Exception as e:
            print(f"Error processing message: {e}")
            
    def _check_end_phrases(self, text: str, is_user: bool = True) -> bool:
        """Check if text contains session end phrases
        
        Args:
            text: Text to check
            is_user: True if this is user speech, False if assistant speech
        """
        import re
        
        text_lower = text.lower()
        
        # Debug logging
        print(f"[DEBUG] Checking end phrases in: '{text}' (is_user={is_user})")
        
        # First check for exact phrase matches (bot-directed)
        if any(phrase in text_lower for phrase in self.end_phrases):
            print(f"[DEBUG] Found exact phrase match")
            return True
            
        # Simple goodbye words (for natural conversation flow)
        simple_goodbyes = [
            "tchau", "tchauzinho", "até logo", "até mais", "adeus", 
            "falou", "valeu", "flw", "bye", "goodbye", "see you"
        ]
        
        # Check if this is a simple goodbye
        for goodbye in simple_goodbyes:
            # Use word boundaries to avoid false matches
            pattern = r"\b" + re.escape(goodbye) + r"\b"
            if re.search(pattern, text_lower):
                print(f"[DEBUG] Found simple goodbye: '{goodbye}'")
                if is_user:
                    # User said goodbye - mark it but don't end immediately
                    self._user_said_goodbye = True
                    print(f"[DEBUG] User initiated goodbye sequence")
                    return False  # Don't end immediately, wait for confirmation
                else:
                    # Assistant said goodbye - always treat as session ending
                    print(f"[DEBUG] Assistant said goodbye - ending session")
                    return True
            
        # Bot-directed goodbye patterns (immediate end)
        bot_goodbye_patterns = [
            r"\b(tchau|bye|adeus|até logo)\s+(bot|bote)\b",
            r"\b(obrigad[oa]|thanks?)\s+(bot|bote)\b",
            r"\b(valeu|falou)\s+(bot|bote)\b",
            r"\b(encerrar|terminar|end)\s+(conversa|conversation|sessão|session)\b"
        ]
        
        # Check for bot-directed goodbye patterns
        for pattern in bot_goodbye_patterns:
            if re.search(pattern, text_lower):
                print(f"[DEBUG] Found bot-directed goodbye pattern: '{pattern}'")
                return True
        
        print(f"[DEBUG] No session-ending phrase found")
        return False
        
    def _execute_tool_async(self, call_id: str, tool_name: str, arguments_json: str):
        """Execute a tool asynchronously using the tool execution manager"""
        def response_callback(response_data):
            """Send response back through WebSocket"""
            # Capture WebSocket reference to avoid race conditions
            ws_ref = self.ws
            if ws_ref and self.connected:
                try:
                    ws_ref.send(json.dumps(response_data))
                    # Trigger response generation after sending function output
                    ws_ref.send(json.dumps({"type": "response.create"}))
                    print(f"[FUNCTION_CALL] Function output sent for {tool_name} and response triggered")
                except websocket.WebSocketConnectionClosedException:
                    self.connected = False
                    self.logger.warning(f"WebSocket closed while sending tool response for {tool_name}")
                except Exception as e:
                    self.logger.error(f"Failed to send tool response: {e}", exc_info=True)
        
        # Create a new event loop for async execution
        def run_tool():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.tool_execution_manager.execute_tool(
                        call_id, tool_name, arguments_json, response_callback
                    )
                )
            except Exception as e:
                self.logger.error(f"Tool execution failed for {tool_name}: {e}", exc_info=True)
                # Try to send error response if still connected
                if self.connected:
                    try:
                        error_response = {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": f"Error executing {tool_name}: {str(e)}"
                            }
                        }
                        response_callback(error_response)
                    except Exception as send_err:
                        self.logger.error(f"Failed to send error response: {send_err}")
            finally:
                try:
                    loop.close()
                except Exception as close_err:
                    self.logger.error(f"Failed to close event loop: {close_err}")
        
        # Run in separate thread to avoid blocking
        threading.Thread(target=run_tool, daemon=True, name=f"ToolExecution-{tool_name}").start()
        
    def send_audio(self, audio_base64: str):
        """Send audio to the Realtime session"""
        if not self.session_active or not self.connected:
            return
            
        # Use local reference to avoid race conditions
        ws_ref = self.ws
        if ws_ref:
            message = {
                "type": "input_audio_buffer.append",
                "audio": audio_base64
            }
            try:
                ws_ref.send(json.dumps(message))
            except websocket.WebSocketConnectionClosedException:
                # Connection closed, mark as disconnected
                self.connected = False
                if self.session_active:
                    self.logger.debug("WebSocket connection closed while sending audio")
            except Exception as e:
                if self.session_active:  # Only log if we should be active
                    self.logger.error(f"Error sending audio: {e}")
                
    def send_text(self, text: str, out_of_band: bool = False, metadata: Optional[Dict[str, Any]] = None):
        """Send text message to the session
        
        Args:
            text: Text to send
            out_of_band: If True, response won't be added to conversation
            metadata: Optional metadata to identify the response
        """
        if self.ws and self.connected:
            message = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": text
                    }]
                }
            }
            
            try:
                self.ws.send(json.dumps(message))
                
                # Generate response with optional out-of-band configuration
                response_config = {"type": "response.create"}
                
                if out_of_band:
                    response_config["response"] = {
                        "conversation": "none",
                        "modalities": ["text", "audio"]
                    }
                    
                if metadata:
                    if "response" not in response_config:
                        response_config["response"] = {}
                    response_config["response"]["metadata"] = metadata
                
                self.ws.send(json.dumps(response_config))
                
            except Exception as e:
                print(f"Error sending text: {e}")
                
    def create_response(self, 
                       input_items: Optional[List[Dict[str, Any]]] = None,
                       conversation: str = "default",
                       instructions: Optional[str] = None,
                       modalities: Optional[List[str]] = None,
                       metadata: Optional[Dict[str, Any]] = None):
        """Create a custom response with flexible configuration
        
        Args:
            input_items: Custom input array for the response (None = use default conversation)
            conversation: "default" or "none" (out-of-band response)
            instructions: Custom instructions for this response
            modalities: List of modalities ["text", "audio"]
            metadata: Metadata to identify the response
        """
        if not self.ws or not self.connected:
            print("Not connected to Realtime session")
            return
            
        response_config = {"type": "response.create"}
        response_data = {}
        
        if conversation == "none":
            response_data["conversation"] = "none"
            
        if input_items is not None:
            response_data["input"] = input_items
            
        if instructions:
            response_data["instructions"] = instructions
            
        if modalities:
            response_data["modalities"] = modalities
        else:
            # Default to both audio and text if not specified
            response_data["modalities"] = ["audio", "text"]
            
        if metadata:
            response_data["metadata"] = metadata
            
        if response_data:
            response_config["response"] = response_data
            
        try:
            self.ws.send(json.dumps(response_config))
            print(f"Created custom response: {response_config}")
        except Exception as e:
            print(f"Error creating response: {e}")
                
    def _run_websocket(self):
        """Run the WebSocket connection with error handling"""
        try:
            print("[REALTIME] Starting WebSocket connection...")
            self.ws.run_forever()
        except Exception as e:
            self._connection_error = str(e)
            print(f"[REALTIME ERROR] WebSocket run_forever failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        self._connection_error = str(error)
        print(f"[REALTIME ERROR] WebSocket error: {error}")
        print(f"[REALTIME ERROR] Error type: {type(error).__name__}")
        import traceback
        if hasattr(error, '__traceback__'):
            print("[REALTIME ERROR] Traceback:")
            traceback.print_tb(error.__traceback__)
        
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        print(f"[REALTIME] WebSocket closed (Code: {close_status_code}, Message: {close_msg})")
        self.connected = False
        # IMPORTANT: Don't set session_active to False or call on_session_end here
        # This prevents premature session ends and VoiceOrb disappearing
        # Session should only end via:
        # 1. User/assistant goodbye detection
        # 2. Explicit end_session() call
        # NOT from WebSocket disconnections
        
        # Log the unexpected close if session is still active
        if self.session_active:
            print(f"[REALTIME WARNING] WebSocket closed while session {self.session_id} still active")
            # Attempt to reconnect if session should still be active
            self._attempt_reconnect()
            
    def _schedule_session_end(self, delay: float, reason: str):
        """Schedule session end with race condition prevention"""
        if self.session_ending:
            print(f"[SESSION] Session already ending, ignoring {reason} end request")
            return
            
        if not self.session_active:
            print(f"[SESSION] Session not active, ignoring {reason} end request")
            return
            
        print(f"[SESSION] Scheduling session end in {delay}s (reason: {reason}) - session_id: {self.session_id}")
        
        # Cancel any existing end timer
        if self._session_end_timer:
            self._session_end_timer.cancel()
            
        # Mark as ending to prevent race conditions
        self.session_ending = True
        self._session_end_reason = reason  # Store the reason
        
        # Schedule the actual end
        self._session_end_timer = threading.Timer(delay, self._execute_session_end)
        self._session_end_timer.start()
        
    def _execute_session_end(self):
        """Execute the actual session end after delay"""
        if not self.session_active:
            print(f"[SESSION] Session already ended, skipping execution - session_id: {self.session_id}")
            return
            
        print(f"[SESSION] Executing scheduled session end - session_id: {self.session_id}")
        # The reason was already set in _schedule_session_end
        self.end_session()
        
    def end_session(self, reason: str = None):
        """End the current session"""
        if not self.session_active:
            return
            
        # Set reason if not already set
        if reason:
            self._session_end_reason = reason
        elif not hasattr(self, '_session_end_reason'):
            self._session_end_reason = 'manual_end'
            
        print(f"[SESSION] Ending Realtime session - session_id: {self.session_id}, reason: {self._session_end_reason}")
        
        # Mark as ending to prevent concurrent calls
        self.session_ending = True
        
        # Mark as inactive first
        self.session_active = False
        self.connected = False
        
        # Cancel any pending timers
        if self._session_end_timer:
            self._session_end_timer.cancel()
            self._session_end_timer = None
            
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        
        # Close WebSocket safely
        if self.ws:
            try:
                # Check if WebSocket is still open before closing
                if hasattr(self.ws, 'sock') and self.ws.sock:
                    self.ws.close()
            except Exception as e:
                self.logger.debug(f"Error closing Realtime WebSocket: {e}")
            finally:
                self.ws = None
        
        # Wait for WebSocket thread to finish
        if hasattr(self, 'ws_thread') and self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)
            if self.ws_thread.is_alive():
                print("Warning: Realtime WebSocket thread did not terminate")
            
        # Print session stats
        if self.session_start_time:
            duration = time.time() - self.session_start_time
            print(f"Session duration: {duration:.1f}s")
            print(f"Messages sent: {self.messages_sent}")
            print(f"Messages received: {self.messages_received}")
            
            # Emit session end event with reason
            reason = getattr(self, '_session_end_reason', 'unknown')
            print(f"[SESSION] Emitting ASSISTANT_SESSION_END event for session {self.session_id} (duration: {duration:.1f}s, reason: {reason})")
            event_bus.emit(EventTypes.ASSISTANT_SESSION_END, {
                "session_id": self.session_id,
                "duration_seconds": duration,
                "messages_sent": self.messages_sent,
                "messages_received": self.messages_received,
                "reason": reason  # Include the reason in the event
            }, source="RealtimeSessionManager")
            
        # Call the session end callback if provided
        if self.on_session_end:
            print("[SESSION] Calling on_session_end callback")
            self.on_session_end()
            
    def is_active(self) -> bool:
        """Check if session is active"""
        return self.session_active
        
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        stats = {
            "active": self.session_active,
            "connected": self.connected,
            "session_id": self.session_id,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "tools_registered": len(self.tool_registry.get_all())
        }
        
        if self.session_start_time and self.session_active:
            stats["duration_seconds"] = time.time() - self.session_start_time
            
        return stats
        
    def _resume_audio_input(self):
        """Resume audio input after assistant finishes speaking"""
        print(f"[DEBUG] _resume_audio_input called - audio_handler: {self.audio_handler is not None}, assistant_speaking: {self.assistant_speaking}")
        
        # Start a monitoring thread to check when it's safe to resume
        def monitor_and_resume():
            # Get echo prevention settings from config
            echo_config = AUDIO_DEVICE_CONFIG.get("speaker_echo_delay", {})
            max_wait_time = echo_config.get("max_wait_time", 10.0)
            check_interval = echo_config.get("check_interval", 0.2)
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                elapsed = time.time() - start_time
                if self.audio_handler and not self.assistant_speaking:
                    # Check if it's safe to resume
                    if hasattr(self.audio_handler, 'is_safe_to_resume_input'):
                        is_safe = self.audio_handler.is_safe_to_resume_input()
                        
                        # Get detailed audio state for debugging
                        audio_state = {}
                        if hasattr(self.audio_handler, 'audio_output_manager') and self.audio_handler.audio_output_manager:
                            audio_state['is_playing'] = self.audio_handler.audio_output_manager.is_playing()
                            audio_state['buffer_duration'] = self.audio_handler.audio_output_manager.get_buffer_duration()
                            audio_state['is_actually_playing'] = self.audio_handler.audio_output_manager.is_actually_playing
                        
                        if hasattr(self.audio_handler, '_last_audio_time'):
                            audio_state['time_since_last_audio'] = time.time() - self.audio_handler._last_audio_time
                        
                        print(f"[DEBUG] Resume check at {elapsed:.1f}s - safe: {is_safe}, audio_state: {audio_state}")
                        
                        if is_safe:
                            # Safe to resume
                            if hasattr(self.audio_handler, 'input_paused') and self.audio_handler.input_paused:
                                try:
                                    print("[DEBUG] Safe to resume - calling resume_input()")
                                    self.audio_handler.resume_input()
                                    print("[DEBUG] resume_input() called successfully")
                                    return
                                except Exception as e:
                                    print(f"[ERROR] Failed to resume input: {e}")
                                    return
                            else:
                                print("[DEBUG] Input is not paused, nothing to resume")
                                return
                    else:
                        # Fallback to old behavior if method doesn't exist
                        print("[DEBUG] Fallback: waiting 2.5s before resume")
                        time.sleep(2.5)
                        if hasattr(self.audio_handler, 'input_paused') and self.audio_handler.input_paused:
                            try:
                                self.audio_handler.resume_input()
                                print("[DEBUG] resume_input() called successfully (fallback)")
                            except Exception as e:
                                print(f"[ERROR] Failed to resume input: {e}")
                        return
                else:
                    print(f"[DEBUG] Cannot resume - conditions not met")
                    return
                
                time.sleep(check_interval)
            
            print(f"[WARNING] Timeout waiting for safe resume conditions after {max_wait_time}s")
            print(f"[WARNING] Final state - assistant_speaking: {self.assistant_speaking}")
            
            # Check the actual audio output state
            if self.audio_handler and hasattr(self.audio_handler, 'audio_output_manager'):
                if self.audio_handler.audio_output_manager:
                    is_playing = self.audio_handler.audio_output_manager.is_playing()
                    buffer_duration = self.audio_handler.audio_output_manager.get_buffer_duration()
                    print(f"[WARNING] Audio output state - is_playing: {is_playing}, buffer_duration: {buffer_duration:.2f}s")
            
            # Force resume after timeout
            if self.audio_handler and hasattr(self.audio_handler, 'input_paused') and self.audio_handler.input_paused:
                try:
                    self.audio_handler.resume_input()
                    print("[DEBUG] Forced resume after timeout - microphone should now be active")
                except Exception as e:
                    print(f"[ERROR] Failed to force resume: {e}")
        
        # Start monitoring in a separate thread
        threading.Thread(target=monitor_and_resume, daemon=True, name="AudioResumeMonitor").start()
        
    def _check_goodbye_timeout(self):
        """Check if session should end after goodbye timeout"""
        if self._user_said_goodbye and not self.session_ending:
            print(f"[SESSION] Goodbye timeout reached after 60s - session_id: {self.session_id}")
            # Only end if user really meant to say goodbye and hasn't continued talking
            self._schedule_session_end(delay=0.1, reason="goodbye_timeout")
    
    def _start_heartbeat(self):
        """Start heartbeat to keep connection alive"""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
        self._last_pong_time = time.time()
        self._schedule_next_heartbeat()
    
    def _schedule_next_heartbeat(self):
        """Schedule the next heartbeat"""
        if self.connected and self.session_active:
            self._heartbeat_timer = threading.Timer(self._heartbeat_interval, self._send_heartbeat)
            self._heartbeat_timer.daemon = True
            self._heartbeat_timer.start()
    
    def _send_heartbeat(self):
        """Send heartbeat ping to keep connection alive"""
        if not self.connected or not self.session_active:
            return
            
        try:
            # Check if we've received a response recently
            if self._last_pong_time and time.time() - self._last_pong_time > 90:
                print(f"[REALTIME WARNING] No response for {time.time() - self._last_pong_time:.0f}s, connection may be stale")
                # Attempt reconnect
                self._attempt_reconnect()
                return
            
            # Send a minimal message to keep connection alive
            if self.ws:
                # OpenAI Realtime API doesn't have a specific ping, so we'll send a minimal update
                heartbeat_msg = {
                    "type": "input_audio_buffer.clear"  # Minimal message that doesn't affect state
                }
                self.ws.send(json.dumps(heartbeat_msg))
                print(f"[HEARTBEAT] Sent heartbeat at {time.strftime('%H:%M:%S')}")
            
            # Schedule next heartbeat
            self._schedule_next_heartbeat()
            
        except Exception as e:
            print(f"[HEARTBEAT ERROR] Failed to send heartbeat: {e}")
            # Connection likely lost, attempt reconnect
            self.connected = False
            self._attempt_reconnect()
    
    def _stop_heartbeat(self):
        """Stop heartbeat timer"""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None
    
    def _attempt_reconnect(self):
        """Attempt to reconnect WebSocket if session is still active"""
        if not self.session_active:
            print("[REALTIME] Session not active, skipping reconnect")
            return
            
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            print(f"[REALTIME ERROR] Max reconnect attempts ({self._max_reconnect_attempts}) reached")
            # Don't end session on reconnect failures - keep trying or wait for goodbye
            print(f"[REALTIME] Session {self.session_id} will remain active despite connection issues")
            # Try one more time after a longer delay
            delay = 30.0
            print(f"[REALTIME] Will retry in {delay}s...")
            self._reconnect_timer = threading.Timer(delay, self._execute_reconnect)
            self._reconnect_timer.start()
            return
            
        self._reconnect_attempts += 1
        print(f"[REALTIME] Attempting reconnect {self._reconnect_attempts}/{self._max_reconnect_attempts}...")
        
        # Schedule reconnect with exponential backoff
        delay = min(2.0 * self._reconnect_attempts, 10.0)
        self._reconnect_timer = threading.Timer(delay, self._execute_reconnect)
        self._reconnect_timer.start()
        
    def _execute_reconnect(self):
        """Execute the reconnection attempt"""
        if not self.session_active:
            print("[REALTIME] Session no longer active, skipping reconnect")
            return
            
        try:
            # Attempt to reconnect with existing session parameters
            print("[REALTIME] Reconnecting WebSocket...")
            
            # Create new WebSocket connection
            url = f"wss://api.openai.com/v1/realtime?model={self.model}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self.ws = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=self._on_reconnect_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket in separate thread
            ws_thread = threading.Thread(target=self._run_websocket, daemon=True, name="RealtimeReconnectThread")
            ws_thread.start()
            
            # Wait briefly for connection
            time.sleep(2.0)
            
            if self.connected:
                print("[REALTIME] Reconnection successful!")
                self._reconnect_attempts = 0  # Reset counter on success
            else:
                print("[REALTIME] Reconnection failed")
                self._attempt_reconnect()  # Try again
                
        except Exception as e:
            print(f"[REALTIME ERROR] Reconnection error: {e}")
            self._attempt_reconnect()  # Try again
            
    def _on_reconnect_open(self, ws):
        """Handle reconnected WebSocket open"""
        print("[REALTIME] Reconnected to OpenAI Realtime API")
        self.connected = True
        
        # Re-configure session with same parameters
        vad_config = VAD_CONFIG.get(self.vad_mode, DEFAULT_CONVERSATION_VAD).copy()
        vad_config["create_response"] = True
        vad_config["interrupt_response"] = True
        
        session_config = {
            "type": "session.update",
            "session": {
                "model": self.model,
                "voice": self.voice,
                "instructions": """You are a helpful Portuguese-speaking AI assistant in a voice conversation.
                
Key behaviors:
- Respond naturally in Portuguese (Brazilian) unless the user speaks another language
- Keep responses concise and conversational for voice interaction
- Listen for phrases like "obrigado bot" or "tchau bot" to end the conversation
- Be helpful, friendly, and maintain context throughout the conversation

CRITICAL TOOL USAGE RULES:
- You MUST use tools when the user asks for information that requires them
- When a user asks you to search, check weather, do calculations, or get the time, you MUST call the appropriate tool
- Do NOT pretend to search or say you're searching without actually calling the search tool
- Do NOT make up information - always use tools to get real data
- If a tool is needed, call it IMMEDIATELY - don't say you're going to do it, just do it

Examples of REQUIRED tool usage:
- "pesquise o preço de carros" → MUST call search tool with query "preço de carros"
- "qual é o clima hoje" → MUST call weather tool
- "que horas são" → MUST call datetime tool
- "quanto é 25 x 4" → MUST call calculator tool

When the user says goodbye or thanks you to end the conversation, acknowledge it politely and indicate the conversation is ending.""",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": vad_config,
                "tools": self.tool_execution_manager.get_tool_schemas(),
                "temperature": 0.6,  # Lower temperature for more consistent tool usage
                "tool_choice": "auto",  # Let the model decide when to use tools
                "modalities": ["audio", "text"]  # Always support both audio and text
            }
        }
        
        tool_schemas = self.tool_execution_manager.get_tool_schemas()
        print(f"[SESSION_CONFIG] Tools count: {len(tool_schemas)}")
        if tool_schemas:
            tool_names = [schema.get('name', 'unknown') for schema in tool_schemas]
            print(f"[SESSION_CONFIG] Registered tools: {tool_names}")
            # Debug: Print full schema for datetime tool
            for schema in tool_schemas:
                if schema.get('name') == 'datetime':
                    print(f"[DEBUG] DateTime tool schema: {json.dumps(schema, indent=2)}")
        print(f"[SESSION_CONFIG] Temperature: 0.6, Tool choice: auto, Modalities: audio+text")
        
        # Debug: Print the full session config being sent
        print(f"[DEBUG] Full session config tools: {json.dumps(session_config['session']['tools'][:1], indent=2)}...")
        
        ws.send(json.dumps(session_config))
        print("[REALTIME] Session reconfigured after reconnect")
        
        
    
    def shutdown(self):
        """Shutdown the session manager"""
        # Cancel any pending timers
        if self._goodbye_timer:
            self._goodbye_timer.cancel()
            self._goodbye_timer = None
            
        if self._session_end_timer:
            self._session_end_timer.cancel()
            self._session_end_timer = None
            
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
            
        # Stop heartbeat
        self._stop_heartbeat()
            
        if self.session_active:
            self.end_session()