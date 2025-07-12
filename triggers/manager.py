"""
Trigger manager for two-stage trigger processing
"""

import asyncio
import threading
import time
import uuid
from typing import List, Dict, Any, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, Future, wait
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from queue import Queue, Empty

from .buffer import TranscriptionBuffer
from .base import BaseTrigger
from .models import RequestContext, ValidationResult, DEFAULT_VALIDATION_TIMEOUT, DEFAULT_BUFFER_DURATION, DEFAULT_LLM_MODEL, DEFAULT_MAX_WORKERS
from .utils import setup_trigger_logger

# Import from project root
from events import event_bus, EventTypes
from security import InputSanitizer, InputValidationError
from config import TTS_CONFIG


class TriggerManager:
    """Manages triggers and processes transcriptions through two-stage pipeline"""
    
    def __init__(self, buffer_duration: int = DEFAULT_BUFFER_DURATION, 
                 llm_model: str = DEFAULT_LLM_MODEL, 
                 tts_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 validation_timeout: float = DEFAULT_VALIDATION_TIMEOUT):
        self.logger = setup_trigger_logger("TriggerManager")
        self.buffer = TranscriptionBuffer(duration_seconds=buffer_duration)
        self.triggers: List[BaseTrigger] = []
        self.llm_model = llm_model
        self.validation_timeout = validation_timeout
        self.executor = ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS)
        self._validation_tasks = []
        self.tts_callback = tts_callback  # Callback for TTS synthesis
        
        # Request tracking for proper ordering
        self._request_queue = Queue()
        self._active_requests = {}  # Track active validation tasks
        self._request_counter = 0
        self._latest_request_number = 0  # Track the latest request number
        self._request_id_to_number = {}  # Map request IDs to request numbers
        self._request_lock = threading.Lock()  # Thread safety for request tracking
        self._processing_thread = threading.Thread(target=self._process_request_queue, daemon=True)
        self._processing_thread.start()
        
        # Setup jinja2 template environment
        template_dir = Path(__file__).parent.parent / "templates" / "triggers"
        self.template_env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
    def add_trigger(self, trigger: BaseTrigger):
        """Add a trigger to the manager"""
        self.triggers.append(trigger)
        self.logger.info(f"Added trigger: {trigger}")
        
    def remove_trigger(self, trigger_name: str):
        """Remove a trigger by name"""
        self.triggers = [t for t in self.triggers if t.name != trigger_name]
        
    def get_triggers(self) -> List[BaseTrigger]:
        """Get all registered triggers"""
        return self.triggers.copy()
        
    def process_transcription(self, text: str):
        """Process a new transcription through the trigger pipeline"""
        self.logger.info(f"🎯 TRIGGER PIPELINE: Processing transcription: '{text}'")
        
        # Sanitize input text for security
        try:
            original_text = text
            text = InputSanitizer.sanitize_text(text, input_type='voice_command', strict=False)
            if not text.strip():
                self.logger.debug("Empty text after sanitization, skipping trigger processing")
                return
            if original_text != text:
                self.logger.debug(f"Text sanitized: '{original_text}' → '{text}'")
        except InputValidationError as e:
            self.logger.warning(f"Input validation failed: {e}")
            return
        
        # Add to buffer
        self.buffer.add(text)
        self.logger.debug(f"Added to buffer. Buffer now has {len(self.buffer)} entries")
        
        # Stage 1: Check keywords for all triggers
        self.logger.info(f"📝 STAGE 1: Checking keywords against {len(self.triggers)} triggers...")
        matching_triggers = []
        
        for trigger in self.triggers:
            if not trigger.enabled:
                self.logger.debug(f"  ⏭️ {trigger.name}: DISABLED (skipping)")
                continue
                
            keyword_match = trigger.check_keywords(text)
            if keyword_match:
                self.logger.info(f"  ✅ {trigger.name}: KEYWORDS MATCHED (priority: {trigger.priority})")
                self.logger.debug(f"     Keywords: {trigger.keywords}")
                matching_triggers.append(trigger)
                
                # Emit keyword match event
                event_bus.emit(EventTypes.TRIGGER_KEYWORD_MATCH, {
                    "trigger_name": trigger.name,
                    "text": text,
                    "keywords": trigger.keywords,
                    "priority": trigger.priority
                }, source="TriggerManager")
            else:
                self.logger.debug(f"  ❌ {trigger.name}: No keywords matched")
                
        # Stage 2: Queue validation request if triggers matched
        if matching_triggers:
            request_id = str(uuid.uuid4())
            timestamp = time.time()
            
            with self._request_lock:
                self._request_counter += 1
                current_request_number = self._request_counter
                self._latest_request_number = current_request_number
                self._request_id_to_number[request_id] = current_request_number
            
            self.logger.info(f"🧠 STAGE 2: {len(matching_triggers)} triggers matched, queuing LLM validation...")
            for trigger in matching_triggers:
                self.logger.info(f"  → {trigger.name} (priority: {trigger.priority})")
            
            # Cancel any pending validations to avoid out-of-order responses
            self._cancel_pending_validations()
            
            # Queue the new request
            request = {
                'id': request_id,
                'text': text,
                'triggers': matching_triggers,
                'timestamp': timestamp,
                'number': current_request_number
            }
            
            self.logger.info(f"📋 QUEUE: Adding validation request #{current_request_number}")
            self._request_queue.put(request)
        else:
            self.logger.info("⏭️ STAGE 1 RESULT: No triggers matched - pipeline complete")
                
    def _cancel_pending_validations(self):
        """Cancel any pending validation tasks"""
        # Cancel all active futures and clear the dictionary atomically
        requests_to_cancel = dict(self._active_requests)
        self._active_requests.clear()
        
        for request_id, futures in requests_to_cancel.items():
            for future in futures:
                if not future.done() and not future.cancelled():
                    future.cancel()
            self.logger.debug(f"Cancelled validation futures for request {request_id}")
            
    def _process_request_queue(self):
        """Process queued requests in order"""
        while True:
            try:
                # Get next request with a short timeout
                request = self._request_queue.get(timeout=0.1)
                
                # Check if this request is still the latest by comparing request numbers
                with self._request_lock:
                    is_latest = request['number'] == self._latest_request_number
                
                if not is_latest:
                    self.logger.debug(f"Skipping request {request['number']} as newer request {self._latest_request_number} exists")
                    continue
                    
                # Process this request
                self._validate_and_execute_best(
                    request['id'],
                    request['triggers'],
                    request['text'],
                    request['timestamp']
                )
                
            except Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error processing request queue: {e}", exc_info=True)
                
    def _validate_and_execute_best(self, request_id: str, triggers: List[BaseTrigger], 
                                   text: str, timestamp: float):
        """Validate all triggers and execute only the best one"""
        context = self.buffer.get_context()
        self.logger.info(f"🔍 LLM VALIDATION: Starting validation for {len(triggers)} triggers")
        self.logger.debug(f"Context length: {len(context)} chars, Request: '{text}'")
        
        # Submit all validation tasks
        validation_futures = {}
        futures_list = []
        
        for trigger in triggers:
            self.logger.info(f"  🤖 {trigger.name}: Submitting to LLM ({self.llm_model})...")
            
            # Emit validation start event
            event_bus.emit(EventTypes.TRIGGER_VALIDATION_START, {
                "trigger_name": trigger.name,
                "request_id": request_id,
                "context_length": len(context)
            }, source="TriggerManager")
            
            future = self.executor.submit(self._run_validation_only, trigger, context)
            validation_futures[future] = trigger
            futures_list.append(future)
            
        # Store active futures for this request
        with self._request_lock:
            self._active_requests[request_id] = futures_list
        
        # Wait for all validations to complete
        done, pending = wait(validation_futures.keys(), timeout=self.validation_timeout)
        
        # Cancel any pending validations
        for future in pending:
            future.cancel()
            
        # Check if newer requests have arrived during validation
        with self._request_lock:
            request_number = self._request_id_to_number.get(request_id, 0)
            is_latest = request_number == self._latest_request_number
        
        if not is_latest:
            self.logger.info(f"⏭️ Newer requests detected, cancelling execution for request {request_id}")
            # Properly cancel all futures before cleanup
            if request_id in self._active_requests:
                futures_to_cancel = self._active_requests[request_id]
                for future in futures_to_cancel:
                    if not future.done():
                        future.cancel()
                del self._active_requests[request_id]
            # Clean up request tracking
            with self._request_lock:
                self._request_id_to_number.pop(request_id, None)
            return
            
        # Collect validated triggers with their results
        validated_triggers = []
        for future in done:
            if future.cancelled():
                continue
                
            trigger = validation_futures[future]
            try:
                result = future.result()
                if result:
                    confidence = result.get('confidence', 0.5)
                    reason = result.get('reason', 'No reason provided')
                    validated_triggers.append((trigger, result, confidence))
                    self.logger.info(f"  ✅ {trigger.name}: VALIDATED (confidence: {confidence:.2f})")
                    self.logger.debug(f"     Reason: {reason}")
                    
                    # Emit validation complete event
                    event_bus.emit(EventTypes.TRIGGER_VALIDATION_COMPLETE, {
                        "trigger_name": trigger.name,
                        "request_id": request_id,
                        "confidence": confidence,
                        "validated": True,
                        "result": result
                    }, source="TriggerManager")
                else:
                    self.logger.info(f"  ❌ {trigger.name}: NOT VALIDATED (LLM rejected)")
            except Exception as e:
                self.logger.error(f"Error validating trigger {trigger.name}: {e}", exc_info=True)
                
        # Execute only the best trigger (highest priority + confidence)
        if validated_triggers:
            # Sort by priority and confidence
            best_trigger, best_result, best_confidence = max(
                validated_triggers, 
                key=lambda x: (x[0].priority, x[2])
            )
            
            self.logger.info(f"🎯 EXECUTION: Selected best trigger: {best_trigger.name}")
            self.logger.info(f"   Priority: {best_trigger.priority}, Confidence: {best_confidence:.2f}")
            if len(validated_triggers) > 1:
                other_triggers = [f"{t[0].name}({t[2]:.2f})" for t in validated_triggers if t[0] != best_trigger]
                self.logger.debug(f"   Other candidates: {', '.join(other_triggers)}")
            
            # Include original text in validation result for better tracking
            best_result['_original_query'] = text
            best_result['_request_timestamp'] = timestamp
            self._execute_trigger(best_trigger, best_result)
        else:
            self.logger.info("⏭️ VALIDATION RESULT: No triggers validated - pipeline complete")
            
        # Clean up - ensure all futures are properly cancelled and cleaned
        if request_id in self._active_requests:
            futures_to_cleanup = self._active_requests[request_id]
            for future in futures_to_cleanup:
                if not future.done() and not future.cancelled():
                    future.cancel()
            del self._active_requests[request_id]
        
        # Clean up request tracking to prevent memory leak
        with self._request_lock:
            self._request_id_to_number.pop(request_id, None)
        
    def _run_validation_only(self, trigger: BaseTrigger, context: str) -> Optional[Dict[str, Any]]:
        """Run validation only (without execution) in a separate thread"""
        loop = None
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run validation with template environment
            validation_result = loop.run_until_complete(
                trigger.validate_with_llm(context, self.llm_model, self.template_env)
            )
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Error in trigger validation: {e}", exc_info=True)
            return None
        finally:
            # Always close the loop to prevent resource leaks
            if loop and not loop.is_closed():
                loop.close()
            
    def _execute_trigger(self, trigger: BaseTrigger, validation_result: Dict[str, Any]):
        """Execute a validated trigger action"""
        self.logger.info(f"🚀 ACTION: Executing {trigger.name} trigger...")
        
        # Emit execution start event
        event_bus.emit(EventTypes.TRIGGER_EXECUTION_START, {
            "trigger_name": trigger.name,
            "original_query": validation_result.get('_original_query', ''),
            "confidence": validation_result.get('confidence', 0.5)
        }, source="TriggerManager")
        
        try:
            response = trigger.action(validation_result)
            
            # Emit execution complete event
            event_bus.emit(EventTypes.TRIGGER_EXECUTION_COMPLETE, {
                "trigger_name": trigger.name,
                "response": response,
                "success": True
            }, source="TriggerManager")
        
            # Handle TTS response if available
            if response:
                response_text = response.get("text")
                should_speak = response.get("speak", True)
                voice_settings = response.get("voice_settings", {})
                
                if response_text:
                    self.logger.info(f"📝 RESPONSE: {response_text}")
                    
                    if should_speak and self.tts_callback and TTS_CONFIG.get("enabled", True):
                        self.logger.info(f"🔊 TTS: Synthesizing speech...")
                        try:
                            self.tts_callback(response_text, voice_settings)
                            self.logger.info(f"✅ TTS: Speech synthesis completed")
                        except Exception as e:
                            self.logger.error(f"❌ TTS: Speech synthesis failed: {e}", exc_info=True)
                    elif should_speak:
                        self.logger.info(f"⏭️ TTS: Speech requested but TTS not available (callback: {self.tts_callback is not None}, enabled: {TTS_CONFIG.get('enabled', True)})")
                    else:
                        self.logger.debug(f"📝 TTS: Response generated but speech not requested")
                    
        except Exception as e:
            self.logger.error(f"❌ ACTION ERROR: Failed to execute {trigger.name}: {e}", exc_info=True)
            
            # Emit execution error event
            event_bus.emit(EventTypes.TRIGGER_EXECUTION_ERROR, {
                "trigger_name": trigger.name,
                "error": str(e),
                "error_type": type(e).__name__
            }, source="TriggerManager")
            
    def get_context(self, duration_seconds: int = None) -> str:
        """Get the current conversation context"""
        return self.buffer.get_context(duration_seconds)
        
    def clear_buffer(self):
        """Clear the transcription buffer"""
        self.buffer.clear()
        
    def shutdown(self):
        """Shutdown the trigger manager"""
        # Cancel all pending validations
        self._cancel_pending_validations()
        
        # Clear the request queue
        while not self._request_queue.empty():
            try:
                self._request_queue.get_nowait()
            except Empty:
                break
                
        # Wait for pending validations
        for task in self._validation_tasks:
            task.cancel()
            
        self.executor.shutdown(wait=True)