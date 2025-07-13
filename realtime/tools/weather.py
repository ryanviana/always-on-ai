"""
Weather tool for Realtime API conversations
"""

import os
import aiohttp
from typing import Dict, Any
from .base import RealtimeTool


class WeatherTool(RealtimeTool):
    """Tool for getting weather information"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.base_url = "https://api.openweathermap.org/data/2.5"
        
    @property
    def estimated_duration(self) -> float:
        """Weather API call takes a bit longer"""
        return 2.0
        
    @property
    def feedback_message(self) -> str:
        """User-friendly message in Portuguese"""
        return "Verificando o clima..."
        
    @property
    def category(self) -> str:
        """Tool category"""
        return "information"
        
    @property
    def schema(self) -> Dict[str, Any]:
        """OpenAI function schema"""
        return {
            "type": "function",
            "name": "weather",
            "description": "Get current weather or forecast for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or location (e.g., 'São Paulo', 'Rio de Janeiro')"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["current", "forecast"],
                        "description": "Type of weather information to retrieve"
                    },
                    "units": {
                        "type": "string",
                        "enum": ["metric", "imperial"],
                        "description": "Temperature units (default: metric for Celsius)"
                    }
                },
                "required": ["location"]
            }
        }
        
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get weather information"""
        location = params.get("location", "").strip()
        weather_type = params.get("type", "current")
        units = params.get("units", "metric")
        
        if not location:
            return {"error": "Location is required"}
            
        # Mock response if no API key
        if not self.api_key:
            return self._mock_weather_response(location, weather_type, units)
            
        try:
            # Make API request
            endpoint = "weather" if weather_type == "current" else "forecast"
            url = f"{self.base_url}/{endpoint}"
            
            params = {
                "q": location,
                "appid": self.api_key,
                "units": units,
                "lang": "pt_br"  # Portuguese descriptions
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._format_weather_response(data, weather_type, units)
                    else:
                        return {"error": f"Weather API error: {response.status}"}
                        
        except Exception as e:
            return {"error": f"Failed to get weather: {str(e)}"}
            
    def _format_weather_response(self, data: Dict[str, Any], 
                               weather_type: str, units: str) -> Dict[str, Any]:
        """Format weather API response"""
        unit_symbol = "°C" if units == "metric" else "°F"
        
        if weather_type == "current":
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            
            return {
                "location": data.get("name", "Unknown"),
                "temperature": f"{main.get('temp', 'N/A')}{unit_symbol}",
                "feels_like": f"{main.get('feels_like', 'N/A')}{unit_symbol}",
                "description": weather.get("description", "N/A"),
                "humidity": f"{main.get('humidity', 'N/A')}%",
                "wind_speed": f"{data.get('wind', {}).get('speed', 'N/A')} m/s"
            }
        else:
            # Forecast - return next 3 periods
            forecasts = []
            for item in data.get("list", [])[:3]:
                dt_txt = item.get("dt_txt", "")
                main = item.get("main", {})
                weather = item.get("weather", [{}])[0]
                
                forecasts.append({
                    "time": dt_txt,
                    "temperature": f"{main.get('temp', 'N/A')}{unit_symbol}",
                    "description": weather.get("description", "N/A")
                })
                
            return {
                "location": data.get("city", {}).get("name", "Unknown"),
                "forecast": forecasts
            }
            
    def _mock_weather_response(self, location: str, weather_type: str, units: str) -> Dict[str, Any]:
        """Mock response when no API key is available"""
        unit_symbol = "°C" if units == "metric" else "°F"
        
        if weather_type == "current":
            return {
                "location": location,
                "temperature": f"25{unit_symbol}",
                "feels_like": f"27{unit_symbol}",
                "description": "céu parcialmente nublado",
                "humidity": "65%",
                "wind_speed": "3.5 m/s",
                "note": "Mock data - configure OPENWEATHER_API_KEY for real data"
            }
        else:
            return {
                "location": location,
                "forecast": [
                    {
                        "time": "Amanhã manhã",
                        "temperature": f"22{unit_symbol}",
                        "description": "sol com algumas nuvens"
                    },
                    {
                        "time": "Amanhã tarde", 
                        "temperature": f"28{unit_symbol}",
                        "description": "ensolarado"
                    },
                    {
                        "time": "Amanhã noite",
                        "temperature": f"20{unit_symbol}",
                        "description": "céu limpo"
                    }
                ],
                "note": "Mock data - configure OPENWEATHER_API_KEY for real data"
            }