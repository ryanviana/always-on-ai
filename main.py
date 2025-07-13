#!/usr/bin/env python3
"""
Main application - Orchestrates audio stream and transcription with VAD and trigger checking
"""

import signal
import sys
import threading
import time
from audio.audio_stream import AudioStreamManager
from transcription.simple_transcriber import RealtimeTranscriber
from config import (
    DISPLAY_CONFIG, TRIGGER_CONFIG, CONVERSATION_CONFIG,
    CONTEXT_CONFIG, ASSISTANT_CONFIG, TTS_CONFIG, AUDIO_DEVICE_CONFIG, LOGGING_CONFIG, REALTIME_CONFIG
)
from core.logging_config import setup_logging, get_logger
from core.config_validator import validate_startup_config, ConfigValidationError
from triggers import TriggerManager
from triggers.builtin import TestTrigger, AssistantTrigger, RevenueVerificationTrigger
from context import EnhancedContextManager, ContextPersistence, setup_context_access
from context.persistence import AutoSaveContextManager
from core import ConnectionCoordinator, StateManager, AppState
from realtime import RealtimeSessionManager, RealtimeAudioHandler
from realtime.tools import ToolRegistry, ToolLoader, DateTimeTool
from tts import OpenAITTSService, AudioOutputManager
from audio import AudioDeviceDetector


