"""
Security module for input sanitization
"""

import re
from typing import Optional


class InputValidationError(Exception):
    """Exception raised when input validation fails"""
    pass


class InputSanitizer:
    """Provides input sanitization for security"""
    
    # Pattern to remove potentially dangerous characters
    DANGEROUS_PATTERNS = [
        (r'[<>]', ''),  # Remove HTML-like characters
        (r'[\x00-\x1F\x7F-\x9F]', ''),  # Remove control characters
        (r'(\r\n|\r|\n)+', ' '),  # Replace multiple newlines with space
    ]
    
    # Maximum lengths by input type
    MAX_LENGTHS = {
        'voice_command': 1000,
        'text_input': 5000,
        'default': 2000
    }
    
    @classmethod
    def sanitize_text(cls, text: str, input_type: str = 'default', strict: bool = True) -> str:
        """
        Sanitize text input for security
        
        Args:
            text: The text to sanitize
            input_type: Type of input (voice_command, text_input, default)
            strict: Whether to apply strict validation
            
        Returns:
            Sanitized text
            
        Raises:
            InputValidationError: If validation fails in strict mode
        """
        if not text:
            return ""
            
        # Apply maximum length
        max_length = cls.MAX_LENGTHS.get(input_type, cls.MAX_LENGTHS['default'])
        if len(text) > max_length:
            if strict:
                raise InputValidationError(f"Input exceeds maximum length of {max_length} characters")
            text = text[:max_length]
            
        # Apply sanitization patterns
        for pattern, replacement in cls.DANGEROUS_PATTERNS:
            text = re.sub(pattern, replacement, text)
            
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Final validation
        if strict and not text.strip():
            raise InputValidationError("Input is empty after sanitization")
            
        return text.strip()