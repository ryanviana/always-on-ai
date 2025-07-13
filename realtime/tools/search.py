"""
Search tool for Realtime API conversations
"""

import os
from typing import Dict, Any, List
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .base import RealtimeTool


class SearchTool(RealtimeTool):
    """Tool for web searching"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        # Initialize search service
        if self.api_key:
            self.search_service = build("customsearch", "v1", developerKey=self.api_key)
        else:
            self.search_service = None
            
    @property
    def estimated_duration(self) -> float:
        """Search API calls take longer"""
        return 3.0
        
    @property
    def feedback_message(self) -> str:
        """User-friendly message in Portuguese"""
        return "Pesquisando informações..."
        
    @property
    def category(self) -> str:
        """Tool category"""
        return "search"
            
    @property 
    def schema(self) -> Dict[str, Any]:
        """OpenAI function schema"""
        return {
            "type": "function",
            "name": "search",
            "description": "REQUIRED: Use this tool to search the web when user asks you to search for something or needs current information. Examples: 'pesquise preço de carros', 'busque notícias sobre...', 'procure informações sobre...'",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query exactly as the user requested. For Portuguese queries, keep in Portuguese."
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 3, max: 5)",
                        "minimum": 1,
                        "maximum": 5
                    },
                    "language": {
                        "type": "string",
                        "enum": ["pt", "en", "auto"],
                        "description": "Search language (default: auto-detect)"
                    }
                },
                "required": ["query"]
            }
        }
        
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute web search"""
        query = params.get("query", "").strip()
        num_results = min(params.get("num_results", 3), 5)
        language = params.get("language", "auto")
        
        if not query:
            return {"error": "Search query is required"}
            
        # Mock response if no API key
        if not self.search_service or not self.search_engine_id:
            return self._mock_search_response(query, num_results)
            
        try:
            # Auto-detect language if needed
            if language == "auto":
                language = self._detect_language(query)
                
            # Build search parameters
            search_params = {
                "cx": self.search_engine_id,
                "q": query,
                "num": num_results
            }
            
            # Add language-specific parameters
            if language == "pt":
                search_params.update({
                    "lr": "lang_pt",
                    "gl": "br",
                    "hl": "pt-BR"
                })
                
            # Execute search
            result = self.search_service.cse().list(**search_params).execute()
            
            # Format results
            return self._format_search_results(query, result)
            
        except HttpError as e:
            return {"error": f"Search API error: {e.resp.status}"}
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
            
    def _detect_language(self, text: str) -> str:
        """Simple language detection"""
        portuguese_indicators = [
            'que', 'com', 'para', 'por', 'uma', 'como', 'mais', 
            'tem', 'ser', 'está', 'quando', 'onde', 'quem'
        ]
        
        text_lower = text.lower()
        portuguese_count = sum(1 for word in portuguese_indicators if word in text_lower)
        
        return "pt" if portuguese_count >= 1 else "en"
        
    def _format_search_results(self, query: str, raw_results: Dict[str, Any]) -> Dict[str, Any]:
        """Format search results"""
        items = raw_results.get("items", [])
        
        if not items:
            return {
                "query": query,
                "results": [],
                "message": "No results found"
            }
            
        results = []
        for item in items:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
                "source": item.get("displayLink", "")
            })
            
        return {
            "query": query,
            "results": results,
            "total_results": raw_results.get("searchInformation", {}).get("totalResults", "0")
        }
        
    def _mock_search_response(self, query: str, num_results: int) -> Dict[str, Any]:
        """Mock response when no API key is available"""
        mock_results = [
            {
                "title": f"Result 1 for '{query}'",
                "snippet": f"This is a mock search result for {query}. Configure GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID for real results.",
                "link": "https://example.com/1",
                "source": "example.com"
            },
            {
                "title": f"Result 2 for '{query}'",
                "snippet": "Another mock result with relevant information about your search query.",
                "link": "https://example.com/2",
                "source": "example.com"
            },
            {
                "title": f"Result 3 for '{query}'",
                "snippet": "Third mock result demonstrating search functionality.",
                "link": "https://example.com/3",
                "source": "example.com"
            }
        ]
        
        return {
            "query": query,
            "results": mock_results[:num_results],
            "total_results": "3",
            "note": "Mock data - configure Google API for real results"
        }