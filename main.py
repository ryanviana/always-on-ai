#!/usr/bin/env python3
"""
Main application - Real-time transcription only
"""

import signal
import sys
import threading
import time
from audio_stream import AudioStreamManager
from transcription.simple_transcriber import RealtimeTranscriber
from config import (
    DISPLAY_CONFIG, CONVERSATION_CONFIG, CONTEXT_CONFIG, LOGGING_CONFIG, CONNECTION_TIMEOUT,
    TRIGGER_CONFIG, TTS_CONFIG
)
from logging_config import setup_logging, get_logger
from context import EnhancedContextManager, ContextPersistence, setup_context_access, MeetingSessionManager
from datetime import datetime
from triggers import TriggerManager


class VoiceTranscriber:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.audio_manager = AudioStreamManager()
        
        # Initialize TTS if enabled
        self.tts_service = None
        self.audio_output = None
        if TTS_CONFIG.get("enabled", False):
            self._setup_tts()
        
        # Initialize trigger system
        self.trigger_manager = None
        if TRIGGER_CONFIG.get("enabled", False):
            self.trigger_manager = self._setup_triggers()
        
        # Initialize context management
        self.context_manager = None
        self.meeting_session_manager = None
        self.context_access = None
        if CONTEXT_CONFIG.get("enabled", True):
            self.context_manager = self._setup_context_manager()
            
            # Setup context access servers (WebSocket + HTTP)
            if self.context_manager:
                try:
                    self.context_access = setup_context_access(self.context_manager)
                except Exception as e:
                    self.logger.warning("Could not start context access servers", exc_info=True, extra={"extra_data": {"error": str(e)}})
        
        # Initialize transcriber with context and trigger support
        self.transcriber = RealtimeTranscriber(
            trigger_manager=self.trigger_manager,
            speech_started_callback=None,
            speech_stopped_callback=None,
            use_conversation_manager=CONVERSATION_CONFIG.get("enabled", False),
        )
        
        # Hook conversation manager to context manager
        if self.context_manager:
            if hasattr(self.transcriber, 'conversation_manager') and self.transcriber.conversation_manager:
                # Store original callback
                original_callback = self.transcriber.conversation_manager.on_complete_callback
                
                # Create new callback that adds to context
                def context_aware_callback(merged_text: str):
                    # Add to context manager
                    self.context_manager.add_transcription(merged_text, speaker="user")
                    print(f"📝 Added to context: {merged_text}")
                    
                    # Call original callback if it exists
                    if original_callback:
                        original_callback(merged_text)
                        
                # Replace the callback
                self.transcriber.conversation_manager.on_complete_callback = context_aware_callback
            else:
                # If no conversation manager, hook directly to transcriber
                self.logger.info("No conversation manager found, hooking directly to transcriber")
                
                # Create a callback for final transcriptions
                def add_to_context(text: str):
                    self.context_manager.add_transcription(text, speaker="user")
                    print(f"📝 Added to context: {text}")
                
                # Hook into the transcriber's message processing
                if hasattr(self.transcriber, 'on_message'):
                    original_on_message = self.transcriber.on_message
                    
                    def hooked_on_message(ws, message):
                        result = original_on_message(ws, message)
                        
                        # Check for completed transcriptions
                        try:
                            import json
                            event = json.loads(message)
                            if event.get("type") == "conversation.item.input_audio_transcription.completed":
                                transcript = event.get("transcript", "")
                                if transcript and not self.transcriber.paused:
                                    add_to_context(transcript)
                        except:
                            pass
                            
                        return result
                    
                    self.transcriber.on_message = hooked_on_message
        
        self.running = False
        
    def _setup_context_manager(self):
        """Setup context management with meeting session persistence"""
        colors = DISPLAY_CONFIG["colors"]
        
        self.logger.info("Initializing meeting-based context management")
        
        # Create unique session ID for this meeting
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create context manager with session ID
        context_manager = EnhancedContextManager(
            window_minutes=CONTEXT_CONFIG.get("raw_window_minutes", 5),
            summary_model=CONTEXT_CONFIG.get("summarization_model", "gpt-4.1-nano"),
            summary_interval_seconds=CONTEXT_CONFIG.get("summarization_interval", 60),
            session_id=session_id
        )
        
        # Setup meeting session manager if persistence enabled
        if CONTEXT_CONFIG.get("persistence_enabled", True):
            persistence = ContextPersistence(
                storage_dir=CONTEXT_CONFIG.get("persistence_dir", "./context_storage"),
                max_files=CONTEXT_CONFIG.get("max_persistence_files", 10)
            )
            
            self.meeting_session_manager = MeetingSessionManager(
                context_manager=context_manager,
                persistence=persistence
            )
            
        return context_manager
        
    def _setup_tts(self):
        """Setup TTS services"""
        from tts import OpenAITTSService, AudioOutputManager
        
        self.logger.info("🔊 Initializing TTS services...")
        
        # Create audio output manager
        self.audio_output = AudioOutputManager()
        
        # Create TTS service
        self.tts_service = OpenAITTSService()
        self.tts_service.connect()
        
        self.logger.info("✅ TTS services ready")
        
    def _setup_triggers(self):
        """Setup trigger system with configured triggers"""
        from triggers.manager import TriggerManager
        from triggers.builtin import TestTrigger
        
        self.logger.info("🎯 Initializing proactive trigger system...")
        
        # Create TTS callback if TTS is available
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
                    if hasattr(self.audio_manager, 'is_microphone_paused') and self.audio_manager.is_microphone_paused():
                        self.logger.debug("TTS resuming microphone after error")
                        self.audio_manager.resume_microphone()
        
        # Create trigger manager
        trigger_manager = TriggerManager(
            buffer_duration=TRIGGER_CONFIG.get("buffer_duration_seconds", 60),
            llm_model=TRIGGER_CONFIG.get("llm_model", "gpt-4.1-nano"),
            tts_callback=tts_callback,
            validation_timeout=TRIGGER_CONFIG.get("validation_timeout", 8.0)
        )
        
        # Load enabled triggers
        enabled_triggers = TRIGGER_CONFIG.get("enabled_triggers", [])
        
        if "test" in enabled_triggers:
            trigger_manager.add_trigger(TestTrigger())
            self.logger.info("  ✅ TestTrigger loaded and ready")
            
        self.logger.info(f"✅ Trigger system ready with {len(trigger_manager.triggers)} triggers")
        self.logger.info(f"   LLM Model: {TRIGGER_CONFIG.get('llm_model', 'gpt-4.1-nano')}")
        self.logger.info(f"   Validation Timeout: {TRIGGER_CONFIG.get('validation_timeout', 8.0)}s")
        return trigger_manager
        
    def start(self):
        """Start the voice transcriber"""
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]

        self.logger.info("Starting Voice Transcriber")
        print(f"{colors['info']}{emojis['mic']} Starting real-time transcription...{colors['reset']}")

        # Start context management
        if self.context_manager:
            self.context_manager.start()
            if self.meeting_session_manager:
                self.meeting_session_manager.start()
                
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
        start_time = time.time()
        while time.time() - start_time < CONNECTION_TIMEOUT:
            if hasattr(self.transcriber, 'connected') and self.transcriber.connected:
                break
            time.sleep(0.1)
        else:
            self.logger.warning("Transcriber connection timeout")
            
        self.running = True
        
        # Print status
        self.logger.info("Transcription system ready", extra={"extra_data": {
            "context_management": bool(self.context_manager),
            "context_access_servers": bool(self.context_access)
        }})
        print(f"{colors['info']}{emojis['speaker']} Listening for speech... (Press Ctrl+C to stop){colors['reset']}")
        
        if self.context_manager:
            print(f"{colors['info']}🧠 Context management enabled with summarization{colors['reset']}")
        if self.context_access:
            print(f"{colors['info']}🌐 Context access servers running (HTTP + WebSocket){colors['reset']}")
        if self.trigger_manager:
            print(f"{colors['info']}🎯 Proactive triggers enabled ({len(self.trigger_manager.triggers)} triggers loaded){colors['reset']}")
            for trigger in self.trigger_manager.triggers:
                print(f"{colors['info']}   • {trigger.name} (priority: {trigger.priority}){colors['reset']}")
        if self.tts_service:
            print(f"{colors['info']}🔊 TTS enabled (voice: {TTS_CONFIG.get('voice', 'nova')}){colors['reset']}")

        try:
            while self.running:
                transcriber_thread.join(timeout=1.0)
                if not transcriber_thread.is_alive():
                    break
                    
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the voice transcriber"""
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]

        self.logger.info("Stopping voice transcriber")
        print(f"{colors['info']}{emojis['stop']} Stopping transcription...{colors['reset']}")

        self.running = False

        # First remove audio consumer to prevent new audio from being sent
        try:
            self.audio_manager.remove_consumer(self.transcriber.send_audio)
        except Exception as e:
            self.logger.error(f"Error removing transcriber consumer: {e}", exc_info=True)

        # Stop transcriber
        try:
            self.transcriber.stop()
        except Exception as e:
            self.logger.error(f"Error stopping transcriber: {e}", exc_info=True)

        # Stop context management and save meeting session
        if self.context_manager:
            try:
                self.context_manager.stop()
            except Exception as e:
                self.logger.error(f"Error stopping context manager: {e}", exc_info=True)
                
            if self.meeting_session_manager:
                try:
                    print(f"{colors['info']}🏁 Ending meeting session...{colors['reset']}")
                    self.meeting_session_manager.stop()
                except Exception as e:
                    self.logger.error(f"Error stopping meeting session manager: {e}", exc_info=True)
                    
        # Stop context access servers
        if self.context_access:
            try:
                self.context_access.stop()
            except Exception as e:
                self.logger.error(f"Error stopping context access servers: {e}", exc_info=True)
                
        # Stop trigger manager
        if self.trigger_manager:
            try:
                self.logger.info("🎯 Shutting down trigger system...")
                self.trigger_manager.shutdown()
                self.logger.info("✅ Trigger system shutdown complete")
            except Exception as e:
                self.logger.error(f"Error stopping trigger manager: {e}", exc_info=True)
                
        # Stop TTS services
        if self.audio_output:
            try:
                self.logger.info("🔊 Stopping audio output...")
                self.audio_output.stop()
                self.logger.info("✅ Audio output stopped")
            except Exception as e:
                self.logger.error(f"Error stopping audio output: {e}", exc_info=True)
                
        if self.tts_service:
            try:
                self.logger.info("🔊 Disconnecting TTS service...")
                self.tts_service.disconnect()
                self.logger.info("✅ TTS service disconnected")
            except Exception as e:
                self.logger.error(f"Error disconnecting TTS service: {e}", exc_info=True)

        # Stop audio stream
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

        self.logger.info("Voice transcriber stopped")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global transcriber
    transcriber.stop()
    sys.exit(0)


if __name__ == "__main__":
    # Setup logging system
    setup_logging(LOGGING_CONFIG)
    logger = get_logger(__name__)
    logger.info("Starting Voice Transcriber application")
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Create and start voice transcriber
    transcriber = VoiceTranscriber()

    try:
        transcriber.start()
    except Exception as e:
        logger.error("Failed to start Voice Transcriber", exc_info=True, extra={
            "extra_data": {"error_type": type(e).__name__, "error_message": str(e)}
        })
        transcriber.stop()