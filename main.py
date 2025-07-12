#!/usr/bin/env python3
"""
Main application - Simple real-time transcription only
"""

import signal
import sys
import threading
import time
from audio_stream import AudioStreamManager
from transcription.simple_transcriber import SimpleTranscriber
from config import (
    DISPLAY_CONFIG, CONVERSATION_CONFIG, LOGGING_CONFIG, CONNECTION_TIMEOUT
)
from logging_config import setup_logging, get_logger


class SimpleVoiceTranscriber:
    def __init__(self):
        self.logger = get_logger(__name__)
        self.audio_manager = AudioStreamManager()
        
        # Initialize transcriber without any external dependencies
        self.transcriber = SimpleTranscriber(
            trigger_manager=None,
            speech_started_callback=None,
            speech_stopped_callback=None,
            use_conversation_manager=CONVERSATION_CONFIG.get("enabled", False),
        )
        
        self.running = False
        
    def start(self):
        """Start the voice transcriber"""
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]

        self.logger.info("Starting Simple Voice Transcriber")
        print(f"{colors['info']}{emojis['mic']} Starting real-time transcription...{colors['reset']}")

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
        self.logger.info("Transcription system ready")
        print(f"{colors['info']}{emojis['speaker']} Listening for speech... (Press Ctrl+C to stop){colors['reset']}")

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
    logger.info("Starting Simple Voice Transcriber application")
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Create and start voice transcriber
    transcriber = SimpleVoiceTranscriber()

    try:
        transcriber.start()
    except Exception as e:
        logger.error("Failed to start Simple Voice Transcriber", exc_info=True, extra={
            "extra_data": {"error_type": type(e).__name__, "error_message": str(e)}
        })
        transcriber.stop()