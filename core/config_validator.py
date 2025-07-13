"""
Configuration validation module for production readiness.

This module validates all configuration settings on startup to catch
issues early and provide clear error messages for misconfigurations.
"""

import os
import re
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import logging


class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""
    pass


class ConfigValidator:
    """Validates application configuration for production readiness"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        Validate all configuration settings.
        
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors.clear()
        self.warnings.clear()
        
        # Core validation checks
        self._validate_environment_variables()
        self._validate_api_keys()
        self._validate_audio_config()
        self._validate_model_config()
        self._validate_file_paths()
        self._validate_network_config()
        self._validate_logging_config()
        self._validate_security_config()
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors.copy(), self.warnings.copy()
    
    def _validate_environment_variables(self):
        """Validate required environment variables"""
        required_env_vars = [
            "OPENAI_API_KEY"
        ]
        
        optional_env_vars = {
            "GOOGLE_API_KEY": "Google Search functionality will be disabled",
            "GOOGLE_SEARCH_ENGINE_ID": "Google Search functionality will be disabled", 
            "OPENWEATHER_API_KEY": "Weather functionality will be disabled"
        }
        
        # Check required variables
        for var in required_env_vars:
            if not os.getenv(var):
                self.errors.append(f"Required environment variable {var} is not set")
            elif not os.getenv(var).strip():
                self.errors.append(f"Required environment variable {var} is empty")
        
        # Check optional variables
        for var, warning_msg in optional_env_vars.items():
            if not os.getenv(var):
                self.warnings.append(f"Optional environment variable {var} not set: {warning_msg}")
    
    def _validate_api_keys(self):
        """Validate API key formats and basic validity"""
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            if not openai_key.startswith("sk-"):
                self.errors.append("OPENAI_API_KEY does not appear to be a valid OpenAI API key (should start with 'sk-')")
            elif len(openai_key) < 20:
                self.errors.append("OPENAI_API_KEY appears to be too short")
        
        google_key = os.getenv("GOOGLE_API_KEY", "")
        if google_key and len(google_key) < 10:
            self.warnings.append("GOOGLE_API_KEY appears to be too short")
            
        weather_key = os.getenv("OPENWEATHER_API_KEY", "")
        if weather_key and len(weather_key) < 10:
            self.warnings.append("OPENWEATHER_API_KEY appears to be too short")
    
    def _validate_audio_config(self):
        """Validate audio configuration settings"""
        try:
            from config import AUDIO_CONFIG, AUDIO_DEVICE_CONFIG
            
            # Validate sample rate
            sample_rate = AUDIO_CONFIG.get("sample_rate", 16000)
            if sample_rate not in [8000, 16000, 22050, 44100, 48000]:
                self.warnings.append(f"Unusual audio sample rate: {sample_rate}Hz. Common rates are 16000, 44100, 48000")
            
            # Validate channels
            channels = AUDIO_CONFIG.get("channels", 1)
            if channels not in [1, 2]:
                self.errors.append(f"Invalid audio channels: {channels}. Must be 1 (mono) or 2 (stereo)")
            
            # Validate chunk size
            chunk_size = AUDIO_CONFIG.get("chunk_size", 1024)
            if chunk_size < 128 or chunk_size > 8192:
                self.warnings.append(f"Audio chunk size {chunk_size} may cause performance issues. Recommended: 1024-4096")
            
            # Check if chunk size is power of 2
            if chunk_size & (chunk_size - 1) != 0:
                self.warnings.append(f"Audio chunk size {chunk_size} is not a power of 2, which may be less efficient")
                
        except ImportError as e:
            self.errors.append(f"Failed to import audio configuration: {e}")
    
    def _validate_model_config(self):
        """Validate model configuration"""
        try:
            from config import (TRANSCRIPTION_MODELS, CONVERSATION_MODELS, 
                              DEFAULT_TRANSCRIPTION_MODEL, DEFAULT_CONVERSATION_MODEL)
            
            # Validate default models exist in their respective dictionaries
            if DEFAULT_TRANSCRIPTION_MODEL not in TRANSCRIPTION_MODELS.values():
                self.errors.append(f"Default transcription model '{DEFAULT_TRANSCRIPTION_MODEL}' not found in TRANSCRIPTION_MODELS")
                
            if DEFAULT_CONVERSATION_MODEL not in CONVERSATION_MODELS.values():
                self.errors.append(f"Default conversation model '{DEFAULT_CONVERSATION_MODEL}' not found in CONVERSATION_MODELS")
                
        except ImportError as e:
            self.errors.append(f"Failed to import model configuration: {e}")
    
    def _validate_file_paths(self):
        """Validate file paths and directories"""
        try:
            from config import CONTEXT_CONFIG, LOGGING_CONFIG
            
            # Validate log directory
            log_dir = LOGGING_CONFIG.get("log_dir", "./logs")
            log_path = Path(log_dir)
            
            # Check if parent directory exists and is writable
            parent_dir = log_path.parent
            if not parent_dir.exists():
                self.errors.append(f"Log directory parent '{parent_dir}' does not exist")
            elif not os.access(parent_dir, os.W_OK):
                self.errors.append(f"Log directory parent '{parent_dir}' is not writable")
            
            # Validate context storage directory if persistence is enabled
            if CONTEXT_CONFIG.get("persistence_enabled", True):
                context_dir = CONTEXT_CONFIG.get("persistence_dir", "./context_storage")
                context_path = Path(context_dir)
                parent_dir = context_path.parent
                
                if not parent_dir.exists():
                    self.errors.append(f"Context storage parent directory '{parent_dir}' does not exist")
                elif not os.access(parent_dir, os.W_OK):
                    self.errors.append(f"Context storage parent directory '{parent_dir}' is not writable")
                    
        except ImportError as e:
            self.errors.append(f"Failed to import path configuration: {e}")
    
    def _validate_network_config(self):
        """Validate network and API configuration"""
        try:
            from config import API_ENDPOINTS, REALTIME_CONFIG
            
            # Validate API endpoints are proper URLs
            for name, url in API_ENDPOINTS.items():
                if not url.startswith(("http://", "https://", "ws://", "wss://")):
                    self.errors.append(f"API endpoint '{name}' has invalid URL format: {url}")
            
            # Validate connection timeout
            timeout = REALTIME_CONFIG.get("connection_timeout", 10.0)
            if timeout < 1.0 or timeout > 60.0:
                self.warnings.append(f"Connection timeout {timeout}s may be too {'low' if timeout < 5 else 'high'}. Recommended: 5-30s")
                
        except ImportError as e:
            self.errors.append(f"Failed to import network configuration: {e}")
    
    def _validate_logging_config(self):
        """Validate logging configuration"""
        try:
            from config import LOGGING_CONFIG
            
            # Validate log level
            log_level = LOGGING_CONFIG.get("log_level", "INFO")
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if log_level.upper() not in valid_levels:
                self.errors.append(f"Invalid log level '{log_level}'. Must be one of: {', '.join(valid_levels)}")
            
            # Validate log file size
            max_size = LOGGING_CONFIG.get("max_log_size_mb", 10)
            if max_size < 1 or max_size > 1000:
                self.warnings.append(f"Log file size {max_size}MB may be {'too small' if max_size < 5 else 'too large'}. Recommended: 5-100MB")
            
            # Validate backup count
            backup_count = LOGGING_CONFIG.get("backup_count", 5)
            if backup_count < 1 or backup_count > 50:
                self.warnings.append(f"Log backup count {backup_count} may be {'too low' if backup_count < 3 else 'too high'}. Recommended: 3-20")
                
        except ImportError as e:
            self.errors.append(f"Failed to import logging configuration: {e}")
    
    def _validate_security_config(self):
        """Validate security configuration and settings"""
        try:
            from .security import validate_production_security, APIKeyValidator
            
            # Run comprehensive security validation
            security_results = validate_production_security()
            
            # Add security errors and warnings to validation results
            self.errors.extend(security_results["errors"])
            self.warnings.extend(security_results["warnings"])
            
            # Additional security checks
            environment = os.getenv("ENVIRONMENT", "development").lower()
            if environment == "production":
                # In production, warn about missing security features
                if not os.getenv("HTTPS_ENABLED", "").lower() == "true":
                    self.warnings.append("HTTPS not explicitly enabled for production deployment")
                
                # Check for default/weak passwords or keys
                if os.getenv("ADMIN_PASSWORD") in ["admin", "password", "123456"]:
                    self.errors.append("Weak or default admin password detected")
                    
        except ImportError as e:
            self.warnings.append(f"Security module not available: {e}")


def validate_startup_config() -> None:
    """
    Validate configuration on startup and exit if critical errors are found.
    
    Raises:
        ConfigValidationError: If critical configuration errors are found
    """
    validator = ConfigValidator()
    is_valid, errors, warnings = validator.validate_all()
    
    # Always show warnings
    if warnings:
        print("⚠️  Configuration Warnings:")
        for warning in warnings:
            print(f"  • {warning}")
        print()
    
    # Handle errors
    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"  • {error}")
        print()
        
        # Create helpful error message
        error_msg = f"Found {len(errors)} configuration error(s) that must be fixed before starting the application."
        if warnings:
            error_msg += f" Also found {len(warnings)} warning(s) that should be addressed."
            
        raise ConfigValidationError(error_msg)
    
    # Success message
    if warnings:
        print(f"✅ Configuration validated successfully with {len(warnings)} warning(s)")
    else:
        print("✅ Configuration validated successfully")
    print()


def validate_production_readiness() -> Dict[str, Any]:
    """
    Perform additional production readiness checks.
    
    Returns:
        Dict with validation results and recommendations
    """
    results = {
        "is_production_ready": True,
        "errors": [],
        "warnings": [],
        "recommendations": []
    }
    
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    # Check environment setting
    if environment not in ["production", "staging", "development"]:
        results["warnings"].append(f"Unknown ENVIRONMENT value: {environment}. Should be 'production', 'staging', or 'development'")
    
    # Production-specific checks
    if environment == "production":
        # Check for debug settings
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level == "DEBUG":
            results["warnings"].append("DEBUG log level in production may impact performance and expose sensitive information")
        
        # Check for required production settings
        if not os.getenv("LOG_DIR"):
            results["recommendations"].append("Set LOG_DIR environment variable to a dedicated log directory in production")
        
        # Check file logging is enabled
        if os.getenv("ENABLE_FILE_LOGGING", "true").lower() != "true":
            results["warnings"].append("File logging should be enabled in production for audit trails")
    
    return results


if __name__ == "__main__":
    """Command-line interface for configuration validation"""
    try:
        validate_startup_config()
        production_results = validate_production_readiness()
        
        if production_results["recommendations"]:
            print("💡 Production Recommendations:")
            for rec in production_results["recommendations"]:
                print(f"  • {rec}")
            print()
            
        print("🎉 All configuration checks passed!")
        
    except ConfigValidationError as e:
        print(f"\n💥 Configuration validation failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n🔥 Unexpected error during validation: {e}")
        exit(1)