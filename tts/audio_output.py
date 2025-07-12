"""
Audio output manager for playing TTS audio
"""

import queue
import threading
import pyaudio
import time
from typing import Optional, List
from events import event_bus, EventTypes


class AudioOutputManager:
    """Manages audio output playback"""
    
    def __init__(self, sample_rate: int = 24000, channels: int = 1, chunk_size: int = 2048):
        # Import config for TTS settings
        from config import TTS_CONFIG
        
        self.sample_rate = TTS_CONFIG.get("output_sample_rate", sample_rate)
        self.channels = channels
        self.chunk_size = TTS_CONFIG.get("playback_chunk_size", chunk_size)
        self.format = pyaudio.paInt16
        
        # Audio components
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        
        # Playback queue and thread
        self.audio_queue = queue.Queue()
        self.playback_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Simple byte buffer instead of numpy array
        self.audio_buffer = b''  # Direct bytes
        self.buffer_lock = threading.Lock()
        
        # Track timing for smooth playback
        self.total_samples_played = 0
        self.playback_start_time = None
        
        # Debug counters
        self.callback_count = 0
        self.last_callback_log = 0
        
        # Playback state tracking
        self.is_actually_playing = False
        self.playback_complete_callbacks = []
        
    def start(self):
        """Start the audio output stream"""
        if self.running:
            return
            
        # Open audio stream
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.sample_rate,
            output=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._audio_callback
        )
        
        # Start playback thread
        self.running = True
        self.playback_thread = threading.Thread(target=self._playback_worker)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
        # Start the stream
        self.stream.start_stream()
        print("Audio output started")
        
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback for continuous playback"""
        # Track callback invocations
        self.callback_count += 1
        current_time = time.time()
        
        # Log every second
        if current_time - self.last_callback_log >= 1.0:
            buffer_samples = len(self.audio_buffer) // 2  # 2 bytes per sample (16-bit)
            print(f"[AUDIO] Callback #{self.callback_count}, buffer size: {buffer_samples} samples")
            self.last_callback_log = current_time
        
        # Calculate bytes needed (2 bytes per sample for 16-bit audio)
        bytes_needed = frame_count * 2
        
        with self.buffer_lock:
            if len(self.audio_buffer) > 0:
                # Track timing on first playback
                if self.playback_start_time is None:
                    self.playback_start_time = time.time()
                
                # Mark as actually playing
                if not self.is_actually_playing:
                    self.is_actually_playing = True
                    print("[AUDIO] Playback started")
                
                # Take the required bytes from the buffer
                bytes_to_take = min(len(self.audio_buffer), bytes_needed)
                output = self.audio_buffer[:bytes_to_take]
                
                # Pad with silence if we don't have enough
                if bytes_to_take < bytes_needed:
                    output += b'\x00' * (bytes_needed - bytes_to_take)
                
                # Remove used bytes from buffer
                self.audio_buffer = self.audio_buffer[bytes_to_take:]
                
                # Update total samples played
                self.total_samples_played += bytes_to_take // 2
                
            else:
                # Buffer empty - generate silence
                output = b'\x00' * bytes_needed
                
                # Check if we were playing
                if self.is_actually_playing:
                    self.is_actually_playing = False
                    print("[AUDIO] Playback complete")
                    
                    # Call playback complete callbacks if any
                    for callback in self.playback_complete_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            print(f"[ERROR] Playback complete callback failed: {e}")
                
        return (output, pyaudio.paContinue)
        
    def _playback_worker(self):
        """Worker thread for processing audio queue"""
        while self.running:
            try:
                # Get audio data from queue
                audio_data = self.audio_queue.get(timeout=0.1)
                
                if audio_data is None:
                    continue
                    
                # Append bytes directly to buffer
                with self.buffer_lock:
                    self.audio_buffer += audio_data
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Playback error: {e}")
                
    def play_audio(self, audio_data: bytes):
        """Queue audio data for playback"""
        if not self.running:
            self.start()
            
        # Add to queue
        self.audio_queue.put(audio_data)
        
        # Audio data received (reduced logging)
        
    def stop(self):
        """Stop the audio output stream"""
        self.running = False
        
        # Stop playback thread
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=2.0)
            
        # Stop and close stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            
        print("Audio output stopped")
        
    def clear_queue(self):
        """Clear any pending audio"""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
                
        with self.buffer_lock:
            self.audio_buffer = b''  # Clear bytes buffer
            
            # Mark as not playing and trigger callback if we were playing
            if self.is_actually_playing:
                self.is_actually_playing = False
                print("[AUDIO] Playback cleared")
                
                # Call playback complete callbacks if any
                for callback in self.playback_complete_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        print(f"[ERROR] Playback complete callback failed: {e}")
            
        # Reset timing
        self.total_samples_played = 0
        self.playback_start_time = None
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        with self.buffer_lock:
            # Check both buffer and actual playback state
            return len(self.audio_buffer) > 0 or self.is_actually_playing
    
    def get_buffer_duration(self) -> float:
        """Get the duration of audio remaining in the buffer (in seconds)"""
        with self.buffer_lock:
            if len(self.audio_buffer) == 0:
                return 0.0
            # 2 bytes per sample for 16-bit audio
            samples = len(self.audio_buffer) // 2
            return samples / self.sample_rate
    
    def add_playback_complete_callback(self, callback):
        """Add a callback to be called when playback completes"""
        if callback not in self.playback_complete_callbacks:
            self.playback_complete_callbacks.append(callback)
    
    def remove_playback_complete_callback(self, callback):
        """Remove a playback complete callback"""
        if callback in self.playback_complete_callbacks:
            self.playback_complete_callbacks.remove(callback)
    
    def set_playback_complete_callback(self, callback):
        """Set a callback to be called when playback completes (legacy method)"""
        # Clear existing callbacks and add the new one for backward compatibility
        self.playback_complete_callbacks.clear()
        if callback:
            self.playback_complete_callbacks.append(callback)
    
    def wait_for_playback_complete(self, timeout: float = 30.0, expected_text: str = "") -> bool:
        """
        Wait for audio playback to complete
        
        Args:
            timeout: Maximum time to wait in seconds
            expected_text: Text being synthesized (for duration estimation)
            
        Returns:
            True if playback completed, False if timeout
        """
        start_time = time.time()
        check_interval = 0.05  # Check every 50ms
        
        print(f"[AUDIO] Waiting for playback to complete...")
        
        # Check if stream is active
        if not self.stream or not self.stream.is_active():
            print("[AUDIO] Warning: Audio stream is not active")
            return True
        
        # Estimate expected duration based on text length (conservative calculation)
        # Use a more conservative estimate: ~10 characters per second for Portuguese
        # This accounts for slower speech and ensures we don't resume too early
        estimated_duration = max(2.0, len(expected_text) / 10.0) if expected_text else 3.0
        min_wait_time = min(1.0, estimated_duration * 0.4)  # Wait at least 40% of estimated duration
        
        print(f"[AUDIO] Estimated duration: {estimated_duration:.1f}s, minimum wait: {min_wait_time:.1f}s")
        
        # First, wait for audio to start streaming into buffer
        audio_started = False
        buffer_start_time = start_time
        
        while time.time() - start_time < timeout:
            # Calculate everything inside a single lock acquisition
            with self.buffer_lock:
                buffer_empty = len(self.audio_buffer) == 0
                buffer_size = len(self.audio_buffer)
                # Calculate duration directly here (2 bytes per sample)
                samples = buffer_size // 2
                remaining_duration = samples / self.sample_rate if samples > 0 else 0.0
            
            elapsed = time.time() - start_time
            
            # Check if audio has started streaming
            if not audio_started and buffer_size > 0:
                audio_started = True
                buffer_start_time = time.time()
                print(f"[AUDIO] Audio started streaming after {elapsed:.2f}s")
            
            # Don't complete until we've waited the minimum time AND audio has started AND is no longer playing
            if buffer_empty and audio_started and elapsed >= min_wait_time and not self.is_actually_playing:
                print(f"[AUDIO] Playback complete after {elapsed:.2f}s (min wait: {min_wait_time:.1f}s)")
                return True
            elif buffer_empty and not audio_started and elapsed > 3.0:
                # If no audio started after 3 seconds, assume it's done (increased from 2s)
                print(f"[AUDIO] No audio detected after 3s, assuming complete")
                return True
            else:
                # Still playing or haven't waited minimum time
                if int(elapsed) != int(elapsed - check_interval):  # Log every second boundary
                    if buffer_size > 0:
                        print(f"[AUDIO] Still playing... {remaining_duration:.2f}s remaining in buffer ({buffer_size} samples)")
                    elif elapsed < min_wait_time:
                        print(f"[AUDIO] Waiting minimum time... {min_wait_time - elapsed:.1f}s remaining")
                    
            time.sleep(check_interval)
            
        print(f"[AUDIO] Playback timeout after {timeout}s")
        return False
    
    def interrupt(self, fade_ms: int = 50):
        """Interrupt current playback
        
        Args:
            fade_ms: Duration of fade out in milliseconds (ignored in simplified version)
        """
        print(f"Interrupting audio playback")
        
        # Clear the queue first to prevent new audio from being added
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        
        with self.buffer_lock:
            # Simply clear the buffer (no fade effect without numpy)
            self.audio_buffer = b''
            
            # Reset timing and state
            self.total_samples_played = 0
            self.playback_start_time = None
            
            # Mark as not playing and trigger callback if we were playing
            if self.is_actually_playing:
                self.is_actually_playing = False
                print("[AUDIO] Playback interrupted")
                
                # Call playback complete callbacks if any
                for callback in self.playback_complete_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        print(f"[ERROR] Playback complete callback failed: {e}")
            
    def __del__(self):
        """Cleanup on deletion"""
        self.stop()
        if hasattr(self, 'audio'):
            self.audio.terminate()