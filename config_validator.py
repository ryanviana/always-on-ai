"""
Configuration validator - Simplified for transcription-only mode
"""

import os


class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""
    pass


def validate_startup_config():
    """Validate configuration before starting the application"""
    # Check for required API key
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigValidationError("OPENAI_API_KEY environment variable is required")
    
    print("✅ Configuration validation passed")