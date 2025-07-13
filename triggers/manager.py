"""
Trigger manager for two-stage trigger processing
"""

import asyncio
import threading
import time
import uuid
from typing import List, Dict, Any, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, Future, wait, as_completed
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from queue import Queue, Empty
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from events import event_bus, EventTypes
from security import InputSanitizer, InputValidationError
from logging_config import get_logger

from .buffer import TranscriptionBuffer
from .base import BaseTrigger
from config import TTS_CONFIG


class TriggerManager:
    """Manages triggers and processes transcriptions through two-stage pipeline"""
    
    def __init__(self, buffer_duration: int = 60, llm_model: str = "gpt-4o-mini", 
                 tts_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 validation_timeout: float = 8.0):
        self.logger = get_logger(__name__)
        self.buffer = TranscriptionBuffer(duration_seconds=buffer_duration)
        self.triggers: List[BaseTrigger] = []
        self.llm_model = llm_model
        self.validation_timeout = validation_timeout
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._validation_tasks = []
        self.tts_callback = tts_callback  # Callback for TTS synthesis
        
        # Request tracking for proper ordering
        self._request_queue = Queue()
        self._active_requests = {}  # Track active validation tasks
        self._request_counter = 0
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
        print(f"Added trigger: {trigger}")
        
    def remove_trigger(self, trigger_name: str):
        """Remove a trigger by name"""
        self.triggers = [t for t in self.triggers if t.name != trigger_name]
        
    def get_triggers(self) -> List[BaseTrigger]:
        """Get all registered triggers"""
        return self.triggers.copy()
        
    def process_transcription(self, text: str):
        """Process a new transcription through the trigger pipeline"""
        # Sanitize input text for security
        try:
            text = InputSanitizer.sanitize_text(text, input_type='voice_command', strict=False)
            if not text.strip():
                self.logger.debug("Empty text after sanitization, skipping trigger processing")
                return
        except InputValidationError as e:
            self.logger.warning(f"Input validation failed: {e}")
            return
        
        # Add to buffer
        self.buffer.add(text)
        
        # Stage 1: Check keywords for all triggers
        matching_triggers = []
        for trigger in self.triggers:
            if trigger.enabled and trigger.check_keywords(text):
                print(f"Keywords detected for {trigger.name}, validating...")
                matching_triggers.append(trigger)
                
                # Emit keyword match event
                event_bus.emit(EventTypes.TRIGGER_KEYWORD_MATCH, {
                    "trigger_name": trigger.name,
                    "text": text,
                    "keywords": trigger.keywords,
                    "priority": trigger.priority
                }, source="TriggerManager")
                
        # Stage 2: Queue validation request if triggers matched
        if matching_triggers:
            request_id = str(uuid.uuid4())
            timestamp = time.time()
            self._request_counter += 1
            
            # Cancel any pending validations to avoid out-of-order responses
            self._cancel_pending_validations()
            
            # Queue the new request
            request = {
                'id': request_id,
                'text': text,
                'triggers': matching_triggers,
                'timestamp': timestamp,
                'number': self._request_counter
            }
            
            print(f"[QUEUE] Adding request #{self._request_counter}: {text[:30]}...")
            self._request_queue.put(request)
                
    def _cancel_pending_validations(self):
        """Cancel any pending validation tasks"""
        # Cancel all active futures and clear the dictionary atomically
        requests_to_cancel = dict(self._active_requests)
        self._active_requests.clear()
        
        for request_id, futures in requests_to_cancel.items():
            for future in futures:
                if not future.done() and not future.cancelled():
                    future.cancel()
            print(f"Cancelled validation futures for request {request_id}")
            
    def _process_request_queue(self):
        """Process queued requests in order"""
        while True:
            try:
                # Get next request with a short timeout
                request = self._request_queue.get(timeout=0.1)
                
                # Check if we should skip this request by looking for newer ones
                # Use a temporary list to check without consuming items
                newer_requests = []
                should_skip = False
                
                # Peek at queue contents without blocking
                try:
                    while True:
                        newer_req = self._request_queue.get_nowait()
                        newer_requests.append(newer_req)
                        # If we find a newer request, we should skip the current one
                        if newer_req['number'] > request['number']:
                            should_skip = True
                except Empty:
                    pass
                
                # Put back all the newer requests we found
                for req in newer_requests:
                    self._request_queue.put(req)
                
                if should_skip:
                    print(f"Skipping request {request['number']} as newer requests exist")
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
                print(f"Error processing request queue: {e}")
                
    def _validate_and_execute_best(self, request_id: str, triggers: List[BaseTrigger], 
                                   text: str, timestamp: float):
        """Validate all triggers and execute only the best one"""
        context = self.buffer.get_context()
        
        # Submit all validation tasks
        validation_futures = {}
        futures_list = []
        
        for trigger in triggers:
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
        self._active_requests[request_id] = futures_list
        
        # Wait for all validations to complete
        done, pending = wait(validation_futures.keys(), timeout=self.validation_timeout)
        
        # Cancel any pending validations
        for future in pending:
            future.cancel()
            
        # Check if this request is still the latest
        if self._request_queue.qsize() > 0:
            print(f"Newer requests detected, cancelling execution for request {request_id}")
            # Properly cancel all futures before cleanup
            if request_id in self._active_requests:
                futures_to_cancel = self._active_requests[request_id]
                for future in futures_to_cancel:
                    if not future.done():
                        future.cancel()
                del self._active_requests[request_id]
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
                    validated_triggers.append((trigger, result, confidence))
                    print(f"Trigger {trigger.name} validated with confidence {confidence}")
                    
                    # Emit validation complete event
                    event_bus.emit(EventTypes.TRIGGER_VALIDATION_COMPLETE, {
                        "trigger_name": trigger.name,
                        "request_id": request_id,
                        "confidence": confidence,
                        "validated": True,
                        "result": result
                    }, source="TriggerManager")
            except Exception as e:
                print(f"Error validating trigger {trigger.name}: {e}")
                
        # Execute only the best trigger (highest priority + confidence)
        if validated_triggers:
            # Sort by priority and confidence
            best_trigger, best_result, _ = max(
                validated_triggers, 
                key=lambda x: (x[0].priority, x[2])
            )
            
            print(f"Executing best trigger: {best_trigger.name} for query: {text[:50]}...")
            # Include original text in validation result for better tracking
            best_result['_original_query'] = text
            best_result['_request_timestamp'] = timestamp
            self._execute_trigger(best_trigger, best_result)
            
        # Clean up - ensure all futures are properly cancelled and cleaned
        if request_id in self._active_requests:
            futures_to_cleanup = self._active_requests[request_id]
            for future in futures_to_cleanup:
                if not future.done() and not future.cancelled():
                    future.cancel()
            del self._active_requests[request_id]
        
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
            print(f"Error in trigger validation: {e}")
            return None
        finally:
            # Always close the loop to prevent resource leaks
            if loop and not loop.is_closed():
                loop.close()
            
    def _execute_trigger(self, trigger: BaseTrigger, validation_result: Dict[str, Any]):
        """Execute a validated trigger action"""
        print(f"Trigger {trigger.name} validated! Executing action...")
        
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
            if response and self.tts_callback and TTS_CONFIG.get("enabled", True):
                text = response.get("text")
                speak = response.get("speak", True)
                voice_settings = response.get("voice_settings", {})
                
                if text and speak:
                    print(f"Speaking response: {text}")
                    self.tts_callback(text, voice_settings)
                    
        except Exception as e:
            print(f"Error executing trigger {trigger.name}: {e}")
            
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