"""
Tool registry for managing available tools
"""

from typing import Dict, List, Any, Optional
from .base import RealtimeTool


class ToolRegistry:
    """Registry for managing and accessing tools"""
    
    def __init__(self):
        """Initialize tool registry"""
        self.tools: Dict[str, RealtimeTool] = {}
        
    def register(self, tool: RealtimeTool, name: Optional[str] = None):
        """
        Register a tool
        
        Args:
            tool: Tool instance to register
            name: Optional custom name (defaults to tool.name)
        """
        tool_name = name or tool.name
        self.tools[tool_name] = tool
        print(f"Registered tool: {tool_name}")
        
    def unregister(self, name: str):
        """Remove a tool from the registry"""
        if name in self.tools:
            del self.tools[name]
            print(f"Unregistered tool: {name}")
            
    def get(self, name: str) -> Optional[RealtimeTool]:
        """Get a tool by name"""
        return self.tools.get(name)
        
    def get_all(self) -> Dict[str, RealtimeTool]:
        """Get all registered tools"""
        return self.tools.copy()
        
    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all registered tools"""
        schemas = []
        
        for name, tool in self.tools.items():
            schema = tool.schema.copy()
            schema["name"] = name
            schemas.append(schema)
            
        return schemas
        
    def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name
        
        Args:
            name: Tool name
            params: Parameters for the tool
            
        Returns:
            Tool execution result
        """
        tool = self.get(name)
        if not tool:
            return {"error": f"Tool '{name}' not found"}
            
        try:
            # Tools are async, so we need to handle that
            import asyncio
            
            if asyncio.iscoroutinefunction(tool.execute):
                # Run async tool
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(tool.execute(params))
                loop.close()
            else:
                # Run sync tool
                result = tool.execute(params)
                
            return result
            
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}