"""
Simple OpenAI TTS implementation using the official client library
"""

import asyncio
import threading
import time
from typing import Optional, Callable
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()


class OpenAITTSService:
    """Service for converting text to speech using OpenAI TTS API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
            
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        
        # Import config for voice settings
        from config import TTS_CONFIG
        
        self.connected = False
        self.voice = TTS_CONFIG.get("voice", "alloy")
        self.model = "tts-1"  # or "tts-1-hd" for higher quality
        self.speed = 1.0  # Speech speed (0.25 to 4.0)
        
        # Queue for sequential TTS processing
        self.tts_queue = None
        self.processing_task = None
        self.event_loop = None
        
        # Track active synthesis
        self.synthesis_cancelled = False
        
    def connect(self):
        """Initialize the TTS service"""
        if self.connected:
            return
            
        try:
            self.connected = True
            # Start the processing task
            self.event_loop = asyncio.new_event_loop()
            
            def run_loop():
                asyncio.set_event_loop(self.event_loop)
                # Create queue in the correct event loop
                self.tts_queue = asyncio.Queue()
                self.processing_task = self.event_loop.create_task(self._process_tts_queue())
                self.event_loop.run_forever()
            
            threading.Thread(target=run_loop, daemon=True).start()
            print("OpenAI TTS service ready (simple implementation)")
            
        except Exception as e:
            print(f"Failed to initialize OpenAI TTS service: {e}")
            raise ConnectionError(f"Failed to initialize OpenAI TTS service: {e}")
            
    def synthesize(self, text: str, callback: Callable[[bytes], None], 
                   on_start: Optional[Callable[[], None]] = None,
                   on_complete: Optional[Callable[[], None]] = None,
                   voice: Optional[str] = None,
                   speed: Optional[float] = None):
        """Synthesize speech from text
        
        Args:
            text: Text to synthesize
            callback: Function to call with audio chunks
            on_start: Optional callback when synthesis starts
            on_complete: Optional callback when synthesis completes
            voice: Optional voice override
            speed: Optional speed override (0.25 to 4.0)
        """
        if not self.connected:
            self.connect()
            
        # Add to queue for sequential processing
        try:
            asyncio.run_coroutine_threadsafe(
                self.tts_queue.put((text, callback, on_start, on_complete, voice, speed)),
                self.event_loop
            )
        except RuntimeError as e:
            print(f"Error queuing TTS: {e}")
            # Try to recover by reconnecting
            self.connected = False
            self.connect()
            # Try again
            asyncio.run_coroutine_threadsafe(
                self.tts_queue.put((text, callback, on_start, on_complete, voice, speed)),
                self.event_loop
            )
        
    async def _process_tts_queue(self):
        """Process TTS requests sequentially from the queue"""
        while True:
            try:
                # Get next TTS request
                item = await self.tts_queue.get()
                
                # Unpack request
                text, callback, on_start, on_complete, voice, speed = item
                
                # Check if synthesis was cancelled
                if self.synthesis_cancelled:
                    print("TTS synthesis cancelled, skipping request")
                    self.synthesis_cancelled = False
                    if on_complete:
                        on_complete()
                    continue
                
                # Call on_start callback if provided
                if on_start:
                    on_start()
                
                # Synthesize this request
                await self._synthesize_simple(text, callback, voice, speed)
                
                # Call on_complete callback if provided
                if on_complete:
                    on_complete()
                
                # Small delay between requests to ensure clean audio
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"Error processing TTS queue: {e}")
                import traceback
                traceback.print_exc()
            
    async def _synthesize_simple(self, text: str, callback: Callable[[bytes], None],
                                 voice: Optional[str] = None, speed: Optional[float] = None):
        """Synthesize using the OpenAI client library"""
        try:
            print(f"[TTS] Starting synthesis for text: {text[:50]}...")
            print(f"[TTS] Using voice: {voice or self.voice}, speed: {speed or self.speed}")
            
            # Validate and clean text
            if not text or not text.strip():
                print("[TTS] Error: Empty text provided")
                return
                
            # Use provided voice/speed or defaults
            voice = voice or self.voice
            speed = speed or self.speed
            
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            
            def generate_speech():
                print("[TTS] Calling OpenAI API...")
                response = self.client.audio.speech.create(
                    model=self.model,
                    voice=voice,
                    input=text.strip(),
                    response_format="pcm",  # Raw PCM audio (16-bit at 24kHz)
                    speed=speed
                )
                print("[TTS] API call completed")
                return response
            
            # Generate speech in thread pool
            response = await loop.run_in_executor(None, generate_speech)
            
            print("[TTS] Processing audio response...")
            
            # Stream the response content
            chunk_size = 4096  # 4KB chunks
            chunk_count = 0
            total_bytes = 0
            
            # The response object has a .content attribute that's a bytes-like object
            # We can also use response.stream_to_file() or response.iter_bytes()
            if hasattr(response, 'iter_bytes'):
                # Streaming response
                for chunk in response.iter_bytes(chunk_size):
                    if self.synthesis_cancelled:
                        print("[TTS] Synthesis cancelled during streaming")
                        break
                        
                    if chunk and callback:
                        chunk_count += 1
                        total_bytes += len(chunk)
                        callback(chunk)
                        
                        # Debug output every 10 chunks
                        if chunk_count % 10 == 0:
                            print(f"[TTS] Streamed {chunk_count} chunks, {total_bytes} bytes total")
            else:
                # If no streaming available, send all at once
                audio_data = response.content
                print(f"[TTS] Got {len(audio_data)} bytes of audio data")
                
                # Send in chunks to callback
                for i in range(0, len(audio_data), chunk_size):
                    if self.synthesis_cancelled:
                        print("[TTS] Synthesis cancelled during playback")
                        break
                        
                    chunk = audio_data[i:i+chunk_size]
                    if chunk and callback:
                        chunk_count += 1
                        total_bytes += len(chunk)
                        callback(chunk)
                        
                        # Small delay to prevent overwhelming the audio buffer
                        await asyncio.sleep(0.01)
                
            print(f"[TTS] Streaming complete: {chunk_count} chunks, {total_bytes} bytes total")
            print("[TTS] Synthesis completed successfully")
            
        except Exception as e:
            print(f"[TTS] Error during synthesis: {e}")
            print(f"[TTS] Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            
    def cancel_synthesis(self):
        """Cancel any ongoing synthesis"""
        self.synthesis_cancelled = True
        print("[TTS] Synthesis cancellation requested")
        
    def disconnect(self):
        """Disconnect the TTS service"""
        self.connected = False
        if self.event_loop:
            self.event_loop.call_soon_threadsafe(self.event_loop.stop)
            
    def get_available_voices(self):
        """Get list of available voices"""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]