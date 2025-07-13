"""
Utility functions for the trigger system
"""

import json
from typing import Dict, Any, Optional
import logging
from .exceptions import TriggerException


def parse_llm_json_response(response_text: str) -> Dict[str, Any]:
    """
    Parse JSON response from LLM, handling common formatting issues
    
    Args:
        response_text: Raw response text from LLM
        
    Returns:
        Parsed JSON as dictionary
        
    Raises:
        TriggerException: If JSON parsing fails
    """
    if not response_text:
        raise TriggerException("Empty response from LLM")
    
    # Clean up common LLM response formatting
    cleaned_text = response_text.strip()
    
    # Remove markdown code blocks if present
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
        
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
        
    cleaned_text = cleaned_text.strip()
    
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        # Try to extract JSON from the text
        import re
        json_match = re.search(r'\{[^{}]*\}', cleaned_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        raise TriggerException(
            f"Failed to parse JSON response: {e}", 
            details={"response_text": response_text, "cleaned_text": cleaned_text}
        )


def setup_trigger_logger(name: str) -> logging.Logger:
    """
    Setup a logger for trigger components
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger
    """
    try:
        from core.logging_config import get_logger
        return get_logger(name)
    except ImportError:
        # Fallback to basic logger if logging_config not available
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(levelname)s] [%(name)s] %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger


def sanitize_trigger_name(name: str) -> str:
    """
    Sanitize trigger name for use in logs and events
    
    Args:
        name: Raw trigger name
        
    Returns:
        Sanitized name
    """
    # Remove any special characters that might cause issues
    return name.replace(" ", "_").replace("-", "_").lower()


def calculate_confidence_score(validation_result: Dict[str, Any], 
                             trigger_priority: int) -> float:
    """
    Calculate adjusted confidence score based on validation result and trigger priority
    
    Args:
        validation_result: Raw validation result from LLM
        trigger_priority: Trigger priority (0-100)
        
    Returns:
        Adjusted confidence score (0.0-1.0)
    """
    base_confidence = validation_result.get('confidence', 0.5)
    
    # Apply small boost based on priority (max 10% boost)
    priority_boost = (trigger_priority / 100) * 0.1
    
    # Ensure we stay within 0-1 range
    return min(1.0, base_confidence + priority_boost)