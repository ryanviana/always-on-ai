"""
Security hardening module for production deployment.

This module provides security validation, input sanitization, and protection
mechanisms to ensure safe operation in production environments.
"""

import os
import re
import hashlib
import hmac
import secrets
import time
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from functools import wraps
from logging_config import get_logger

logger = get_logger(__name__)


class SecurityError(Exception):
    """Raised when security validation fails"""
    pass


class RateLimitExceeded(SecurityError):
    """Raised when rate limits are exceeded"""
    pass


class InputValidationError(SecurityError):
    """Raised when input validation fails"""
    pass


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10


class RateLimiter:
    """Simple in-memory rate limiter for API protection"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.requests: Dict[str, List[float]] = {}
        
    def is_allowed(self, identifier: str) -> bool:
        """
        Check if request is allowed for given identifier.
        
        Args:
            identifier: Unique identifier (e.g., IP address, user ID)
            
        Returns:
            True if request is allowed, False otherwise
        """
        now = time.time()
        
        # Initialize if new identifier
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        request_times = self.requests[identifier]
        
        # Clean old requests (older than 1 hour)
        cutoff_hour = now - 3600
        request_times[:] = [t for t in request_times if t > cutoff_hour]
        
        # Check hourly limit
        if len(request_times) >= self.config.requests_per_hour:
            return False
        
        # Check per-minute limit
        cutoff_minute = now - 60
        recent_requests = [t for t in request_times if t > cutoff_minute]
        if len(recent_requests) >= self.config.requests_per_minute:
            return False
        
        # Check burst limit (last 10 seconds)
        cutoff_burst = now - 10
        burst_requests = [t for t in request_times if t > cutoff_burst]
        if len(burst_requests) >= self.config.burst_size:
            return False
        
        # Request is allowed
        request_times.append(now)
        return True
    
    def time_until_allowed(self, identifier: str) -> float:
        """
        Get time in seconds until next request is allowed.
        
        Args:
            identifier: Unique identifier
            
        Returns:
            Seconds until next request allowed, 0 if allowed now
        """
        if self.is_allowed(identifier):
            return 0.0
            
        now = time.time()
        request_times = self.requests.get(identifier, [])
        
        # Check which limit is hit
        cutoff_minute = now - 60
        recent_requests = [t for t in request_times if t > cutoff_minute]
        
        if len(recent_requests) >= self.config.requests_per_minute:
            # Hit per-minute limit
            oldest_recent = min(recent_requests)
            return oldest_recent + 60 - now
        
        cutoff_burst = now - 10
        burst_requests = [t for t in request_times if t > cutoff_burst]
        
        if len(burst_requests) >= self.config.burst_size:
            # Hit burst limit
            oldest_burst = min(burst_requests)
            return oldest_burst + 10 - now
        
        # Hit hourly limit
        oldest_request = min(request_times)
        return oldest_request + 3600 - now


class InputSanitizer:
    """Sanitizes and validates user inputs for security"""
    
    # Patterns for potentially dangerous content
    SCRIPT_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'vbscript:',
        r'on\w+\s*=',
    ]
    
    # Maximum lengths for different input types
    MAX_LENGTHS = {
        'text': 10000,
        'voice_command': 500,
        'search_query': 200,
        'username': 50,
        'filename': 255
    }
    
    @classmethod
    def sanitize_text(cls, text: str, input_type: str = 'text', 
                      strict: bool = False) -> str:
        """
        Sanitize text input for security.
        
        Args:
            text: Input text to sanitize
            input_type: Type of input (affects validation rules)
            strict: If True, applies stricter sanitization
            
        Returns:
            Sanitized text
            
        Raises:
            InputValidationError: If input fails validation
        """
        if not isinstance(text, str):
            raise InputValidationError("Input must be a string")
        
        # Check length limits
        max_length = cls.MAX_LENGTHS.get(input_type, cls.MAX_LENGTHS['text'])
        if len(text) > max_length:
            raise InputValidationError(f"Input too long: {len(text)} > {max_length}")
        
        # Check for empty input
        if not text.strip():
            return text.strip()
        
        # Check for script injection patterns
        for pattern in cls.SCRIPT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"Potential script injection detected: {pattern}")
                if strict:
                    raise InputValidationError("Potentially dangerous content detected")
                # Remove the dangerous content
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # For voice commands, only allow safe characters
        if input_type == 'voice_command':
            # Allow letters, numbers, spaces, and common punctuation
            safe_pattern = r'^[a-zA-Z0-9\s\.,!?;:\-áéíóúâêîôûàèìòùãõçÁÉÍÓÚÂÊÎÔÛÀÈÌÒÙÃÕÇ]+$'
            if not re.match(safe_pattern, text):
                if strict:
                    raise InputValidationError("Voice command contains unsafe characters")
                # Remove unsafe characters
                text = re.sub(r'[^a-zA-Z0-9\s\.,!?;:\-áéíóúâêîôûàèìòùãõçÁÉÍÓÚÂÊÎÔÛÀÈÌÒÙÃÕÇ]', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text
    
    @classmethod
    def validate_filename(cls, filename: str) -> str:
        """
        Validate and sanitize filename for safe file operations.
        
        Args:
            filename: Proposed filename
            
        Returns:
            Sanitized filename
            
        Raises:
            InputValidationError: If filename is invalid
        """
        if not filename or not filename.strip():
            raise InputValidationError("Filename cannot be empty")
        
        filename = filename.strip()
        
        # Check length
        if len(filename) > cls.MAX_LENGTHS['filename']:
            raise InputValidationError(f"Filename too long: {len(filename)} > {cls.MAX_LENGTHS['filename']}")
        
        # Prevent directory traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            raise InputValidationError("Filename cannot contain path separators or '..'")
        
        # Remove or replace unsafe characters
        unsafe_chars = r'[<>:"|?*\x00-\x1f]'
        if re.search(unsafe_chars, filename):
            raise InputValidationError("Filename contains unsafe characters")
        
        # Prevent reserved Windows filenames
        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
            'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4',
            'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        
        name_without_ext = filename.split('.')[0].upper()
        if name_without_ext in reserved_names:
            raise InputValidationError(f"Filename cannot be a reserved name: {filename}")
        
        return filename


class APIKeyValidator:
    """Validates API keys and handles secure storage"""
    
    @staticmethod
    def validate_openai_key(api_key: str) -> bool:
        """
        Validate OpenAI API key format.
        
        Args:
            api_key: API key to validate
            
        Returns:
            True if format is valid
        """
        if not api_key or not isinstance(api_key, str):
            return False
        
        # OpenAI keys start with 'sk-' and are typically 51 characters
        if not api_key.startswith('sk-'):
            return False
        
        if len(api_key) < 20 or len(api_key) > 200:
            return False
        
        # Should only contain alphanumeric characters, hyphens, and underscores after 'sk-'
        key_part = api_key[3:]  # Remove 'sk-'
        if not re.match(r'^[a-zA-Z0-9\-_]+$', key_part):
            return False
        
        return True
    
    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """
        Mask API key for safe logging.
        
        Args:
            api_key: API key to mask
            
        Returns:
            Masked version showing only first and last few characters
        """
        if not api_key or len(api_key) < 8:
            return "***"
        
        return f"{api_key[:4]}...{api_key[-4:]}"
    
    @staticmethod
    def validate_environment_security() -> List[str]:
        """
        Validate security aspects of environment configuration.
        
        Returns:
            List of security warnings
        """
        warnings = []
        
        # Check if running in debug mode in production
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment == "production":
            debug_vars = ["DEBUG", "FLASK_DEBUG", "DJANGO_DEBUG"]
            for var in debug_vars:
                if os.getenv(var, "").lower() in ["true", "1", "yes"]:
                    warnings.append(f"Debug mode enabled in production: {var}")
        
        # Check for weak secrets
        secret_vars = ["SECRET_KEY", "SESSION_SECRET", "JWT_SECRET"]
        for var in secret_vars:
            secret = os.getenv(var, "")
            if secret and len(secret) < 32:
                warnings.append(f"Weak secret detected for {var} (less than 32 characters)")
        
        # Check for insecure protocols in URLs
        url_vars = ["DATABASE_URL", "REDIS_URL", "WEBHOOK_URL"]
        for var in url_vars:
            url = os.getenv(var, "")
            if url and url.startswith("http://") and not url.startswith("http://localhost"):
                warnings.append(f"Insecure HTTP protocol used in {var}")
        
        return warnings


def rate_limit(requests_per_minute: int = 60):
    """
    Decorator for rate limiting function calls.
    
    Args:
        requests_per_minute: Maximum requests per minute
    """
    config = RateLimitConfig(requests_per_minute=requests_per_minute)
    limiter = RateLimiter(config)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Use function name as identifier for global rate limiting
            identifier = f"function_{func.__name__}"
            
            if not limiter.is_allowed(identifier):
                wait_time = limiter.time_until_allowed(identifier)
                raise RateLimitExceeded(f"Rate limit exceeded. Try again in {wait_time:.1f} seconds")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def secure_random_string(length: int = 32) -> str:
    """
    Generate a cryptographically secure random string.
    
    Args:
        length: Length of the string to generate
        
    Returns:
        Random string suitable for secrets
    """
    return secrets.token_urlsafe(length)


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify webhook signature for secure API communication.
    
    Args:
        payload: Raw payload bytes
        signature: Signature to verify
        secret: Shared secret
        
    Returns:
        True if signature is valid
    """
    if not signature or not secret:
        return False
    
    # Compute expected signature
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Use constant time comparison to prevent timing attacks
    return hmac.compare_digest(signature, expected)