class VoiceAssistant:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.audio_manager = AudioStreamManager()
        
        # Initialize device detector for smart feedback prevention
        self.device_detector = AudioDeviceDetector(AUDIO_DEVICE_CONFIG)
        
        # Initialize state manager
        self.state_manager = StateManager()
        
        # Initialize context management
        self.context_manager = None
        self.auto_save_manager = None
        self.context_access = None
        if CONTEXT_CONFIG.get("enabled", True):
            self.context_manager = self._setup_context_manager()
            
            # Setup context access servers (WebSocket + HTTP)
            if self.context_manager:
                try:
                    self.context_access = setup_context_access(self.context_manager)
                except Exception as e:
                    self.logger.warning("Could not start context access servers", exc_info=True, extra={"extra_data": {"error": str(e)}})
            
        # Initialize connection coordinator
        self.connection_coordinator = ConnectionCoordinator(
            audio_manager=self.audio_manager,
            context_manager=self.context_manager,
            on_mode_change=self._handle_mode_change
        )
        
        # Initialize TTS if enabled
        self.tts_service = None
        self.audio_output = None
        if TTS_CONFIG.get("enabled", True):
            self._setup_tts()

        # Initialize trigger system if enabled
        self.trigger_manager = None
        if TRIGGER_CONFIG.get("enabled", False):
            self.trigger_manager = self._setup_triggers()

        # Initialize transcriber
        self.transcriber = RealtimeTranscriber(
            trigger_manager=self.trigger_manager,
            speech_started_callback=None,
            speech_stopped_callback=None,
            use_conversation_manager=CONVERSATION_CONFIG.get("enabled", True),
        )
        
        # Set transcriber in connection coordinator
        self.connection_coordinator.set_transcriber(self.transcriber)
        
        # Initialize Realtime components
        self.realtime_session = None
        self.realtime_audio = None
        self.tool_registry = None
        if ASSISTANT_CONFIG.get("enabled", True):
            self._setup_realtime_components()
            
        self.running = False
        
    def _setup_context_manager(self):
        """Setup context management with persistence"""
        colors = DISPLAY_CONFIG["colors"]
        
        self.logger.info("Initializing context management")
        
        # Create context manager
        context_manager = EnhancedContextManager(
            window_minutes=CONTEXT_CONFIG.get("raw_window_minutes", 5),
            summary_model=CONTEXT_CONFIG.get("summarization_model", "gpt-4.1-nano"),
            summary_interval_seconds=CONTEXT_CONFIG.get("summarization_interval", 60)
        )
        
        # Wrap with persistence if enabled
        if CONTEXT_CONFIG.get("persistence", {}).get("enabled", True):
            persistence = ContextPersistence(
                storage_dir=CONTEXT_CONFIG.get("persistence", {}).get("directory", "./context"),
                max_files=CONTEXT_CONFIG.get("persistence", {}).get("max_file_size_mb", 10)
            )
            
            self.auto_save_manager = AutoSaveContextManager(
                context_manager=context_manager,
                persistence=persistence,
                save_interval=CONTEXT_CONFIG.get("persistence_interval", 60)
            )
            
            return context_manager
        
        return context_manager
    
    def _setup_tts(self):
        """Setup TTS services"""
        colors = DISPLAY_CONFIG["colors"]
        
        self.logger.info("Initializing TTS services")
        
        # Create audio output manager
        self.audio_output = AudioOutputManager()
        
        # Create TTS service
        self.tts_service = OpenAITTSService()
        self.tts_service.connect()
        
    def _setup_realtime_components(self):
        """Setup Realtime API components"""
        colors = DISPLAY_CONFIG["colors"]
        
        self.logger.info("Initializing Realtime components")
        
        # Create tool registry using auto-discovery
        tool_loader = ToolLoader(logger=self.logger)
        tool_config = {
            "enabled_tools": ASSISTANT_CONFIG.get("tools_enabled", []),
            "tool_configs": ASSISTANT_CONFIG.get("tool_configs", {})
        }
        
        # Load tools from configuration
        self.tool_registry = tool_loader.load_tools_from_config(tool_config)
        self.logger.info(f"Auto-loaded {len(self.tool_registry.get_all())} tools")
        
        # Create Realtime session manager
        vad_mode = ASSISTANT_CONFIG.get("vad_mode", "server_vad")
        self.logger.info(f"Using VAD mode: {vad_mode} for assistant sessions")
        self.realtime_session = RealtimeSessionManager(
            audio_callback=self._handle_realtime_audio,
            on_session_end=self._handle_session_end,
            vad_mode=vad_mode
        )
        
        # Register tools with session
        for name, tool in self.tool_registry.get_all().items():
            self.realtime_session.register_tool(name, tool)
            
        # Set in connection coordinator
        self.connection_coordinator.set_realtime_session(self.realtime_session)
        
        # Create Realtime audio handler with device detection
        self.realtime_audio = RealtimeAudioHandler(
            audio_manager=self.audio_manager,
            audio_output_manager=self.audio_output,
            session_manager=self.realtime_session,
            device_detector=self.device_detector
        )
        
        # Connect audio handler to session manager for feedback prevention
        self.realtime_session.audio_handler = self.realtime_audio
        self.logger.debug("Connected audio_handler to session_manager", extra={"extra_data": {"handler_type": type(self.realtime_audio).__name__, "handler_instance": str(self.realtime_audio)}})

    def _setup_triggers(self):
        """Setup and configure triggers"""
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]

        self.logger.info("Initializing trigger system")

        # Create trigger manager with TTS callback if available
        tts_callback = None
        if self.tts_service and self.audio_output:
            def tts_callback(text, voice_settings):
                # Define callbacks for TTS lifecycle
                def on_tts_start():
                    # Pause microphone when TTS starts to prevent feedback
                    self.logger.debug("TTS starting synthesis - pausing microphone")
                    self.audio_manager.pause_microphone()
                    
                def on_tts_complete():
                    # Wait for actual playback to complete
                    self.logger.debug("TTS synthesis complete - waiting for playback to finish")
                    if self.audio_output:
                        self.audio_output.wait_for_playback_complete(timeout=10.0, expected_text=text)
                    
                    # Add hardware latency delay
                    import time
                    hardware_delay = TTS_CONFIG.get("hardware_latency_delay", 0.2)
                    if hardware_delay > 0:
                        self.logger.debug(f"TTS adding {hardware_delay}s hardware latency delay")
                        time.sleep(hardware_delay)
                    
                    # Resume microphone after playback is truly complete
                    self.logger.debug("TTS playback complete - resuming microphone")
                    self.audio_manager.resume_microphone()
                
                try:
                    # Synthesize with lifecycle callbacks
                    self.tts_service.synthesize(
                        text=text,
                        callback=self.audio_output.play_audio,
                        on_start=on_tts_start,
                        on_complete=on_tts_complete,
                        voice=voice_settings.get("voice"),
                        speed=voice_settings.get("speed")
                    )
                except Exception as e:
                    # Ensure microphone is resumed even if TTS fails
                    self.logger.error(f"TTS error during synthesis: {e}", exc_info=True)
                    if self.audio_manager.is_microphone_paused():
                        self.logger.debug("TTS resuming microphone after error")
                        self.audio_manager.resume_microphone()
                
        trigger_manager = TriggerManager(
            buffer_duration=TRIGGER_CONFIG.get("buffer_duration_seconds", 60),
            llm_model=TRIGGER_CONFIG.get("llm_model", "gpt-4o-mini"),
            tts_callback=tts_callback,
            validation_timeout=TRIGGER_CONFIG.get("validation_timeout", 8.0)
        )

        # Add enabled triggers
        enabled_triggers = TRIGGER_CONFIG.get("enabled_triggers", [])

        if "assistant" in enabled_triggers:
            trigger_manager.add_trigger(AssistantTrigger())

        if "test" in enabled_triggers:
            trigger_manager.add_trigger(TestTrigger())

        if "revenue_verification" in enabled_triggers:
            trigger_manager.add_trigger(RevenueVerificationTrigger())

        self.logger.info(f"Loaded {len(trigger_manager.get_triggers())} triggers")
        return trigger_manager

    def _handle_mode_change(self, new_mode):
        """Handle connection mode changes"""
        colors = DISPLAY_CONFIG["colors"]
        
        # Update state manager
        from core.connection_coordinator import ConnectionMode
        if new_mode == ConnectionMode.ASSISTANT:
            self.state_manager.transition_to(AppState.ASSISTANT_ACTIVE, "Assistant mode started")
        elif new_mode == ConnectionMode.TRANSCRIPTION:
            # Check current state to determine proper transition
            current_state = self.state_manager.get_state()
            if current_state == AppState.ASSISTANT_ACTIVE:
                # First transition to closing state
                self.state_manager.transition_to(AppState.ASSISTANT_CLOSING, "Ending assistant mode")
            # Then transition to listening
            self.state_manager.transition_to(AppState.LISTENING, "Returned to transcription mode")
            
    def _handle_realtime_audio(self, audio_data: bytes):
        """Handle audio output from Realtime session"""
        if self.audio_output:
            self.audio_output.play_audio(audio_data)
            
    def _handle_session_end(self):
        """Handle Realtime session end"""
        colors = DISPLAY_CONFIG["colors"]
        self.logger.info("Assistant session ended, returning to transcription mode")
        
        # Stop audio handler
        if self.realtime_audio:
            self.realtime_audio.stop()
        
        # End assistant mode
        if self.connection_coordinator.end_assistant_mode():
            self.logger.info("Ready for triggers again! Say 'Hey Bot' or 'Fala Bot' to start assistant mode")
        
    def _handle_assistant_trigger(self):
        """Handle assistant trigger activation"""
        colors = DISPLAY_CONFIG["colors"]
        
        # Check if already in assistant mode
        from core.connection_coordinator import ConnectionMode
        if self.connection_coordinator.get_current_mode() == ConnectionMode.ASSISTANT:
            self.logger.info("Already in assistant mode")
            return
            
        self.logger.info("Starting assistant mode")
        
        # Update state
        self.state_manager.transition_to(AppState.ASSISTANT_ACTIVATING, "Assistant trigger activated")
        
        # Start assistant mode (this starts the session)
        if self.connection_coordinator.start_assistant_mode():
            # Start audio handler AFTER session is ready
            if self.realtime_audio:
                self.realtime_audio.start()
            self.logger.info("Assistant mode started successfully")
        else:
            self.logger.error("Failed to start assistant mode")
            self.state_manager.transition_to(AppState.LISTENING, "Assistant mode failed")

    def start(self):
        """Start the voice assistant"""
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]

        self.logger.info("Starting Enhanced Voice Assistant")
        
        # Transition to listening state
        self.state_manager.transition_to(AppState.LISTENING, "System started")
        
        # Start context management
        if self.context_manager:
            self.context_manager.start()
            if self.auto_save_manager:
                self.auto_save_manager.start()
                
        # Start audio output if available
        if self.audio_output:
            self.audio_output.start()

        # Register transcriber as audio consumer
        self.audio_manager.add_consumer(self.transcriber.send_audio)

        # Start audio stream
        self.audio_manager.start()

        # Track threads for proper cleanup
        self.threads = []
        
        # Start transcriber in separate thread
        transcriber_thread = threading.Thread(target=self.transcriber.connect, name="TranscriberThread")
        transcriber_thread.daemon = True
        transcriber_thread.start()
        self.threads.append(transcriber_thread)
        
        # Wait for transcriber to connect with timeout
        connection_timeout = REALTIME_CONFIG.get("connection_timeout", 20.0)
        start_time = time.time()
        while time.time() - start_time < connection_timeout:
            if hasattr(self.transcriber, 'connected') and self.transcriber.connected:
                break
            time.sleep(0.1)
        else:
            self.logger.warning("Transcriber connection timeout")
            
        self.connection_coordinator.initialize_transcription_mode()
        
        # Update trigger manager to handle assistant trigger specially
        if self.trigger_manager:
            # Store original methods
            self._original_execute = self.trigger_manager._execute_trigger
            self._original_process = self.trigger_manager.process_transcription
            
            # Create wrapper methods with proper references
            def custom_execute(trigger, validation_result):
                # Check if this is an assistant trigger
                response = trigger.action(validation_result)
                if response and response.get("action") == "start_assistant":
                    # Handle assistant activation
                    self._handle_assistant_trigger()
                else:
                    # Normal trigger execution
                    self._original_execute(trigger, validation_result)
                    
            def custom_process(text):
                # Add to context manager first
                if self.context_manager:
                    try:
                        self.context_manager.add_transcription(text)
                    except Exception as e:
                        self.logger.error(f"Error adding to context: {e}", exc_info=True)
                    
                # Then process triggers
                self._original_process(text)
                
            # Replace methods
            self.trigger_manager._execute_trigger = custom_execute
            self.trigger_manager.process_transcription = custom_process

        self.running = True
        
        # Print status
        self.logger.info("System ready", extra={"extra_data": {
            "context_management": bool(self.context_manager),
            "tts_service": bool(self.tts_service),
            "assistant_mode": bool(self.realtime_session),
            "triggers_count": len(self.trigger_manager.get_triggers()) if self.trigger_manager else 0
        }})
        self.logger.info("Say 'Hey Bot' or 'Fala Bot' to start assistant mode")

        # Keep main thread alive with periodic state broadcasts
        last_state_broadcast = 0
        
        try:
            while self.running:
                transcriber_thread.join(timeout=1.0)
                if not transcriber_thread.is_alive():
                    break
                    
                # Broadcast microphone state every 30 seconds for dashboard sync
                import time as time_module
                current_time = time_module.time()
                if current_time - last_state_broadcast > 30:
                    if self.audio_manager:
                        self.audio_manager.broadcast_microphone_state()
                    last_state_broadcast = current_time
                    
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the voice assistant"""
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]

        self.logger.info("Stopping voice assistant")

        self.running = False
        
        # Transition to shutdown state
        self.state_manager.transition_to(AppState.SHUTTING_DOWN, "User requested shutdown")

        # First remove audio consumer to prevent new audio from being sent
        try:
            self.audio_manager.remove_consumer(self.transcriber.send_audio)
        except Exception as e:
            self.logger.error(f"Error removing transcriber consumer: {e}", exc_info=True)

        # Stop realtime components if active
        if self.realtime_audio and self.realtime_audio.is_active():
            try:
                self.realtime_audio.stop()
            except Exception as e:
                self.logger.error(f"Error stopping realtime audio: {e}", exc_info=True)
            
        if self.realtime_session and self.realtime_session.is_active():
            try:
                self.realtime_session.end_session()
            except Exception as e:
                self.logger.error(f"Error ending realtime session: {e}", exc_info=True)

        # Shutdown connection coordinator (handles transcriber stop)
        try:
            self.connection_coordinator.shutdown()
        except Exception as e:
            self.logger.error(f"Error shutting down connection coordinator: {e}", exc_info=True)

        # Stop trigger manager
        if self.trigger_manager:
            try:
                self.trigger_manager.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down trigger manager: {e}", exc_info=True)
            
        # Stop context management
        if self.context_manager:
            try:
                self.context_manager.stop()
            except Exception as e:
                self.logger.error(f"Error stopping context manager: {e}", exc_info=True)
                
            if self.auto_save_manager:
                try:
                    self.auto_save_manager.stop()
                except Exception as e:
                    self.logger.error(f"Error stopping auto save manager: {e}", exc_info=True)
                    
        # Stop context access servers
        if self.context_access:
            try:
                self.context_access.stop()
            except Exception as e:
                self.logger.error(f"Error stopping context access servers: {e}", exc_info=True)

        # Stop audio components
        if self.audio_output:
            try:
                self.audio_output.stop()
            except Exception as e:
                self.logger.error(f"Error stopping audio output: {e}", exc_info=True)
            
        if self.tts_service:
            # TTS service doesn't have a stop method in current implementation
            pass

        # Finally stop audio stream after everything else
        try:
            self.audio_manager.stop()
        except Exception as e:
            self.logger.error(f"Error stopping audio manager: {e}", exc_info=True)
        
        # Wait for threads to finish
        if hasattr(self, 'threads'):
            for thread in self.threads:
                if thread.is_alive():
                    thread.join(timeout=2.0)
                    if thread.is_alive():
                        self.logger.warning(f"Thread {thread.name} did not terminate")

        self.logger.info("Voice assistant stopped")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global assistant
    try:
        print("\n\nShutting down gracefully...")
        assistant.stop()
    except Exception as e:
        print(f"Error during shutdown: {e}")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    # Validate configuration first (before logging setup)
    try:
        validate_startup_config()
    except ConfigValidationError as e:
        print(f"❌ Configuration validation failed: {e}")
        print("Please fix the configuration errors and try again.")
        sys.exit(1)
    
    # Setup logging system
    setup_logging(LOGGING_CONFIG)
    logger = get_logger(__name__)
    logger.info("Starting Voice Assistant application")
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Create and start voice assistant
    assistant = VoiceAssistant()

    try:
        assistant.start()
    except Exception as e:
        logger.error("Failed to start Voice Assistant", exc_info=True, extra={
            "extra_data": {"error_type": type(e).__name__, "error_message": str(e)}
        })
        assistant.stop()