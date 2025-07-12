"""
Built-in triggers for common commands
"""

from .test_trigger import TestTrigger

# Export only the triggers we want available
__all__ = [
    "TestTrigger",
]