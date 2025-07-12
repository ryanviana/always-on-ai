"""
Trigger validation component
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, Future, wait
from jinja2 import Environment

from .base import BaseTrigger
from .models import ValidationResult, DEFAULT_VALIDATION_TIMEOUT
from .utils import setup_trigger_logger
from events import event_bus, EventTypes


class TriggerValidator:
    """Handles LLM validation of triggers"""
    
    def __init__(self, llm_model: str, template_env: Environment, 
                 max_workers: int = 3, timeout: float = DEFAULT_VALIDATION_TIMEOUT):
        self.logger = setup_trigger_logger("TriggerValidator")
        self.llm_model = llm_model
        self.template_env = template_env
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.timeout = timeout
        
    async def validate_triggers(self, triggers: List[BaseTrigger], context: str, 
                              request_id: str) -> List[Tuple[BaseTrigger, ValidationResult]]:
        """
        Validate multiple triggers concurrently
        
        Args:
            triggers: List of triggers to validate
            context: Conversation context
            request_id: Request ID for tracking
            
        Returns:
            List of tuples containing trigger and validation result
        """
        self.logger.info(f"Starting validation for {len(triggers)} triggers")
        
        # Submit all validation tasks
        validation_futures: Dict[Future, BaseTrigger] = {}
        
        for trigger in triggers:
            self.logger.debug(f"Submitting {trigger.name} for validation")
            
            # Emit validation start event
            event_bus.emit(EventTypes.TRIGGER_VALIDATION_START, {
                "trigger_name": trigger.name,
                "request_id": request_id,
                "context_length": len(context)
            }, source="TriggerValidator")
            
            future = self.executor.submit(self._run_validation, trigger, context)
            validation_futures[future] = trigger
            
        # Wait for all validations to complete
        done, pending = wait(validation_futures.keys(), timeout=self.timeout)
        
        # Cancel any pending validations
        for future in pending:
            future.cancel()
            self.logger.warning(f"Validation timeout for trigger")
            
        # Collect results
        validated_triggers = []
        
        for future in done:
            if future.cancelled():
                continue
                
            trigger = validation_futures[future]
            try:
                result = future.result()
                if result:
                    validated_triggers.append((trigger, result))
                    self.logger.info(f"{trigger.name} validated (confidence: {result.confidence:.2f})")
                    
                    # Emit validation complete event
                    event_bus.emit(EventTypes.TRIGGER_VALIDATION_COMPLETE, {
                        "trigger_name": trigger.name,
                        "request_id": request_id,
                        "confidence": result.confidence,
                        "validated": True,
                        "result": result
                    }, source="TriggerValidator")
                else:
                    self.logger.debug(f"{trigger.name} not validated")
                    
            except Exception as e:
                self.logger.error(f"Error validating {trigger.name}: {e}", exc_info=True)
                
        return validated_triggers
        
    def _run_validation(self, trigger: BaseTrigger, context: str) -> Optional[ValidationResult]:
        """Run validation in a separate thread"""
        loop = None
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run validation
            return loop.run_until_complete(
                trigger.validate_with_llm(context, self.llm_model, self.template_env)
            )
            
        except Exception as e:
            self.logger.error(f"Validation error: {e}", exc_info=True)
            return None
        finally:
            # Always close the loop
            if loop and not loop.is_closed():
                loop.close()
                
    def shutdown(self):
        """Shutdown the validator"""
        self.executor.shutdown(wait=True)