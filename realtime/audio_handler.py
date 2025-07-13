"""
Audio handler for Realtime API bidirectional streaming
"""

import threading
import queue
import base64
import time
from typing import Optional, Callable
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audio import AudioDeviceDetector, DeviceType
from config import AUDIO_DEVICE_CONFIG
from events import event_bus, EventTypes


class RealtimeAudioHandler:
    """Handles bidirectional audio for Realtime sessions"""
    
    def __init__(self,
                 audio_manager,
                 audio_output_manager,
                 session_manager,
                 device_detector: Optional[AudioDeviceDetector] = None):
        """
        Initialize audio handler
        
        Args:
            audio_manager: AudioStreamManager for input
            audio_output_manager: AudioOutputManager for output
            session_manager: RealtimeSessionManager instance
            device_detector: AudioDeviceDetector for smart feedback prevention
        """
        self.audio_manager = audio_manager
        self.audio_output_manager = audio_output_manager
        self.session_manager = session_manager
        
        # Device detection for smart feedback prevention
        self.device_detector = device_detector or AudioDeviceDetector(AUDIO_DEVICE_CONFIG)
        
        # Audio routing
        self.input_active = False
        self.output_active = False
        self.input_paused = False
        self.device_aware_pause = False  # New: track device-aware pausing
        
        # Audio conversion
        self.input_sample_rate = 16000  # From microphone
        self.output_sample_rate = 24000  # From Realtime API
        
        # Store consumer callback reference
        self.input_consumer = None
        
        # Output buffer for smooth playback
        self.output_queue = queue.Queue()
        self.output_thread = None
        
        # Get initial device type
        self.current_device_type = self.device_detector.get_current_device_type()
        print(f"[DEVICE] Detected audio device type: {self.current_device_type.value}")
        
        # Track playback state for better resume timing
        # Initialize to current time to prevent immediate resume issues
        self._last_audio_time = time.time()
        self._playback_monitor_thread = None
        self._resume_time = 0  # Track when input was resumed
        
        # Get echo prevention settings from config
        echo_config = AUDIO_DEVICE_CONFIG.get("speaker_echo_delay", {})
        self._dead_zone_duration = echo_config.get("dead_zone_duration", 0.5)
        self._min_silence_time = echo_config.get("min_silence_time", 1.0)
        
        # Set up playback complete callback
        if self.audio_output_manager:
            self.audio_output_manager.set_playback_complete_callback(self._on_playback_complete)
        
    def start(self):
        """Start audio handling for Realtime session"""
        if self.input_active:
            return
            
        print("Starting Realtime audio handler")
        
        # Store reference and register as audio consumer
        self.input_consumer = self._handle_input_audio
        self.audio_manager.add_consumer(self.input_consumer)
        
        # Configure session audio callback
        self.session_manager.audio_callback = self._handle_output_audio
        
        # Start output thread
        self.output_active = True
        self.output_thread = threading.Thread(
            target=self._output_worker,
            daemon=True
        )
        self.output_thread.start()
        
        self.input_active = True
        
    def stop(self):
        """Stop audio handling"""
        if not self.input_active:
            return
            
        print("Stopping Realtime audio handler")
        
        # Remove audio consumer using stored reference
        if self.input_consumer:
            self.audio_manager.remove_consumer(self.input_consumer)
            self.input_consumer = None
        
        # Stop output thread
        self.output_active = False
        if self.output_thread:
            self.output_thread.join(timeout=1.0)
            
        # Clear output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
                
        self.input_active = False
        
    def _handle_input_audio(self, audio_base64: str):
        """Handle input audio from microphone"""
        if not self.input_active or self.input_paused:
            return
        
        # Check if we're in the dead zone after resume
        if self._resume_time > 0:
            time_since_resume = time.time() - self._resume_time
            if time_since_resume < self._dead_zone_duration:
                # Still in dead zone, ignore input
                return
            
        # Forward to Realtime session
        if self.session_manager and self.session_manager.is_active():
            self.session_manager.send_audio(audio_base64)
            
    def _handle_output_audio(self, audio_data: bytes):
        """Handle output audio from Realtime API"""
        if not self.output_active:
            return
            
        # CRITICAL: Don't update _last_audio_time here!
        # It must only be updated in _on_playback_complete() when audio actually finishes playing.
        # Updating it here was causing the timeout issue because resume checks thought audio
        # had finished when it had only just arrived.
        
        # Queue for output
        try:
            self.output_queue.put_nowait(audio_data)
        except queue.Full:
            # Drop audio if queue is full
            pass
            
    def _output_worker(self):
        """Worker thread for audio output"""
        # Buffer for accumulating audio before playback
        audio_buffer = []
        buffer_size = 4800  # 100ms at 24kHz
        
        while self.output_active:
            try:
                # Get audio chunk
                audio_data = self.output_queue.get(timeout=0.1)
                
                # Add to buffer
                audio_buffer.append(audio_data)
                
                # Check if we have enough to play
                total_size = sum(len(chunk) for chunk in audio_buffer)
                
                if total_size >= buffer_size:
                    # Combine chunks
                    combined = b''.join(audio_buffer)
                    
                    # Send to output with proper sample rate handling
                    if self.audio_output_manager:
                        # Check if we need to resample
                        if self.output_sample_rate != self.audio_output_manager.sample_rate:
                            # Convert sample rate if needed
                            combined = self._resample_audio(
                                combined,
                                self.output_sample_rate,
                                self.audio_output_manager.sample_rate
                            )
                            
                        # Play audio
                        self.audio_output_manager.play_audio(combined)
                        
                        # Calculate and emit audio level for voice visualization
                        try:
                            # Convert to numpy array for RMS calculation
                            audio_array = np.frombuffer(combined, dtype=np.int16)
                            if len(audio_array) > 0:
                                # Calculate RMS (Root Mean Square)
                                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                                # Normalize to 0-1 range (int16 max is 32767)
                                normalized_level = min(1.0, (rms / 32767.0) * 2.0)
                                
                                # Emit audio level event for assistant voice
                                if normalized_level > 0.01:  # Only emit if there's actual sound
                                    event_bus.emit(EventTypes.AUDIO_OUTPUT_LEVEL, {
                                        "level": float(normalized_level),
                                        "rms": float(rms),
                                        "is_playing": True,
                                        "source": "realtime_assistant"
                                    }, source="realtime_audio_handler")
                        except Exception as e:
                            print(f"Error calculating audio level: {e}")
                        
                    # Clear buffer
                    audio_buffer = []
                    
            except queue.Empty:
                # If we have any buffered audio, play it
                if audio_buffer:
                    combined = b''.join(audio_buffer)
                    if self.audio_output_manager and len(combined) > 0:
                        # Resample if needed
                        if self.output_sample_rate != self.audio_output_manager.sample_rate:
                            combined = self._resample_audio(
                                combined,
                                self.output_sample_rate,
                                self.audio_output_manager.sample_rate
                            )
                        self.audio_output_manager.play_audio(combined)
                        
                        # Calculate and emit audio level
                        try:
                            audio_array = np.frombuffer(combined, dtype=np.int16)
                            if len(audio_array) > 0:
                                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                                normalized_level = min(1.0, (rms / 32767.0) * 2.0)
                                if normalized_level > 0.01:
                                    event_bus.emit(EventTypes.AUDIO_OUTPUT_LEVEL, {
                                        "level": float(normalized_level),
                                        "rms": float(rms),
                                        "is_playing": True,
                                        "source": "realtime_assistant"
                                    }, source="realtime_audio_handler")
                        except Exception as e:
                            print(f"Error calculating audio level: {e}")
                            
                    audio_buffer = []
                    
            except Exception as e:
                print(f"Error in audio output worker: {e}")
                
    def _resample_audio(self, audio_data: bytes, 
                       from_rate: int, to_rate: int) -> bytes:
        """
        Simple audio resampling
        
        Args:
            audio_data: PCM16 audio data
            from_rate: Source sample rate
            to_rate: Target sample rate
            
        Returns:
            Resampled audio data
        """
        if from_rate == to_rate:
            return audio_data
            
        try:
            # Convert to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate resampling factor
            factor = to_rate / from_rate
            
            # Simple linear interpolation resampling
            if factor > 1:
                # Upsampling
                new_length = int(len(audio_array) * factor)
                indices = np.arange(new_length) / factor
                resampled = np.interp(indices, np.arange(len(audio_array)), audio_array)
            else:
                # Downsampling
                indices = np.arange(0, len(audio_array), 1/factor)
                indices = indices[:int(len(audio_array) * factor)]
                resampled = audio_array[indices.astype(int)]
                
            # Convert back to int16
            resampled = resampled.astype(np.int16)
            
            return resampled.tobytes()
            
        except Exception as e:
            print(f"Error resampling audio: {e}")
            return audio_data  # Return original if resampling fails
            
    def is_active(self) -> bool:
        """Check if audio handler is active"""
        return self.input_active
        
    def interrupt_output(self):
        """Interrupt current audio output"""
        # Clear output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
                
        # Interrupt audio output manager
        if self.audio_output_manager:
            self.audio_output_manager.interrupt(fade_ms=50)
            
    def pause_input(self):
        """Pause audio input (to prevent feedback) - device-aware"""
        # Update device type in case it changed
        self.current_device_type = self.device_detector.get_current_device_type()
        feedback_needed = self.device_detector.is_feedback_prevention_needed()
        
        print(f"[DEBUG] pause_input() called - Device: {self.current_device_type.value}, Feedback prevention needed: {feedback_needed}")
        
        if feedback_needed:
            print(f"[DEVICE] ✓ Pausing microphone - {self.current_device_type.value} detected")
            self.input_paused = True
            self.device_aware_pause = True
        else:
            print(f"[DEVICE] Keeping microphone active - {self.current_device_type.value} allows interruption")
            self.device_aware_pause = False
        
    def resume_input(self):
        """Resume audio input - device-aware"""
        # Only resume if we actually paused it due to device type
        if self.device_aware_pause and self.input_paused:
            print(f"[DEVICE] ✓ Resuming microphone - {self.current_device_type.value}")
            self.input_paused = False
            self.device_aware_pause = False
            self._resume_time = time.time()  # Track resume time for dead zone
        elif self.input_paused and not self.device_aware_pause:
            # Input was paused by force, not device-aware logic
            print(f"[DEVICE] ✓ Resuming microphone (force paused) - {self.current_device_type.value}")
            self.input_paused = False
            self._resume_time = time.time()  # Track resume time for dead zone
        # Else: Nothing to resume, don't log anything to reduce noise
    
    def force_pause_input(self):
        """Force pause input regardless of device type (for manual override)"""
        print("[DEVICE] Force pausing microphone")
        self.input_paused = True
        
    def force_resume_input(self):
        """Force resume input regardless of device type (for manual override)"""
        print("[DEVICE] Force resuming microphone")
        self.input_paused = False
        
    def get_device_info(self) -> dict:
        """Get current device information and recommendations"""
        return self.device_detector.get_device_recommendations()
        
    def should_allow_interruption(self) -> bool:
        """Check if interruption should be allowed based on current device"""
        return self.device_detector.should_allow_interruption()
    
    def is_safe_to_resume_input(self) -> bool:
        """Check if it's safe to resume input (no audio playing and sufficient time passed)"""
        # Check if output is still playing
        if self.audio_output_manager and self.audio_output_manager.is_playing():
            buffer_duration = self.audio_output_manager.get_buffer_duration()
            is_actually_playing = self.audio_output_manager.is_actually_playing
            print(f"[AUDIO] Output still playing, not safe to resume (buffer: {buffer_duration:.2f}s, actually_playing: {is_actually_playing})")
            return False
        
        # Check if output queue has pending audio
        if not self.output_queue.empty():
            queue_size = self.output_queue.qsize()
            print(f"[AUDIO] Output queue not empty ({queue_size} items), not safe to resume")
            return False
        
        # Check time since last audio (add extra buffer for echo)
        time_since_last_audio = time.time() - self._last_audio_time
        
        if time_since_last_audio < self._min_silence_time:
            print(f"[AUDIO] Only {time_since_last_audio:.1f}s since last audio, waiting for {self._min_silence_time}s")
            return False
        
        print(f"[AUDIO] Safe to resume: no audio playing, {time_since_last_audio:.1f}s since last audio")
        return True
    
    def _on_playback_complete(self):
        """Called when audio playback completes"""
        current_time = time.time()
        time_since_previous = current_time - self._last_audio_time
        print(f"[AUDIO] Playback complete callback triggered - time since previous audio: {time_since_previous:.1f}s")
        # Update last audio time to now (when playback actually finished)
        self._last_audio_time = current_time
        
        # Emit audio level event indicating playback stopped
        event_bus.emit(EventTypes.AUDIO_OUTPUT_LEVEL, {
            "level": 0.0,
            "rms": 0.0,
            "is_playing": False,
            "source": "realtime_assistant"
        }, source="realtime_audio_handler")