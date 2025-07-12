"""
Trigger processing pipeline orchestrator
"""

from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .base import BaseTrigger
from .buffer import TranscriptionBuffer
from .validator import TriggerValidator
from .executor import TriggerExecutor
from .request_queue import RequestQueue, TriggerRequest
from .models import ValidationResult, DEFAULT_BUFFER_DURATION, DEFAULT_LLM_MODEL, DEFAULT_VALIDATION_TIMEOUT
from .utils import setup_trigger_logger
from security import InputSanitizer, InputValidationError
from events import event_bus, EventTypes


class TriggerPipeline:
    """
    Orchestrates the trigger processing flow
    
    This class coordinates the two-stage trigger pipeline:
    1. Keyword matching
    2. LLM validation and execution
    """
    
    def __init__(self, 
                 buffer_duration: int = DEFAULT_BUFFER_DURATION,
                 llm_model: str = DEFAULT_LLM_MODEL,
                 validation_timeout: float = DEFAULT_VALIDATION_TIMEOUT,
                 tts_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        self.logger = setup_trigger_logger("TriggerPipeline")
        
        # Initialize components
        self.buffer = TranscriptionBuffer(duration_seconds=buffer_duration)
        self.triggers: List[BaseTrigger] = []
        
        # Setup template environment
        template_dir = Path(__file__).parent.parent / "templates" / "triggers"
        template_env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Initialize sub-components
        self.validator = TriggerValidator(llm_model, template_env, timeout=validation_timeout)
        self.executor = TriggerExecutor(tts_callback)
        self.request_queue = RequestQueue(self._process_request)
        
        # Start request processing
        self.request_queue.start()
        
    def add_trigger(self, trigger: BaseTrigger):
        """Add a trigger to the pipeline"""
        self.triggers.append(trigger)
        self.logger.info(f"Added trigger: {trigger}")
        
    def remove_trigger(self, trigger_name: str):
        """Remove a trigger by name"""
        self.triggers = [t for t in self.triggers if t.name != trigger_name]
        self.logger.info(f"Removed trigger: {trigger_name}")
        
    def get_triggers(self) -> List[BaseTrigger]:
        """Get all registered triggers"""
        return self.triggers.copy()
        
    def process_transcription(self, text: str):
        """
        Process a new transcription through the trigger pipeline
        
        Args:
            text: Transcription text to process
        """
        self.logger.info(f"Processing transcription: '{text}'")
        
        # Stage 1: Sanitize and validate input
        sanitized_text = self._sanitize_input(text)
        if not sanitized_text:
            return
            
        # Add to buffer
        self.buffer.add(sanitized_text)
        self.logger.debug(f"Added to buffer. Buffer size: {len(self.buffer)}")
        
        # Stage 2: Check keywords
        matching_triggers = self._check_keywords(sanitized_text)
        
        if matching_triggers:
            # Stage 3: Queue for LLM validation
            self.logger.info(f"Found {len(matching_triggers)} matching triggers, queuing for validation")
            self.request_queue.add_request(
                sanitized_text, 
                matching_triggers,
                metadata={"original_text": text}
            )
        else:
            self.logger.info("No triggers matched")
            
    def _sanitize_input(self, text: str) -> Optional[str]:
        """Sanitize input text for security"""
        try:
            original_text = text
            text = InputSanitizer.sanitize_text(text, input_type='voice_command', strict=False)
            
            if not text.strip():
                self.logger.debug("Empty text after sanitization")
                return None
                
            if original_text != text:
                self.logger.debug(f"Text sanitized: '{original_text}' → '{text}'")
                
            return text
            
        except InputValidationError as e:
            self.logger.warning(f"Input validation failed: {e}")
            return None
            
    def _check_keywords(self, text: str) -> List[BaseTrigger]:
        """Check keywords for all triggers"""
        self.logger.info(f"Checking keywords against {len(self.triggers)} triggers")
        matching_triggers = []
        
        for trigger in self.triggers:
            if not trigger.enabled:
                self.logger.debug(f"{trigger.name}: DISABLED")
                continue
                
            if trigger.check_keywords(text):
                self.logger.info(f"{trigger.name}: Keywords matched (priority: {trigger.priority})")
                matching_triggers.append(trigger)
                
                # Emit keyword match event
                event_bus.emit(EventTypes.TRIGGER_KEYWORD_MATCH, {
                    "trigger_name": trigger.name,
                    "text": text,
                    "keywords": trigger.keywords,
                    "priority": trigger.priority
                }, source="TriggerPipeline")
            else:
                self.logger.debug(f"{trigger.name}: No keywords matched")
                
        return matching_triggers
        
    def _process_request(self, request: TriggerRequest):
        """Process a trigger request"""
        context = self.buffer.get_context()
        self.logger.info(f"Validating {len(request.triggers)} triggers")
        
        # Validate triggers - run async method in sync context
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            validated_triggers = loop.run_until_complete(
                self.validator.validate_triggers(
                    request.triggers, 
                    context, 
                    request.id
                )
            )
        finally:
            loop.close()
        
        if validated_triggers:
            # Select and execute best trigger
            best_trigger, best_result = self._select_best_trigger(validated_triggers)
            
            self.logger.info(f"Selected {best_trigger.name} for execution")
            
            # Add request context
            request_context = {
                "original_query": request.text,
                "request_timestamp": request.timestamp
            }
            
            # Execute trigger
            self.executor.execute_trigger(best_trigger, best_result, request_context)
        else:
            self.logger.info("No triggers validated")
            
    def _select_best_trigger(self, validated_triggers: List[Tuple[BaseTrigger, ValidationResult]]) -> Tuple[BaseTrigger, ValidationResult]:
        """Select the best trigger based on priority and confidence"""
        # Sort by priority and confidence
        best = max(
            validated_triggers,
            key=lambda x: (x[0].priority, x[1].confidence)
        )
        
        if len(validated_triggers) > 1:
            other_triggers = [f"{t[0].name}({t[1].confidence:.2f})" 
                            for t in validated_triggers if t[0] != best[0]]
            self.logger.debug(f"Other candidates: {', '.join(other_triggers)}")
            
        return best
        
    def get_context(self, duration_seconds: Optional[int] = None) -> str:
        """Get the current conversation context"""
        return self.buffer.get_context(duration_seconds)
        
    def clear_buffer(self):
        """Clear the transcription buffer"""
        self.buffer.clear()
        
    def shutdown(self):
        """Shutdown the pipeline"""
        self.logger.info("Shutting down trigger pipeline")
        
        # Stop request processing
        self.request_queue.stop()
        
        # Shutdown validator
        self.validator.shutdown()
        
        self.logger.info("Trigger pipeline shutdown complete")