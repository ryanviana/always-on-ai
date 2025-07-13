"""
Central event bus for tracking and broadcasting system events
"""

import time
import json
import threading
from typing import Dict, Any, List, Callable, Optional
from queue import Queue, Empty
from collections import defaultdict
from datetime import datetime
import uuid


class SystemEvent:
    """Represents a system event"""
    
    def __init__(self, event_type: str, data: Dict[str, Any], source: str = None):
        self.id = str(uuid.uuid4())
        self.type = event_type
        self.data = data
        self.source = source or "system"
        self.timestamp = time.time()
        self.datetime = datetime.now().isoformat()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp,
            "datetime": self.datetime
        }


class EventBus:
    """Central event bus for system-wide event tracking"""
    
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.event_queue = Queue()
        self.event_history: List[SystemEvent] = []
        self.max_history = 1000
        self._running = True
        self._processor_thread = threading.Thread(target=self._process_events, daemon=True)
        self._processor_thread.start()
        
        # Performance metrics
        self.event_counts = defaultdict(int)
        self.processing_times = defaultdict(list)
        
    def emit(self, event_type: str, data: Dict[str, Any], source: str = None):
        """Emit an event to the bus"""
        event = SystemEvent(event_type, data, source)
        self.event_queue.put(event)
        
    def on(self, event_type: str, callback: Callable[[SystemEvent], None]):
        """Register a listener for specific event type"""
        self.listeners[event_type].append(callback)
        
    def on_all(self, callback: Callable[[SystemEvent], None]):
        """Register a listener for all events"""
        self.listeners["*"].append(callback)
        
    def off(self, event_type: str, callback: Callable[[SystemEvent], None]):
        """Remove a listener"""
        if callback in self.listeners[event_type]:
            self.listeners[event_type].remove(callback)
            
    def _process_events(self):
        """Process events from the queue"""
        while self._running:
            try:
                event = self.event_queue.get(timeout=0.1)
                start_time = time.time()
                
                # Track event
                self.event_counts[event.type] += 1
                
                # Debug logging for tool events
                if event.type.startswith('tool.'):
                    print(f"[DEBUG] Event Bus processing tool event: {event.type} from {event.source}")
                
                # Add to history
                self.event_history.append(event)
                if len(self.event_history) > self.max_history:
                    self.event_history.pop(0)
                
                # Notify specific listeners
                for listener in self.listeners.get(event.type, []):
                    try:
                        listener(event)
                    except Exception as e:
                        print(f"Error in event listener for {event.type}: {e}")
                        
                # Notify wildcard listeners
                for listener in self.listeners.get("*", []):
                    try:
                        listener(event)
                    except Exception as e:
                        print(f"Error in wildcard event listener: {e}")
                        
                # Track processing time
                processing_time = time.time() - start_time
                self.processing_times[event.type].append(processing_time)
                if len(self.processing_times[event.type]) > 100:
                    self.processing_times[event.type].pop(0)
                    
            except Empty:
                continue
            except Exception as e:
                print(f"Error processing event: {e}")
                
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        stats = {
            "total_events": sum(self.event_counts.values()),
            "event_counts": dict(self.event_counts),
            "queue_size": self.event_queue.qsize(),
            "history_size": len(self.event_history),
            "listener_counts": {
                event_type: len(listeners)
                for event_type, listeners in self.listeners.items()
            }
        }
        
        # Calculate average processing times
        avg_times = {}
        for event_type, times in self.processing_times.items():
            if times:
                avg_times[event_type] = sum(times) / len(times)
        stats["avg_processing_times"] = avg_times
        
        return stats
        
    def get_recent_events(self, count: int = 50, event_type: str = None) -> List[Dict[str, Any]]:
        """Get recent events from history"""
        events = self.event_history[-count:]
        
        if event_type:
            events = [e for e in events if e.type == event_type]
            
        return [e.to_dict() for e in events]
        
    def shutdown(self):
        """Shutdown the event bus"""
        self._running = False
        if self._processor_thread.is_alive():
            self._processor_thread.join(timeout=2.0)


# Global event bus instance
event_bus = EventBus()


# Event type constants
class EventTypes:
    # Trigger events
    TRIGGER_KEYWORD_MATCH = "trigger.keyword_match"
    TRIGGER_VALIDATION_START = "trigger.validation_start"
    TRIGGER_VALIDATION_COMPLETE = "trigger.validation_complete"
    TRIGGER_EXECUTION_START = "trigger.execution_start"
    TRIGGER_EXECUTION_COMPLETE = "trigger.execution_complete"
    TRIGGER_EXECUTION_ERROR = "trigger.execution_error"
    
    # Audio events
    AUDIO_CAPTURE_START = "audio.capture_start"
    AUDIO_CAPTURE_STOP = "audio.capture_stop"
    AUDIO_MICROPHONE_PAUSE = "audio.microphone_pause"
    AUDIO_MICROPHONE_RESUME = "audio.microphone_resume"
    AUDIO_MICROPHONE_STATE = "audio.microphone_state"
    REQUEST_MICROPHONE_STATE = "request.microphone_state"
    AUDIO_PLAYBACK_START = "audio.playback_start"
    AUDIO_PLAYBACK_COMPLETE = "audio.playback_complete"
    AUDIO_OUTPUT_LEVEL = "audio.output_level"
    
    # Transcription events
    TRANSCRIPTION_START = "transcription.start"
    TRANSCRIPTION_COMPLETE = "transcription.complete"
    TRANSCRIPTION_ERROR = "transcription.error"
    
    # TTS events
    TTS_SYNTHESIS_START = "tts.synthesis_start"
    TTS_SYNTHESIS_COMPLETE = "tts.synthesis_complete"
    TTS_PLAYBACK_START = "tts.playback_start"
    TTS_PLAYBACK_COMPLETE = "tts.playback_complete"
    
    # Assistant mode events
    ASSISTANT_SESSION_START = "assistant.session_start"
    ASSISTANT_SESSION_END = "assistant.session_end"
    ASSISTANT_SPEAKING_START = "assistant.speaking_start"
    ASSISTANT_SPEAKING_END = "assistant.speaking_end"
    ASSISTANT_LISTENING_START = "assistant.listening_start"
    ASSISTANT_LISTENING_END = "assistant.listening_end"
    
    # Tool events
    TOOL_CALL_START = "tool.call_start"
    TOOL_CALL_COMPLETE = "tool.call_complete"
    TOOL_CALL_ERROR = "tool.call_error"
    TOOL_PROCESSING_START = "tool.processing_start"
    TOOL_PROCESSING_END = "tool.processing_end"
    
    # Context events
    CONTEXT_ADD_TRANSCRIPTION = "context.add_transcription"
    CONTEXT_SUMMARIZATION_START = "context.summarization_start"
    CONTEXT_SUMMARIZATION_COMPLETE = "context.summarization_complete"
    CONTEXT_CLEARED = "context.cleared"
    
    # System events
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    SYSTEM_ERROR = "system.error"
    
    # WebSocket events
    WEBSOCKET_CLIENT_CONNECT = "websocket.client_connect"
    WEBSOCKET_CLIENT_DISCONNECT = "websocket.client_disconnect"
    WEBSOCKET_MESSAGE_SENT = "websocket.message_sent"
    
    # Performance events
    PERFORMANCE_METRIC = "performance.metric"