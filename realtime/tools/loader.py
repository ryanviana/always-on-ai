"""
Tool auto-discovery and configuration-driven loading system
"""

import os
import importlib
import inspect
from pathlib import Path
from typing import Dict, Any, List, Optional, Type
from logging import Logger

from .base import RealtimeTool
from .registry import ToolRegistry


class ToolLoader:
    """Automatically discovers and loads tools from the tools directory"""
    
    def __init__(self, logger: Optional[Logger] = None):
        """
        Initialize tool loader
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger
        self.tools_directory = Path(__file__).parent
        
    def discover_tools(self) -> Dict[str, Type[RealtimeTool]]:
        """
        Discover all tool classes in the tools directory
        
        Returns:
            Dict mapping tool names to tool classes
        """
        discovered_tools = {}
        
        # Get all Python files in the tools directory
        tool_files = [f for f in self.tools_directory.glob("*.py") 
                     if f.name not in ["__init__.py", "base.py", "registry.py", "loader.py"]]
        
        for tool_file in tool_files:
            try:
                # Import the module
                module_name = f"realtime.tools.{tool_file.stem}"
                module = importlib.import_module(module_name)
                
                # Find tool classes in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, RealtimeTool) and 
                        obj is not RealtimeTool and 
                        not inspect.isabstract(obj)):
                        
                        tool_name = obj().name
                        discovered_tools[tool_name] = obj
                        
                        if self.logger:
                            self.logger.debug(f"Discovered tool: {tool_name} from {tool_file.name}")
                            
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error loading tool from {tool_file.name}: {e}")
                    
        return discovered_tools
        
    def load_tools_from_config(self, 
                              tool_config: Dict[str, Any],
                              global_config: Optional[Dict[str, Any]] = None) -> ToolRegistry:
        """
        Load tools based on configuration
        
        Args:
            tool_config: Configuration dict with enabled tools and their settings
            global_config: Optional global configuration to merge
            
        Returns:
            ToolRegistry with loaded and configured tools
        """
        registry = ToolRegistry()
        
        # Discover available tools
        available_tools = self.discover_tools()
        
        # Get enabled tools list
        enabled_tools = tool_config.get("enabled_tools", [])
        
        if self.logger:
            self.logger.info(f"Loading {len(enabled_tools)} enabled tools from {len(available_tools)} available")
            
        for tool_name in enabled_tools:
            try:
                # Check if tool is available
                if tool_name not in available_tools:
                    if self.logger:
                        self.logger.warning(f"Enabled tool '{tool_name}' not found in available tools")
                    continue
                    
                # Get tool class
                tool_class = available_tools[tool_name]
                
                # Get tool-specific configuration
                tool_specific_config = tool_config.get("tool_configs", {}).get(tool_name, {})
                
                # Merge with global config if provided
                final_config = {}
                if global_config:
                    final_config.update(global_config)
                final_config.update(tool_specific_config)
                
                # Create and configure tool instance
                tool_instance = tool_class(config=final_config)
                
                # Validate configuration
                if not tool_instance.validate_config():
                    if self.logger:
                        self.logger.error(f"Tool '{tool_name}' failed configuration validation")
                    continue
                    
                # Register the tool
                registry.register(tool_instance, tool_name)
                
                if self.logger:
                    self.logger.info(f"Loaded tool: {tool_name} with config: {final_config}")
                    
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error loading tool '{tool_name}': {e}")
                    
        return registry
        
    def load_all_tools(self, global_config: Optional[Dict[str, Any]] = None) -> ToolRegistry:
        """
        Load all discovered tools with optional global configuration
        
        Args:
            global_config: Optional global configuration for all tools
            
        Returns:
            ToolRegistry with all discovered tools
        """
        registry = ToolRegistry()
        available_tools = self.discover_tools()
        
        for tool_name, tool_class in available_tools.items():
            try:
                # Create tool instance with global config
                tool_instance = tool_class(config=global_config or {})
                
                # Validate configuration
                if not tool_instance.validate_config():
                    if self.logger:
                        self.logger.warning(f"Tool '{tool_name}' failed configuration validation, skipping")
                    continue
                    
                # Register the tool
                registry.register(tool_instance, tool_name)
                
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error loading tool '{tool_name}': {e}")
                    
        return registry
        
    def get_tool_info(self) -> List[Dict[str, Any]]:
        """
        Get information about all discovered tools
        
        Returns:
            List of dicts containing tool information
        """
        available_tools = self.discover_tools()
        tool_info = []
        
        for tool_name, tool_class in available_tools.items():
            try:
                # Create temporary instance to get metadata
                temp_instance = tool_class()
                
                info = {
                    "name": tool_name,
                    "class_name": tool_class.__name__,
                    "category": temp_instance.category,
                    "estimated_duration": temp_instance.estimated_duration,
                    "feedback_message": temp_instance.feedback_message,
                    "configuration_schema": temp_instance.configuration_schema,
                    "description": temp_instance.schema.get("description", "No description available")
                }
                
                tool_info.append(info)
                
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error getting info for tool '{tool_name}': {e}")
                    
        return tool_info
        
    def validate_tool_config(self, tool_config: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate tool configuration and return any errors
        
        Args:
            tool_config: Configuration to validate
            
        Returns:
            Dict with tool names as keys and lists of validation errors as values
        """
        validation_errors = {}
        available_tools = self.discover_tools()
        
        enabled_tools = tool_config.get("enabled_tools", [])
        tool_configs = tool_config.get("tool_configs", {})
        
        for tool_name in enabled_tools:
            errors = []
            
            # Check if tool exists
            if tool_name not in available_tools:
                errors.append(f"Tool '{tool_name}' not found")
                validation_errors[tool_name] = errors
                continue
                
            try:
                # Create instance with config to test validation
                tool_class = available_tools[tool_name]
                tool_specific_config = tool_configs.get(tool_name, {})
                tool_instance = tool_class(config=tool_specific_config)
                
                # Check configuration validation
                if not tool_instance.validate_config():
                    errors.append("Configuration validation failed")
                    
                # Check required configuration fields
                schema = tool_instance.configuration_schema
                if schema:
                    required_fields = schema.get("required", [])
                    for field in required_fields:
                        if field not in tool_specific_config:
                            errors.append(f"Required configuration field '{field}' missing")
                            
            except Exception as e:
                errors.append(f"Error validating tool: {str(e)}")
                
            if errors:
                validation_errors[tool_name] = errors
                
        return validation_errors


def create_default_tool_config() -> Dict[str, Any]:
    """
    Create a default tool configuration with all discovered tools enabled
    
    Returns:
        Default configuration dict
    """
    loader = ToolLoader()
    available_tools = loader.discover_tools()
    
    return {
        "enabled_tools": list(available_tools.keys()),
        "tool_configs": {
            # Tool-specific configurations can be added here
        }
    }