"""
Tool execution manager for centralized tool operations
"""

import json
import asyncio
import time
import threading
from typing import Dict, Any, Optional, Callable, List
from logging import Logger

from .tools.base import RealtimeTool
from .tools.registry import ToolRegistry
from events import event_bus, EventTypes


class ToolExecutionManager:
    """Manages tool execution, events, and lifecycle"""
    
    def __init__(self, 
                 tool_registry: ToolRegistry,
                 session_id: Optional[str] = None,
                 logger: Optional[Logger] = None):
        """
        Initialize tool execution manager
        
        Args:
            tool_registry: Registry containing available tools
            session_id: Optional session ID for event tracking
            logger: Optional logger instance
        """
        self.tool_registry = tool_registry
        self.session_id = session_id
        self.logger = logger
        
        # Track executed function calls to prevent duplicates (thread-safe)
        self.executed_function_calls = set()
        self._execution_lock = threading.Lock()
        
        # Tool execution statistics (thread-safe)
        self.execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "execution_times": {}
        }
        self._stats_lock = threading.Lock()
        
    def set_session_id(self, session_id: str):
        """Update the session ID for event tracking"""
        self.session_id = session_id
        
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Get schemas for all registered tools
        
        Returns:
            List of tool schemas in OpenAI format
        """
        return self.tool_registry.get_schemas()
        
    def get_tool_metadata(self, tool_name: str) -> Dict[str, Any]:
        """
        Get metadata for a specific tool
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Dict containing tool metadata
        """
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return {}
            
        return {
            "name": tool_name,
            "estimated_duration": tool.estimated_duration,
            "feedback_message": tool.feedback_message,
            "category": tool.category,
            "configuration_schema": tool.configuration_schema
        }
        
    def estimate_tool_duration(self, tool_name: str) -> float:
        """
        Get estimated execution duration for a tool
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Estimated duration in seconds
        """
        tool = self.tool_registry.get(tool_name)
        return tool.estimated_duration if tool else 2.0
        
    def get_tool_feedback_message(self, tool_name: str) -> str:
        """
        Get feedback message for a tool
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Feedback message string
        """
        tool = self.tool_registry.get(tool_name)
        return tool.feedback_message if tool else f"Processando {tool_name}..."
        
    async def execute_tool(self, 
                          call_id: str, 
                          tool_name: str, 
                          arguments_json: str,
                          response_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        Execute a tool with full lifecycle management
        
        Args:
            call_id: Unique identifier for this tool call
            tool_name: Name of the tool to execute
            arguments_json: JSON string of arguments
            response_callback: Optional callback to send response back to session
            
        Returns:
            Dict containing the execution result
        """
        # Check for duplicate execution (thread-safe)
        with self._execution_lock:
            if call_id in self.executed_function_calls:
                if self.logger:
                    self.logger.warning(f"Duplicate tool execution attempt: {call_id}")
                return {"error": "Tool call already executed"}
                
            # Mark as executed
            self.executed_function_calls.add(call_id)
        
        # Parse arguments
        try:
            arguments = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON arguments: {str(e)}"
            self._emit_tool_error(call_id, tool_name, error_msg)
            return {"error": error_msg}
            
        # Get tool instance
        tool = self.tool_registry.get(tool_name)
        if not tool:
            error_msg = f"Tool '{tool_name}' not found"
            self._emit_tool_error(call_id, tool_name, error_msg)
            return {"error": error_msg}
            
        # Validate tool configuration
        if not tool.validate_config():
            error_msg = f"Tool '{tool_name}' has invalid configuration"
            self._emit_tool_error(call_id, tool_name, error_msg)
            return {"error": error_msg}
            
        # Start execution tracking (thread-safe)
        start_time = time.time()
        with self._stats_lock:
            self.execution_stats["total_executions"] += 1
        
        # Emit start events
        self._emit_tool_start(call_id, tool_name, arguments_json)
        self._emit_tool_processing_start(call_id, tool_name)
        
        if self.logger:
            self.logger.info(f"Executing tool: {tool_name} with args: {arguments_json}")
            
        try:
            # Call before_execute hook
            await tool.before_execute(arguments)
            
            # Execute the tool
            if asyncio.iscoroutinefunction(tool.execute):
                result = await tool.execute(arguments)
            else:
                # Handle sync tools - run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, tool.execute, arguments)
                
            # Call after_execute hook
            await tool.after_execute(arguments, result)
            
            # Calculate execution time (thread-safe)
            execution_time = time.time() - start_time
            with self._stats_lock:
                self.execution_stats["successful_executions"] += 1
                self.execution_stats["execution_times"][tool_name] = execution_time
            
            # Emit completion events
            self._emit_tool_processing_end(call_id, tool_name)
            self._emit_tool_complete(call_id, tool_name, result)
            
            if self.logger:
                self.logger.info(f"Tool {tool_name} executed successfully in {execution_time:.2f}s")
                
            # Send response back if callback provided
            if response_callback:
                response = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result)
                    }
                }
                response_callback(response)
                
            return result
            
        except Exception as e:
            # Calculate execution time even on error (thread-safe)
            execution_time = time.time() - start_time
            with self._stats_lock:
                self.execution_stats["failed_executions"] += 1
            
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Emit error events
            self._emit_tool_processing_end(call_id, tool_name, error=True)
            self._emit_tool_error(call_id, tool_name, error_msg, error_type)
            
            if self.logger:
                self.logger.error(f"Tool {tool_name} execution failed after {execution_time:.2f}s: {error_msg}")
                
            # Send error response back if callback provided
            if response_callback:
                error_response = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"error": error_msg})
                    }
                }
                response_callback(error_response)
                
            return {"error": error_msg, "error_type": error_type}
            
    def _emit_tool_start(self, call_id: str, tool_name: str, arguments_json: str):
        """Emit tool call start event"""
        event_bus.emit(EventTypes.TOOL_CALL_START, {
            "tool_name": tool_name,
            "call_id": call_id,
            "arguments": arguments_json,
            "session_id": self.session_id
        }, source="ToolExecutionManager")
        
    def _emit_tool_processing_start(self, call_id: str, tool_name: str):
        """Emit tool processing start event"""
        estimated_duration = self.estimate_tool_duration(tool_name)
        event_bus.emit(EventTypes.TOOL_PROCESSING_START, {
            "tool_name": tool_name,
            "call_id": call_id,
            "estimated_duration": estimated_duration,
            "session_id": self.session_id
        }, source="ToolExecutionManager")
        
    def _emit_tool_processing_end(self, call_id: str, tool_name: str, error: bool = False):
        """Emit tool processing end event"""
        event_bus.emit(EventTypes.TOOL_PROCESSING_END, {
            "tool_name": tool_name,
            "call_id": call_id,
            "session_id": self.session_id,
            "error": error
        }, source="ToolExecutionManager")
        
    def _emit_tool_complete(self, call_id: str, tool_name: str, result: Dict[str, Any]):
        """Emit tool call complete event"""
        event_bus.emit(EventTypes.TOOL_CALL_COMPLETE, {
            "tool_name": tool_name,
            "call_id": call_id,
            "result": result,
            "success": True,
            "session_id": self.session_id
        }, source="ToolExecutionManager")
        
    def _emit_tool_error(self, call_id: str, tool_name: str, error: str, error_type: str = "ToolExecutionError"):
        """Emit tool call error event"""
        event_bus.emit(EventTypes.TOOL_CALL_ERROR, {
            "tool_name": tool_name,
            "call_id": call_id,
            "error": error,
            "error_type": error_type,
            "session_id": self.session_id
        }, source="ToolExecutionManager")
        
    def get_execution_stats(self) -> Dict[str, Any]:
        """
        Get tool execution statistics
        
        Returns:
            Dict containing execution statistics
        """
        with self._stats_lock:
            return self.execution_stats.copy()
        
    def reset_stats(self):
        """Reset execution statistics"""
        with self._stats_lock:
            self.execution_stats = {
                "total_executions": 0,
                "successful_executions": 0,
                "failed_executions": 0,
                "execution_times": {}
            }
        
    def clear_executed_calls(self):
        """Clear the executed function calls cache"""
        with self._execution_lock:
            self.executed_function_calls.clear()