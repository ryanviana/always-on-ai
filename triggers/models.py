"""
Data models and types for the trigger system
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum, IntEnum


class TriggerPriority(IntEnum):
    """Priority levels for triggers (higher = more priority)"""
    LOW = 0
    MEDIUM_LOW = 25
    MEDIUM = 50
    MEDIUM_HIGH = 75
    HIGH = 100


class TriggerState(Enum):
    """States of a trigger in the pipeline"""
    PENDING = "pending"
    VALIDATING = "validating"
    VALIDATED = "validated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TriggerConfig:
    """Configuration for a trigger"""
    language: str = "pt-BR"
    priority: int = TriggerPriority.MEDIUM
    activation_criteria: List[str] = field(default_factory=list)
    positive_examples: List[str] = field(default_factory=list)
    negative_examples: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    response_schema: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""


@dataclass
class ValidationResult:
    """Result from LLM validation"""
    triggered: bool
    confidence: float
    reason: str
    extracted_intent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationResult':
        """Create ValidationResult from dictionary"""
        return cls(
            triggered=data.get('triggered', False),
            confidence=data.get('confidence', 0.0),
            reason=data.get('reason', ''),
            extracted_intent=data.get('extracted_intent'),
            metadata={k: v for k, v in data.items() 
                     if k not in ['triggered', 'confidence', 'reason', 'extracted_intent']}
        )


@dataclass
class TriggerResponse:
    """Response from trigger action execution"""
    text: str
    speak: bool = True
    voice_settings: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "text": self.text,
            "speak": self.speak,
            "voice_settings": self.voice_settings,
            **self.metadata
        }


@dataclass
class RequestContext:
    """Context for a trigger processing request"""
    request_id: str
    text: str
    timestamp: float
    request_number: int
    conversation_context: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# Constants
DEFAULT_VALIDATION_TIMEOUT = 8.0
DEFAULT_BUFFER_DURATION = 60
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_WORKERS = 3
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 200

# Error messages
ERROR_EMPTY_TEXT = "Empty text after sanitization"
ERROR_VALIDATION_FAILED = "Trigger validation failed"
ERROR_EXECUTION_FAILED = "Trigger execution failed"
ERROR_JSON_PARSE = "Failed to parse JSON response from LLM"