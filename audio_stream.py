#!/usr/bin/env python3
"""
Audio Stream Manager - Handles microphone input and distributes to consumers
"""

import threading
import base64
import pyaudio
from config import AUDIO_CONFIG, DISPLAY_CONFIG
from events import event_bus, EventTypes
from logging_config import get_logger

logger = get_logger(__name__)


class AudioStreamManager:
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.running = False
        self.consumers = []
        self.consumers_lock = threading.Lock()
        self.stream = None
        self.audio_thread = None
        self.failed_consumers = set()  # Track repeatedly failing consumers
        
        # Pause/resume state
        self.paused_consumers = []  # Store consumers when paused
        self.is_paused = False
        
    def add_consumer(self, consumer_callback):
        """Add a consumer function that will receive audio data"""
        with self.consumers_lock:
            self.consumers.append(consumer_callback)
            # Remove from failed set if it was there
            self.failed_consumers.discard(consumer_callback)
        
    def remove_consumer(self, consumer_callback):
        """Remove a consumer function"""
        with self.consumers_lock:
            if consumer_callback in self.consumers:
                self.consumers.remove(consumer_callback)
            self.failed_consumers.discard(consumer_callback)
            
    def start(self):
        """Start capturing audio from microphone"""
        if self.running:
            return
            
        self.running = True
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=AUDIO_CONFIG["channels"],
            rate=AUDIO_CONFIG["sample_rate"],
            input=True,
            frames_per_buffer=AUDIO_CONFIG["chunk_size"]
        )
        
        # Start audio capture thread
        self.audio_thread = threading.Thread(target=self._audio_loop)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]
        logger.info("Audio stream started")
        print(f"{colors['info']}{emojis['mic']} Audio stream started{colors['reset']}")
        
        # Emit audio capture start event
        event_bus.emit(EventTypes.AUDIO_CAPTURE_START, {
            "sample_rate": AUDIO_CONFIG["sample_rate"],
            "channels": AUDIO_CONFIG["channels"],
            "chunk_size": AUDIO_CONFIG["chunk_size"]
        }, source="AudioStreamManager")
        
        # Listen for state requests
        event_bus.on(EventTypes.REQUEST_MICROPHONE_STATE, self._handle_state_request)
        
    def stop(self):
        """Stop audio capture"""
        # First, signal the audio thread to stop
        self.running = False
        
        # Wait for audio thread to finish processing
        if self.audio_thread:
            self.audio_thread.join(timeout=2.0)
            if self.audio_thread.is_alive():
                logger.warning("Audio thread did not exit in time")
        
        # Now it's safe to clear consumers
        with self.consumers_lock:
            self.consumers.clear()
            self.failed_consumers.clear()
            # Also clear paused consumers and reset pause state
            self.paused_consumers.clear()
            self.is_paused = False
            logger.debug("Cleared all audio consumers")
            
        # Stop and close stream before terminating PyAudio
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}", exc_info=True)
            
        # Finally terminate PyAudio
        try:
            self.audio.terminate()
        except Exception as e:
            logger.error(f"Error terminating PyAudio: {e}", exc_info=True)
        
        colors = DISPLAY_CONFIG["colors"]
        emojis = DISPLAY_CONFIG["emojis"]
        logger.info("Audio stream stopped")
        print(f"{colors['info']}{emojis['stop']} Audio stream stopped{colors['reset']}")
        
        # Emit audio capture stop event
        event_bus.emit(EventTypes.AUDIO_CAPTURE_STOP, {}, source="AudioStreamManager")
        
    def _audio_loop(self):
        """Main audio capture loop"""
        import time
        last_log_time = time.time()
        chunks_captured = 0
        
        while self.running:
            try:
                # Read audio chunk
                audio_data = self.stream.read(
                    AUDIO_CONFIG["chunk_size"], 
                    exception_on_overflow=False
                )
                chunks_captured += 1
                
                # Convert to base64
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                
                # Reduced periodic logging (every 30 seconds)
                current_time = time.time()
                if current_time - last_log_time > 30.0:
                    last_log_time = current_time
                    chunks_captured = 0
                
                # Send to all consumers with proper thread safety
                with self.consumers_lock:
                    # Check if we're still running inside the lock
                    if not self.running:
                        break
                    consumers_copy = self.consumers.copy()
                    failed_copy = self.failed_consumers.copy()
                    
                for consumer in consumers_copy:
                    # Check if we're still running for each consumer
                    if not self.running:
                        break
                        
                    # Skip consumers that have failed too many times
                    if consumer in failed_copy:
                        continue
                        
                    try:
                        consumer(audio_base64)
                    except Exception as e:
                        # Only log and track failures if we're still running
                        if self.running:
                            colors = DISPLAY_CONFIG["colors"]
                            logger.error(f"Consumer error: {e}", exc_info=True)
                            print(f"{colors['error']}Consumer error: {e}{colors['reset']}")
                            
                            # Track failed consumers to avoid repeated errors
                            with self.consumers_lock:
                                if consumer not in self.failed_consumers:
                                    self.failed_consumers.add(consumer)
                                    logger.warning("Consumer marked as failed and will be skipped")
                        
            except Exception as e:
                if self.running:
                    colors = DISPLAY_CONFIG["colors"]
                    logger.error(f"Audio capture error: {e}", exc_info=True)
                    print(f"{colors['error']}Audio capture error: {e}{colors['reset']}")
                    # Try to recover only if stream is still valid
                    if self.stream:
                        time.sleep(0.1)
                        continue
                break
        
        colors = DISPLAY_CONFIG["colors"]
        logger.info("Audio loop ended")
        
    def pause_microphone(self):
        """Pause microphone by temporarily removing all consumers"""
        with self.consumers_lock:
            if self.is_paused:
                logger.debug("Microphone already paused")
                return
                
            # Store current consumers
            self.paused_consumers = self.consumers.copy()
            # Clear active consumers
            self.consumers.clear()
            self.is_paused = True
            
            colors = DISPLAY_CONFIG["colors"]
            logger.info(f"Microphone paused - stored {len(self.paused_consumers)} consumers")
            
            # Emit microphone pause event
            event_bus.emit(EventTypes.AUDIO_MICROPHONE_PAUSE, {
                "consumers_paused": len(self.paused_consumers)
            }, source="AudioStreamManager")
            
    def resume_microphone(self):
        """Resume microphone by restoring consumers"""
        with self.consumers_lock:
            if not self.is_paused:
                logger.debug("Microphone not paused")
                return
                
            # Restore consumers
            self.consumers = self.paused_consumers.copy()
            self.paused_consumers.clear()
            self.is_paused = False
            
            # Clear any failed consumers that were paused
            for consumer in self.consumers:
                self.failed_consumers.discard(consumer)
            
            colors = DISPLAY_CONFIG["colors"]
            logger.info(f"Microphone resumed - restored {len(self.consumers)} consumers")
            
            # Emit microphone resume event
            event_bus.emit(EventTypes.AUDIO_MICROPHONE_RESUME, {
                "consumers_restored": len(self.consumers)
            }, source="AudioStreamManager")
            
    def is_microphone_paused(self) -> bool:
        """Check if microphone is currently paused"""
        with self.consumers_lock:
            return self.is_paused
    
    def broadcast_microphone_state(self):
        """Broadcast current microphone state for dashboard synchronization"""
        with self.consumers_lock:
            event_bus.emit(EventTypes.AUDIO_MICROPHONE_STATE, {
                "is_paused": self.is_paused,
                "consumers_count": len(self.consumers),
                "is_running": self.running
            }, source="AudioStreamManager")
    
    def _handle_state_request(self, event):
        """Handle requests for current microphone state"""
        self.broadcast_microphone_state()