def validate_production_security() -> Dict[str, Any]:
    """
    Perform comprehensive security validation for production deployment.
    
    Returns:
        Dictionary with security check results
    """
    results = {
        "is_secure": True,
        "errors": [],
        "warnings": [],
        "recommendations": []
    }
    
    # Validate API keys
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        if not APIKeyValidator.validate_openai_key(openai_key):
            results["errors"].append("Invalid OpenAI API key format")
            results["is_secure"] = False
        else:
            logger.info(f"OpenAI API key validated: {APIKeyValidator.mask_api_key(openai_key)}")
    
    # Check environment security
    env_warnings = APIKeyValidator.validate_environment_security()
    results["warnings"].extend(env_warnings)
    
    # Check file permissions
    sensitive_files = [".env", "config.py", "secrets.json"]
    for filename in sensitive_files:
        if os.path.exists(filename):
            stat = os.stat(filename)
            # Check if file is readable by others (permission bits)
            if stat.st_mode & 0o044:  # Others have read permission
                results["warnings"].append(f"Sensitive file {filename} is readable by others")
    
    # Production recommendations
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment == "production":
        recommendations = [
            "Use environment variables for all secrets",
            "Enable HTTPS for all external communications",
            "Implement proper authentication and authorization",
            "Set up monitoring and alerting for security events",
            "Regular security updates and vulnerability scanning",
            "Implement proper backup and disaster recovery",
            "Use a proper secrets management system (not .env files)"
        ]
        results["recommendations"].extend(recommendations)
    
    return results


if __name__ == "__main__":
    """Command-line interface for security validation"""
    security_results = validate_production_security()
    
    if security_results["errors"]:
        print("❌ Security Errors:")
        for error in security_results["errors"]:
            print(f"  • {error}")
        print()
    
    if security_results["warnings"]:
        print("⚠️  Security Warnings:")
        for warning in security_results["warnings"]:
            print(f"  • {warning}")
        print()
    
    if security_results["recommendations"]:
        print("💡 Security Recommendations:")
        for rec in security_results["recommendations"]:
            print(f"  • {rec}")
        print()
    
    if security_results["is_secure"]:
        print("🔒 Security validation passed!")
    else:
        print("🚨 Security validation failed! Please address the errors above.")
        exit(1)