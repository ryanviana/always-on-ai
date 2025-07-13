"""
Centralized logging configuration for the voice assistant system.

This module provides structured logging with proper formatting, levels, and
production-ready configurations. Replaces scattered print statements throughout
the codebase with proper logging practices.
"""

import logging
import logging.handlers
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import json


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging in production"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)
            
        return json.dumps(log_entry, ensure_ascii=False)


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with colors for development"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        
        # Format: [TIMESTAMP] [LEVEL] [MODULE] MESSAGE
        formatted = f"[{datetime.now().strftime('%H:%M:%S')}] [{record.levelname}] [{record.module}] {record.getMessage()}"
        
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
            
        return formatted


class LoggingConfig:
    """Centralized logging configuration manager"""
    
    def __init__(self, 
                 log_level: str = "INFO",
                 log_dir: Optional[str] = None,
                 enable_file_logging: bool = True,
                 enable_console_logging: bool = True,
                 structured_logging: bool = False,
                 max_log_size_mb: int = 10,
                 backup_count: int = 5):
        """
        Initialize logging configuration.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_dir: Directory for log files (defaults to ./logs)
            enable_file_logging: Whether to log to files
            enable_console_logging: Whether to log to console
            structured_logging: Use JSON structured logging for production
            max_log_size_mb: Maximum size of each log file in MB
            backup_count: Number of backup log files to keep
        """
        self.log_level = getattr(logging, log_level.upper())
        self.log_dir = Path(log_dir) if log_dir else Path("./logs")
        self.enable_file_logging = enable_file_logging
        self.enable_console_logging = enable_console_logging
        self.structured_logging = structured_logging
        self.max_log_size_mb = max_log_size_mb
        self.backup_count = backup_count
        
        self._configured = False
        
    def configure(self) -> None:
        """Configure the root logger and application loggers"""
        if self._configured:
            return
            
        # Create logs directory
        if self.enable_file_logging:
            self.log_dir.mkdir(exist_ok=True)
        
        # Clear any existing handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        
        # Set root logger level
        root_logger.setLevel(self.log_level)
        
        # Configure console handler
        if self.enable_console_logging:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            
            if self.structured_logging:
                console_handler.setFormatter(StructuredFormatter())
            else:
                console_handler.setFormatter(ColoredConsoleFormatter())
                
            root_logger.addHandler(console_handler)
        
        # Configure file handlers
        if self.enable_file_logging:
            self._setup_file_handlers(root_logger)
            
        # Configure third-party loggers
        self._configure_third_party_loggers()
        
        self._configured = True
        
        # Log configuration startup
        logger = logging.getLogger(__name__)
        logger.info("Logging system configured", extra={
            "extra_data": {
                "log_level": logging.getLevelName(self.log_level),
                "file_logging": self.enable_file_logging,
                "console_logging": self.enable_console_logging,
                "structured_logging": self.structured_logging,
                "log_dir": str(self.log_dir) if self.enable_file_logging else None
            }
        })
    
    def _setup_file_handlers(self, root_logger: logging.Logger) -> None:
        """Setup rotating file handlers for different log levels"""
        
        # Main application log (all levels)
        main_log_file = self.log_dir / "voice_assistant.log"
        main_handler = logging.handlers.RotatingFileHandler(
            main_log_file,
            maxBytes=self.max_log_size_mb * 1024 * 1024,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        main_handler.setLevel(self.log_level)
        
        # Error log (ERROR and CRITICAL only)
        error_log_file = self.log_dir / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=self.max_log_size_mb * 1024 * 1024,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        
        # Set formatters
        if self.structured_logging:
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
        main_handler.setFormatter(formatter)
        error_handler.setFormatter(formatter)
        
        root_logger.addHandler(main_handler)
        root_logger.addHandler(error_handler)
    
    def _configure_third_party_loggers(self) -> None:
        """Configure logging levels for third-party libraries"""
        third_party_configs = {
            'websockets': logging.WARNING,
            'urllib3': logging.WARNING,
            'httpx': logging.WARNING,
            'openai': logging.WARNING,
            'pyaudio': logging.ERROR,
        }
        
        for logger_name, level in third_party_configs.items():
            logging.getLogger(logger_name).setLevel(level)


# Global logging configuration instance
_logging_config: Optional[LoggingConfig] = None


def setup_logging(config_dict: Optional[Dict[str, Any]] = None) -> None:
    """
    Setup logging for the application.
    
    Args:
        config_dict: Configuration dictionary with logging settings
    """
    global _logging_config
    
    if config_dict is None:
        config_dict = {}
    
    # Environment-based defaults
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    
    defaults = {
        "log_level": os.getenv("LOG_LEVEL", "INFO" if is_production else "DEBUG"),
        "log_dir": os.getenv("LOG_DIR", "./logs"),
        "enable_file_logging": os.getenv("ENABLE_FILE_LOGGING", "true").lower() == "true",
        "enable_console_logging": os.getenv("ENABLE_CONSOLE_LOGGING", "true").lower() == "true",
        "structured_logging": is_production,
        "max_log_size_mb": int(os.getenv("MAX_LOG_SIZE_MB", "10")),
        "backup_count": int(os.getenv("LOG_BACKUP_COUNT", "5")),
    }
    
    # Merge with provided config
    merged_config = {**defaults, **config_dict}
    
    _logging_config = LoggingConfig(**merged_config)
    _logging_config.configure()


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    if _logging_config is None:
        setup_logging()
    
    return logging.getLogger(name)


def log_with_context(logger: logging.Logger, level: int, message: str, **context) -> None:
    """
    Log a message with additional context data.
    
    Args:
        logger: Logger instance
        level: Log level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        **context: Additional context data
    """
    logger.log(level, message, extra={"extra_data": context})


# Convenience functions for common logging patterns
def log_function_entry(logger: logging.Logger, func_name: str, **kwargs) -> None:
    """Log function entry with parameters"""
    log_with_context(logger, logging.DEBUG, f"Entering {func_name}", 
                    function=func_name, parameters=kwargs)


def log_function_exit(logger: logging.Logger, func_name: str, result: Any = None) -> None:
    """Log function exit with result"""
    log_with_context(logger, logging.DEBUG, f"Exiting {func_name}",
                    function=func_name, result=str(result) if result is not None else None)


def log_performance(logger: logging.Logger, operation: str, duration_ms: float, **context) -> None:
    """Log performance metrics"""
    log_with_context(logger, logging.INFO, f"Performance: {operation}",
                    operation=operation, duration_ms=duration_ms, **context)


def log_api_call(logger: logging.Logger, service: str, endpoint: str, 
                status_code: int, duration_ms: float, **context) -> None:
    """Log API call metrics"""
    log_with_context(logger, logging.INFO, f"API call: {service} {endpoint}",
                    service=service, endpoint=endpoint, status_code=status_code,
                    duration_ms=duration_ms, **context)


def log_error_with_context(logger: logging.Logger, error: Exception, 
                          operation: str, **context) -> None:
    """Log error with full context"""
    log_with_context(logger, logging.ERROR, f"Error in {operation}: {str(error)}",
                    operation=operation, error_type=type(error).__name__, 
                    error_message=str(error), **context)