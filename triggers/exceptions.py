"""
Custom exceptions for the trigger system
"""

from typing import Optional, Dict, Any


class TriggerException(Exception):
    """Base exception for all trigger-related errors"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class TriggerValidationError(TriggerException):
    """Raised when trigger validation fails"""
    def __init__(self, trigger_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.trigger_name = trigger_name
        super().__init__(f"Validation failed for {trigger_name}: {message}", details)


class TriggerExecutionError(TriggerException):
    """Raised when trigger execution fails"""
    def __init__(self, trigger_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.trigger_name = trigger_name
        super().__init__(f"Execution failed for {trigger_name}: {message}", details)


class TriggerConfigurationError(TriggerException):
    """Raised when trigger configuration is invalid"""
    pass


class TriggerTimeoutError(TriggerException):
    """Raised when trigger validation or execution times out"""
    def __init__(self, trigger_name: str, timeout: float):
        self.trigger_name = trigger_name
        self.timeout = timeout
        super().__init__(f"Trigger {trigger_name} timed out after {timeout}s")


class LLMConnectionError(TriggerException):
    """Raised when connection to LLM fails"""
    pass


class TemplateRenderError(TriggerException):
    """Raised when template rendering fails"""
    pass