"""
Application state manager for tracking system state and transitions
"""

import threading
import time
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from events import event_bus, EventTypes


class AppState(Enum):
    """Application states"""
    INITIALIZING = "initializing"
    LISTENING = "listening"  # Normal transcription mode
    ASSISTANT_ACTIVATING = "assistant_activating"
    ASSISTANT_ACTIVE = "assistant_active"
    ASSISTANT_CLOSING = "assistant_closing"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


class StateTransition:
    """Represents a state transition"""
    def __init__(self, from_state: AppState, to_state: AppState, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        self.timestamp = time.time()
        self.datetime = datetime.now()
        
    def __str__(self):
        return f"{self.from_state.value} → {self.to_state.value} ({self.reason})"


class StateManager:
    """Manages application state and enforces valid transitions"""
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        AppState.INITIALIZING: [AppState.LISTENING, AppState.ERROR],
        AppState.LISTENING: [AppState.ASSISTANT_ACTIVATING, AppState.ERROR, AppState.SHUTTING_DOWN],
        AppState.ASSISTANT_ACTIVATING: [AppState.ASSISTANT_ACTIVE, AppState.LISTENING, AppState.ERROR],
        AppState.ASSISTANT_ACTIVE: [AppState.ASSISTANT_CLOSING, AppState.ERROR],
        AppState.ASSISTANT_CLOSING: [AppState.LISTENING, AppState.ERROR],
        AppState.ERROR: [AppState.LISTENING, AppState.SHUTTING_DOWN],
        AppState.SHUTTING_DOWN: []  # Terminal state
    }
    
    def __init__(self):
        """Initialize state manager"""
        self.current_state = AppState.INITIALIZING
        self.state_lock = threading.RLock()
        
        # State history
        self.transitions: List[StateTransition] = []
        self.max_history = 100
        
        # State listeners
        self.state_listeners: List[Callable[[AppState, AppState], None]] = []
        
        # State timing
        self.state_start_time = time.time()
        self.state_durations: Dict[AppState, float] = {state: 0.0 for state in AppState}
        
        # Error tracking
        self.error_count = 0
        self.last_error = None
        
    def get_state(self) -> AppState:
        """Get current state"""
        with self.state_lock:
            return self.current_state
            
    def transition_to(self, new_state: AppState, reason: str = "") -> bool:
        """
        Transition to a new state
        
        Args:
            new_state: Target state
            reason: Reason for transition
            
        Returns:
            True if transition successful, False if invalid
        """
        with self.state_lock:
            # Check if transition is valid
            if not self._is_valid_transition(self.current_state, new_state):
                print(f"Invalid state transition: {self.current_state.value} → {new_state.value}")
                return False
                
            # Record state duration
            current_duration = time.time() - self.state_start_time
            self.state_durations[self.current_state] += current_duration
            
            # Create transition record
            transition = StateTransition(self.current_state, new_state, reason)
            self.transitions.append(transition)
            
            # Trim history
            if len(self.transitions) > self.max_history:
                self.transitions = self.transitions[-self.max_history:]
                
            # Update state
            old_state = self.current_state
            self.current_state = new_state
            self.state_start_time = time.time()
            
            # Track errors
            if new_state == AppState.ERROR:
                self.error_count += 1
                self.last_error = reason
                
            print(f"State transition: {transition}")
            
            # Note: Assistant session events are emitted by session_manager.py
            # to avoid duplicate events. State transitions are still emitted below.
                
            # Emit state transition event
            event_bus.emit("state.transition", {
                "from_state": old_state.value,
                "to_state": new_state.value,
                "reason": reason
            }, source="state_manager")
            
        # Notify listeners (outside lock to prevent deadlocks)
        self._notify_listeners(old_state, new_state)
        
        return True
        
    def add_listener(self, listener: Callable[[AppState, AppState], None]):
        """Add state change listener"""
        self.state_listeners.append(listener)
        
    def remove_listener(self, listener: Callable[[AppState, AppState], None]):
        """Remove state change listener"""
        if listener in self.state_listeners:
            self.state_listeners.remove(listener)
            
    def _is_valid_transition(self, from_state: AppState, to_state: AppState) -> bool:
        """Check if state transition is valid"""
        valid_targets = self.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_targets
        
    def _notify_listeners(self, old_state: AppState, new_state: AppState):
        """Notify all listeners of state change"""
        for listener in self.state_listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                print(f"Error in state listener: {e}")
                
    def is_in_assistant_mode(self) -> bool:
        """Check if currently in any assistant-related state"""
        with self.state_lock:
            return self.current_state in [
                AppState.ASSISTANT_ACTIVATING,
                AppState.ASSISTANT_ACTIVE,
                AppState.ASSISTANT_CLOSING
            ]
            
    def is_operational(self) -> bool:
        """Check if system is in operational state"""
        with self.state_lock:
            return self.current_state in [
                AppState.LISTENING,
                AppState.ASSISTANT_ACTIVE
            ]
            
    def get_state_duration(self) -> float:
        """Get duration in current state (seconds)"""
        with self.state_lock:
            return time.time() - self.state_start_time
            
    def get_transition_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent state transitions"""
        with self.state_lock:
            recent = self.transitions[-limit:] if self.transitions else []
            return [
                {
                    "from": t.from_state.value,
                    "to": t.to_state.value,
                    "reason": t.reason,
                    "timestamp": t.timestamp,
                    "datetime": t.datetime.isoformat()
                }
                for t in recent
            ]
            
    def get_stats(self) -> Dict[str, Any]:
        """Get state manager statistics"""
        with self.state_lock:
            # Calculate total time in each state
            state_percentages = {}
            total_time = sum(self.state_durations.values())
            
            if total_time > 0:
                for state, duration in self.state_durations.items():
                    # Add current state duration
                    if state == self.current_state:
                        duration += time.time() - self.state_start_time
                    state_percentages[state.value] = (duration / total_time) * 100
                    
            return {
                "current_state": self.current_state.value,
                "state_duration": self.get_state_duration(),
                "transition_count": len(self.transitions),
                "error_count": self.error_count,
                "last_error": self.last_error,
                "state_percentages": state_percentages,
                "is_operational": self.is_operational(),
                "is_assistant_mode": self.is_in_assistant_mode()
            }
            
    def reset_error_state(self, target_state: AppState = AppState.LISTENING) -> bool:
        """Reset from error state"""
        with self.state_lock:
            if self.current_state != AppState.ERROR:
                return False
                
            return self.transition_to(target_state, "Error recovery")
            
    def emergency_shutdown(self):
        """Force transition to shutdown state"""
        with self.state_lock:
            # Force transition regardless of current state
            old_state = self.current_state
            self.current_state = AppState.SHUTTING_DOWN
            
            transition = StateTransition(old_state, AppState.SHUTTING_DOWN, "Emergency shutdown")
            self.transitions.append(transition)
            
            print(f"Emergency shutdown: {transition}")
            
        self._notify_listeners(old_state, AppState.SHUTTING_DOWN)