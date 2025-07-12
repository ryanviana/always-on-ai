"""
Request queue management for trigger processing
"""

import threading
import time
import uuid
from queue import Queue, Empty
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from .base import BaseTrigger
from .models import RequestContext
from .utils import setup_trigger_logger


@dataclass
class TriggerRequest:
    """Request for trigger processing"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    triggers: List[BaseTrigger] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    request_number: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class RequestQueue:
    """Manages request queuing and prioritization for trigger processing"""
    
    def __init__(self, process_callback: Callable[[TriggerRequest], None]):
        self.logger = setup_trigger_logger("RequestQueue")
        self._queue = Queue()
        self._request_counter = 0
        self._processing = False
        self._process_callback = process_callback
        self._processing_thread = None
        
    def start(self):
        """Start the request processing thread"""
        if self._processing:
            return
            
        self._processing = True
        self._processing_thread = threading.Thread(
            target=self._process_queue, 
            name="TriggerRequestProcessor",
            daemon=True
        )
        self._processing_thread.start()
        self.logger.info("Request queue processor started")
        
    def stop(self):
        """Stop the request processing thread"""
        self._processing = False
        if self._processing_thread:
            self._processing_thread.join(timeout=2.0)
        self.logger.info("Request queue processor stopped")
        
    def add_request(self, text: str, triggers: List[BaseTrigger], 
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a new request to the queue
        
        Args:
            text: Transcription text
            triggers: List of triggers that matched
            metadata: Optional metadata
            
        Returns:
            Request ID
        """
        self._request_counter += 1
        
        request = TriggerRequest(
            text=text,
            triggers=triggers,
            request_number=self._request_counter,
            metadata=metadata or {}
        )
        
        self.logger.info(f"Adding request #{request.request_number} to queue")
        self._queue.put(request)
        
        return request.id
        
    def clear_queue(self):
        """Clear all pending requests"""
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                count += 1
            except Empty:
                break
                
        if count > 0:
            self.logger.info(f"Cleared {count} pending requests")
            
    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self._queue.qsize()
        
    def _process_queue(self):
        """Process queued requests"""
        while self._processing:
            try:
                # Get next request with timeout
                request = self._queue.get(timeout=0.1)
                
                # Check if we should skip this request
                if self._should_skip_request(request):
                    self.logger.debug(f"Skipping request {request.request_number} as newer requests exist")
                    continue
                    
                # Process the request
                self.logger.info(f"Processing request #{request.request_number}")
                self._process_callback(request)
                
            except Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error processing request: {e}", exc_info=True)
                
    def _should_skip_request(self, request: TriggerRequest) -> bool:
        """Check if request should be skipped due to newer requests"""
        # Peek at queue to see if there are newer requests
        newer_requests = []
        should_skip = False
        
        try:
            # Temporarily remove items to check
            while True:
                newer_req = self._queue.get_nowait()
                newer_requests.append(newer_req)
                if newer_req.request_number > request.request_number:
                    should_skip = True
        except Empty:
            pass
            
        # Put all items back
        for req in newer_requests:
            self._queue.put(req)
            
        return should_skip