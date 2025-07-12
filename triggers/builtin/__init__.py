"""
Built-in triggers for common commands
"""

from .test_trigger import TestTrigger
from .assistant_trigger import AssistantTrigger

# Export only the triggers we want available
__all__ = [
    "TestTrigger",
    "AssistantTrigger",
]