"""
Trigger execution component
"""

from typing import Dict, Any, Optional, Callable

from .base import BaseTrigger
from .models import ValidationResult, TriggerResponse
from .utils import setup_trigger_logger
from .exceptions import TriggerExecutionError
from events import event_bus, EventTypes
from config import TTS_CONFIG


class TriggerExecutor:
    """Handles trigger action execution and TTS"""
    
    def __init__(self, tts_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        self.logger = setup_trigger_logger("TriggerExecutor")
        self.tts_callback = tts_callback
        
    def execute_trigger(self, trigger: BaseTrigger, validation_result: ValidationResult, 
                       request_context: Optional[Dict[str, Any]] = None) -> Optional[TriggerResponse]:
        """
        Execute a validated trigger action
        
        Args:
            trigger: The trigger to execute
            validation_result: Validation result from LLM
            request_context: Optional context about the original request
            
        Returns:
            TriggerResponse if successful, None otherwise
            
        Raises:
            TriggerExecutionError: If execution fails
        """
        self.logger.info(f"Executing {trigger.name} trigger")
        
        # Emit execution start event
        event_data = {
            "trigger_name": trigger.name,
            "confidence": validation_result.confidence
        }
        if request_context:
            event_data.update(request_context)
            
        event_bus.emit(EventTypes.TRIGGER_EXECUTION_START, event_data, source="TriggerExecutor")
        
        try:
            # Execute trigger action
            response = trigger.action(validation_result)
            
            if response:
                self.logger.info(f"Trigger response: {response.text[:100]}...")
                
                # Handle TTS if requested
                if response.speak:
                    self._handle_tts(response)
                    
                # Emit execution complete event
                event_bus.emit(EventTypes.TRIGGER_EXECUTION_COMPLETE, {
                    "trigger_name": trigger.name,
                    "response": response.to_dict(),
                    "success": True
                }, source="TriggerExecutor")
                
                return response
            else:
                self.logger.warning(f"Trigger {trigger.name} returned no response")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to execute {trigger.name}: {e}", exc_info=True)
            
            # Emit execution error event
            event_bus.emit(EventTypes.TRIGGER_EXECUTION_ERROR, {
                "trigger_name": trigger.name,
                "error": str(e),
                "error_type": type(e).__name__
            }, source="TriggerExecutor")
            
            raise TriggerExecutionError(trigger.name, str(e))
            
    def _handle_tts(self, response: TriggerResponse):
        """Handle text-to-speech synthesis"""
        if not response.text:
            return
            
        tts_enabled = TTS_CONFIG.get("enabled", True)
        
        if self.tts_callback and tts_enabled:
            self.logger.info("Synthesizing speech response")
            try:
                self.tts_callback(response.text, response.voice_settings)
                self.logger.info("Speech synthesis completed")
            except Exception as e:
                self.logger.error(f"Speech synthesis failed: {e}", exc_info=True)
        elif response.speak:
            self.logger.info(f"TTS requested but not available (callback: {self.tts_callback is not None}, enabled: {tts_enabled})")
        else:
            self.logger.debug("Response generated without speech")