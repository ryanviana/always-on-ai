"""
Base class for Realtime API tools
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class RealtimeTool(ABC):
    """Abstract base class for tools used in Realtime conversations"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the tool
        
        Args:
            config: Optional configuration dictionary for the tool
        """
        self.name = self.__class__.__name__.lower().replace("tool", "")
        self.config = config or {}
        
    @property
    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """
        Get the OpenAI function schema for this tool
        
        Returns:
            Dict containing the function schema in OpenAI format
        """
        pass
        
    @property
    def estimated_duration(self) -> float:
        """
        Estimated execution duration in seconds
        
        Returns:
            Estimated duration, defaults to 2.0 seconds
        """
        return 2.0
        
    @property
    def feedback_message(self) -> str:
        """
        User-friendly message to display while tool is executing
        
        Returns:
            Feedback message in Portuguese
        """
        return f"Processando {self.name}..."
        
    @property
    def category(self) -> str:
        """
        Tool category for organization and filtering
        
        Returns:
            Category name (e.g., 'utility', 'search', 'calculation')
        """
        return "utility"
        
    @property
    def configuration_schema(self) -> Dict[str, Any]:
        """
        JSON schema for tool configuration validation
        
        Returns:
            JSON schema dict, empty by default
        """
        return {}
        
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
        
    def validate_config(self) -> bool:
        """
        Validate the tool's configuration against its schema
        
        Returns:
            True if configuration is valid
        """
        # Basic implementation - can be overridden for complex validation
        schema = self.configuration_schema
        if not schema:
            return True
            
        # Simple validation - check required fields exist
        required = schema.get("required", [])
        return all(key in self.config for key in required)
        
    async def before_execute(self, params: Dict[str, Any]) -> None:
        """
        Hook called before tool execution
        
        Args:
            params: Parameters that will be passed to execute()
        """
        pass
        
    async def after_execute(self, params: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Hook called after tool execution
        
        Args:
            params: Parameters that were passed to execute()
            result: Result returned by execute()
        """
        pass
        
    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with given parameters
        
        Args:
            params: Parameters from the function call
            
        Returns:
            Dict containing the result of the tool execution
        """
        pass
        
    def validate_params(self, params: Dict[str, Any], required: list) -> bool:
        """
        Validate that required parameters are present
        
        Args:
            params: Parameters to validate
            required: List of required parameter names
            
        Returns:
            True if all required parameters are present
        """
        return all(param in params for param in required)