"""
Date and time tool for Realtime API conversations
"""

from datetime import datetime, timedelta
import pytz
from typing import Dict, Any, Optional
from .base import RealtimeTool


class DateTimeTool(RealtimeTool):
    """Tool for date and time queries"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.name = "datetime"  # Override default name
        
    @property
    def estimated_duration(self) -> float:
        """Very fast operation"""
        return 0.5
        
    @property
    def feedback_message(self) -> str:
        """User-friendly message in Portuguese"""
        return "Verificando a hora..."
        
    @property
    def category(self) -> str:
        """Tool category"""
        return "utility"
        
    @property
    def schema(self) -> Dict[str, Any]:
        """OpenAI function schema"""
        return {
            "type": "function",
            "name": "datetime",
            "description": "Get current date, time, or perform date calculations",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["current", "add", "subtract", "difference"],
                        "description": "Operation to perform"
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Timezone (e.g., 'America/Sao_Paulo', 'UTC')"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["full", "date", "time", "iso"],
                        "description": "Output format"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days for add/subtract operations"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours for add/subtract operations"
                    },
                    "target_date": {
                        "type": "string",
                        "description": "Target date for difference calculation (ISO format)"
                    }
                },
                "required": ["operation"]
            }
        }
        
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute datetime operation"""
        operation = params.get("operation", "current")
        timezone_str = params.get("timezone", "America/Sao_Paulo")
        output_format = params.get("format", "full")
        
        try:
            # Get timezone
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            
            if operation == "current":
                return self._format_datetime(now, output_format, tz)
                
            elif operation == "add":
                days = params.get("days", 0)
                hours = params.get("hours", 0)
                future = now + timedelta(days=days, hours=hours)
                
                result = self._format_datetime(future, output_format, tz)
                result["operation"] = f"Added {days} days and {hours} hours"
                return result
                
            elif operation == "subtract":
                days = params.get("days", 0)
                hours = params.get("hours", 0)
                past = now - timedelta(days=days, hours=hours)
                
                result = self._format_datetime(past, output_format, tz)
                result["operation"] = f"Subtracted {days} days and {hours} hours"
                return result
                
            elif operation == "difference":
                target_str = params.get("target_date")
                if not target_str:
                    return {"error": "target_date is required for difference operation"}
                    
                try:
                    # Parse target date
                    target = datetime.fromisoformat(target_str.replace('Z', '+00:00'))
                    if target.tzinfo is None:
                        target = tz.localize(target)
                    else:
                        target = target.astimezone(tz)
                        
                    # Calculate difference
                    diff = target - now
                    days = diff.days
                    hours = diff.seconds // 3600
                    minutes = (diff.seconds % 3600) // 60
                    
                    return {
                        "from": self._format_datetime(now, "iso", tz)["datetime"],
                        "to": self._format_datetime(target, "iso", tz)["datetime"],
                        "difference": {
                            "days": days,
                            "hours": hours,
                            "minutes": minutes,
                            "total_seconds": int(diff.total_seconds()),
                            "human_readable": self._human_readable_diff(days, hours, minutes)
                        }
                    }
                    
                except ValueError as e:
                    return {"error": f"Invalid target_date format: {str(e)}"}
                    
            else:
                return {"error": f"Unknown operation: {operation}"}
                
        except Exception as e:
            return {"error": f"Datetime operation failed: {str(e)}"}
            
    def _format_datetime(self, dt: datetime, format_type: str, tz) -> Dict[str, Any]:
        """Format datetime based on requested format"""
        # Portuguese day and month names
        dias_semana = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 
                      'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
        meses = ['', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
                'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
        
        weekday = dias_semana[dt.weekday()]
        month = meses[dt.month]
        
        if format_type == "full":
            return {
                "datetime": dt.isoformat(),
                "formatted": f"{weekday}, {dt.day} de {month} de {dt.year}, {dt.strftime('%H:%M:%S')}",
                "date": f"{dt.day}/{dt.month}/{dt.year}",
                "time": dt.strftime("%H:%M:%S"),
                "weekday": weekday,
                "timezone": str(tz)
            }
        elif format_type == "date":
            return {
                "date": f"{dt.day}/{dt.month}/{dt.year}",
                "formatted": f"{weekday}, {dt.day} de {month} de {dt.year}",
                "weekday": weekday
            }
        elif format_type == "time":
            return {
                "time": dt.strftime("%H:%M:%S"),
                "formatted": f"{dt.hour} horas e {dt.minute} minutos",
                "timezone": str(tz)
            }
        else:  # iso
            return {
                "datetime": dt.isoformat(),
                "timestamp": int(dt.timestamp())
            }
            
    def _human_readable_diff(self, days: int, hours: int, minutes: int) -> str:
        """Create human-readable time difference in Portuguese"""
        parts = []
        
        if days > 0:
            parts.append(f"{days} dia{'s' if days != 1 else ''}")
        elif days < 0:
            parts.append(f"{abs(days)} dia{'s' if abs(days) != 1 else ''} atrás")
            
        if hours > 0:
            parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
        elif hours < 0:
            parts.append(f"{abs(hours)} hora{'s' if abs(hours) != 1 else ''} atrás")
            
        if minutes > 0:
            parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
        elif minutes < 0:
            parts.append(f"{abs(minutes)} minuto{'s' if abs(minutes) != 1 else ''} atrás")
            
        if not parts:
            return "agora"
            
        return " e ".join(parts)