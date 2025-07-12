# Adding New Triggers - Complete Guide

## Overview

This guide provides a comprehensive walkthrough for creating custom proactive triggers in the always-on-ai system. Triggers enable the system to automatically detect user intents from voice transcriptions and execute appropriate actions.

## Understanding the Trigger System

### Two-Stage Processing

1. **Keyword Detection** (< 1ms): Fast initial filtering using keyword matching
2. **LLM Validation** (2-8s): Intelligent intent validation using conversation context

### Trigger Lifecycle

```
User Speech → Transcription → Keyword Match → LLM Validation → Action Execution → TTS Response
```

## Step 1: Create Your Trigger Class

### Basic Trigger Template

Create a new file in `triggers/builtin/your_trigger.py`:

```python
"""
Your trigger description - what does it do?
"""

from typing import Dict, Any, List, Optional
from ..base import BaseTrigger


class YourTrigger(BaseTrigger):
    """One-line description of your trigger's purpose"""

    # Core configuration
    description = "Detailed description for documentation and logs"
    language = "pt-BR"  # or "en" for English
    priority = 50       # 1-100, higher numbers = higher priority

    # LLM Training Data - Critical for accuracy!
    activation_criteria = [
        "Specific scenario 1 when trigger should activate",
        "Specific scenario 2 when trigger should activate",
        "Be very explicit about the intent detection"
    ]

    positive_examples = [
        "Example phrase that should trigger (Portuguese)",
        "Another example that should work",
        "Include various phrasings and formalities",
        "Cover different ways users might say it"
    ]

    negative_examples = [
        "Similar phrase that should NOT trigger",
        "Edge case that might be confusing",
        "Disambiguation examples"
    ]

    edge_cases = [
        "Tricky scenario to consider",
        "Context-dependent situations",
        "Ambiguous cases that need clarification"
    ]

    response_schema = {
        "triggered": "boolean - whether trigger should activate",
        "extracted_data": "string - any specific data extracted from user input",
        "confidence": "float - confidence score 0-1",
        "additional_field": "string - any other structured data you need"
    }

    @property
    def keywords(self) -> List[str]:
        """Keywords for fast initial detection"""
        return [
            # English keywords
            "english_keyword1", "english_keyword2",
            # Portuguese keywords
            "palavra_portuguesa1", "palavra_portuguesa2"
        ]

    def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute your trigger's action"""

        # Extract validated data
        extracted_data = validation_result.get("extracted_data", "")
        confidence = validation_result.get("confidence", 0.0)

        # Log trigger execution
        self.logger.info(f"🎯 {self.__class__.__name__.upper()} FIRED!")
        self.logger.info(f"Extracted data: {extracted_data}")
        self.logger.info(f"Confidence: {confidence}")

        # Implement your logic here
        # This is where you perform the actual action

        # Example: Process the extracted data
        result = self._process_user_request(extracted_data)

        # Generate response text
        response_text = f"Processed your request: {result}"

        # Return response for TTS
        return {
            "text": response_text,
            "speak": True,
            "voice_settings": {
                "speed": 1.0,
                "voice": "nova"  # Optional: specify voice
            }
        }

    def _process_user_request(self, data: str) -> str:
        """Helper method for your specific logic"""
        # Implement your business logic here
        return f"Processed: {data}"
```

## Step 2: Advanced Trigger Features

### Custom Keyword Matching

Override the keyword checking for more sophisticated matching:

```python
def check_keywords(self, text: str) -> bool:
    """Custom keyword matching logic"""
    import re

    # Normalize text
    text_normalized = re.sub(r'[^\w\s]', '', text.lower())

    # Custom pattern matching
    patterns = [
        r'\btimer\s+\w+\s+(\d+)\s+(minutos?|segundos?)',
        r'\balarme\s+em\s+(\d+)',
        r'\blembrar?\s+em\s+(\d+)'
    ]

    for pattern in patterns:
        if re.search(pattern, text_normalized):
            return True

    return super().check_keywords(text)
```

### Custom LLM Validation

Override LLM validation for special processing:

```python
async def validate_with_llm(self, context: str, model: str = "gpt-4.1-mini",
                           template_env=None) -> Optional[Dict[str, Any]]:
    """Custom LLM validation with special logic"""

    # Pre-process context for better validation
    processed_context = self._preprocess_context(context)

    # Call parent validation
    result = await super().validate_with_llm(processed_context, model, template_env)

    # Post-process result
    if result and result.get("triggered"):
        result = self._post_process_validation(result)

    return result

def _preprocess_context(self, context: str) -> str:
    """Preprocess context for better LLM understanding"""
    # Add context annotations or formatting
    return f"[TIMER_CONTEXT] {context}"

def _post_process_validation(self, result: Dict[str, Any]) -> Dict[str, Any]:
    """Post-process validation results"""
    # Extract and validate time duration
    if "duration" in result:
        result["duration_seconds"] = self._parse_duration(result["duration"])
    return result
```

### Error Handling and Validation

```python
def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Robust action implementation with error handling"""

    try:
        # Validate required fields
        if not validation_result.get("triggered"):
            raise ValueError("Trigger validation failed")

        required_data = validation_result.get("required_field")
        if not required_data:
            return {
                "text": "Desculpe, não consegui entender sua solicitação. Pode repetir?",
                "speak": True
            }

        # Process the request
        result = self._safe_process_request(required_data)

        # Generate appropriate response
        if result.get("success"):
            response_text = f"Sucesso! {result['message']}"
        else:
            response_text = f"Erro ao processar: {result.get('error', 'Erro desconhecido')}"

        return {
            "text": response_text,
            "speak": True,
            "voice_settings": {"speed": 1.0}
        }

    except Exception as e:
        self.logger.error(f"Error in {self.__class__.__name__}: {e}", exc_info=True)
        return {
            "text": "Desculpe, ocorreu um erro interno. Tente novamente.",
            "speak": True
        }

def _safe_process_request(self, data: str) -> Dict[str, Any]:
    """Safe processing with error handling"""
    try:
        # Your processing logic here
        result = self._do_processing(data)
        return {"success": True, "message": result}
    except Exception as e:
        self.logger.error(f"Processing error: {e}")
        return {"success": False, "error": str(e)}
```

## Step 3: Real-World Examples

### Timer/Reminder Trigger

```python
"""
Timer trigger for setting timers and reminders
"""

import re
import time
import threading
from typing import Dict, Any, List, Optional
from ..base import BaseTrigger


class TimerTrigger(BaseTrigger):
    """Set timers and reminders with natural language"""

    description = "Set timers and reminders with automatic time extraction"
    language = "pt-BR"
    priority = 85  # High priority - specific intent

    def __init__(self):
        super().__init__()
        self.active_timers = {}  # Track active timers

    activation_criteria = [
        "Timer setting requests with specific duration",
        "Reminder requests with time specifications",
        "Alarm or countdown setting commands"
    ]

    positive_examples = [
        "Colocar um timer de 5 minutos",
        "Timer de 30 segundos",
        "Me lembrar em 2 horas",
        "Definir alarme para 10 minutos",
        "Cronômetro de 1 hora e 30 minutos"
    ]

    negative_examples = [
        "Que horas são agora? (time query)",
        "Quanto tempo demora para cozinhar? (duration question)",
        "Tenho tempo livre (availability statement)"
    ]

    edge_cases = [
        "Handle various time units (segundos, minutos, horas)",
        "Extract compound durations (1 hora e 30 minutos)",
        "Distinguish timer setting from time queries"
    ]

    response_schema = {
        "triggered": "boolean - whether trigger should activate",
        "duration_seconds": "number - total duration in seconds",
        "time_components": "object - breakdown of hours/minutes/seconds",
        "timer_description": "string - optional description/name for timer",
        "confidence": "float - confidence score 0-1"
    }

    @property
    def keywords(self) -> List[str]:
        return [
            # English
            "timer", "alarm", "remind", "countdown", "set",
            # Portuguese
            "timer", "alarme", "lembrar", "cronômetro",
            "minutos", "segundos", "horas", "colocar"
        ]

    def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Set timer based on extracted duration"""

        duration_seconds = validation_result.get("duration_seconds", 0)
        description = validation_result.get("timer_description", "Timer")

        if duration_seconds <= 0:
            return {
                "text": "Desculpe, não consegui entender a duração. Tente algo como 'timer de 5 minutos'.",
                "speak": True
            }

        # Create timer
        timer_id = self._create_timer(duration_seconds, description)

        # Format duration for response
        duration_text = self._format_duration(duration_seconds)

        self.logger.info(f"⏰ TIMER SET: {duration_text} ({timer_id})")

        return {
            "text": f"Timer de {duration_text} iniciado! Eu vou te avisar quando acabar.",
            "speak": True,
            "voice_settings": {"speed": 1.0}
        }

    def _create_timer(self, duration_seconds: int, description: str) -> str:
        """Create and start a timer"""
        timer_id = f"timer_{int(time.time())}"

        def timer_callback():
            time.sleep(duration_seconds)
            self._timer_finished(timer_id, description)

        timer_thread = threading.Thread(target=timer_callback, daemon=True)
        timer_thread.start()

        self.active_timers[timer_id] = {
            "duration": duration_seconds,
            "description": description,
            "start_time": time.time(),
            "thread": timer_thread
        }

        return timer_id

    def _timer_finished(self, timer_id: str, description: str):
        """Handle timer completion"""
        self.logger.info(f"⏰ TIMER FINISHED: {timer_id}")

        # Remove from active timers
        if timer_id in self.active_timers:
            del self.active_timers[timer_id]

        # Trigger completion notification
        from events import event_bus, EventTypes
        event_bus.emit(EventTypes.TIMER_COMPLETED, {
            "timer_id": timer_id,
            "description": description,
            "message": f"Timer finalizado: {description}"
        })

    def _format_duration(self, seconds: int) -> str:
        """Format duration for human reading"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
        if secs > 0 or not parts:
            parts.append(f"{secs} segundo{'s' if secs != 1 else ''}")

        return " e ".join(parts)
```

### API Integration Trigger

```python
"""
Weather trigger with API integration
"""

import os
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from ..base import BaseTrigger


class WeatherTrigger(BaseTrigger):
    """Get weather information with location detection"""

    description = "Fetch weather data with automatic location extraction"
    language = "pt-BR"
    priority = 80

    def __init__(self):
        super().__init__()
        self.weather_api_key = os.getenv("WEATHER_API_KEY")
        self.default_location = "São Paulo"  # Configure default

    activation_criteria = [
        "Weather queries for current conditions",
        "Weather forecast requests",
        "Temperature and climate questions"
    ]

    positive_examples = [
        "Como está o tempo hoje?",
        "Vai chover em São Paulo?",
        "Qual a temperatura agora?",
        "Previsão do tempo para amanhã"
    ]

    negative_examples = [
        "Não tenho tempo agora (time availability)",
        "O tempo passa rápido (time perception)"
    ]

    edge_cases = [
        "Distinguish weather 'tempo' from time 'tempo'",
        "Handle implicit locations (user's current location)",
        "Process relative time (hoje, amanhã, esta semana)"
    ]

    response_schema = {
        "triggered": "boolean - whether trigger should activate",
        "location": "string - extracted location or null for default",
        "time_reference": "string - hoje/amanhã/semana or null",
        "weather_aspect": "string - temperature/rain/general",
        "confidence": "float - confidence score 0-1"
    }

    @property
    def keywords(self) -> List[str]:
        return [
            # Weather terms
            "tempo", "clima", "chuva", "sol", "temperatura",
            "previsão", "chover", "quente", "frio", "graus"
        ]

    async def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch and return weather information"""

        location = validation_result.get("location") or self.default_location
        time_ref = validation_result.get("time_reference", "hoje")
        aspect = validation_result.get("weather_aspect", "general")

        self.logger.info(f"🌤️ WEATHER REQUEST: {location}, {time_ref}, {aspect}")

        try:
            # Fetch weather data
            weather_data = await self._fetch_weather(location, time_ref)

            # Format response
            response_text = self._format_weather_response(weather_data, location, aspect)

        except Exception as e:
            self.logger.error(f"Weather API error: {e}")
            response_text = f"Desculpe, não consegui obter informações do tempo para {location}. Tente novamente mais tarde."

        return {
            "text": response_text,
            "speak": True,
            "voice_settings": {"speed": 1.0}
        }

    async def _fetch_weather(self, location: str, time_ref: str) -> Dict[str, Any]:
        """Fetch weather data from API"""

        if not self.weather_api_key:
            raise ValueError("Weather API key not configured")

        # Example using OpenWeatherMap API
        base_url = "http://api.openweathermap.org/data/2.5"

        async with aiohttp.ClientSession() as session:
            if time_ref == "hoje":
                url = f"{base_url}/weather"
            else:
                url = f"{base_url}/forecast"

            params = {
                "q": location,
                "appid": self.weather_api_key,
                "units": "metric",
                "lang": "pt_br"
            }

            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()

    def _format_weather_response(self, data: Dict[str, Any], location: str, aspect: str) -> str:
        """Format weather data into natural response"""

        try:
            if "current" in data or "main" in data:
                # Current weather
                main = data.get("main", {})
                weather = data.get("weather", [{}])[0]

                temp = main.get("temp", 0)
                description = weather.get("description", "").capitalize()

                if aspect == "temperature":
                    return f"A temperatura em {location} está {temp}°C."
                elif aspect == "rain":
                    return f"Em {location}: {description}."
                else:
                    return f"Em {location} está {temp}°C, {description}."

            else:
                # Forecast data
                return f"A previsão para {location} indica condições variáveis. Verifique uma fonte específica para detalhes."

        except Exception as e:
            self.logger.error(f"Error formatting weather response: {e}")
            return f"Obtive dados do tempo para {location}, mas tive dificuldades para interpretá-los."
```

## Step 4: Register Your Trigger

### 1. Update `__init__.py`

Edit `triggers/builtin/__init__.py`:

```python
"""
Built-in triggers for common commands
"""

from .test_trigger import TestTrigger
from .timer_trigger import TimerTrigger  # Add your import
from .weather_trigger import WeatherTrigger  # Add your import

__all__ = [
    "TestTrigger",
    "TimerTrigger",     # Add to exports
    "WeatherTrigger",   # Add to exports
]
```

### 2. Update `main.py`

Add your trigger to the loading logic in `main.py`:

```python
# Add import at the top
from triggers.builtin import TestTrigger, TimerTrigger, WeatherTrigger

# In the _setup_triggers method, add loading logic:
if "timer" in enabled_triggers:
    trigger_manager.add_trigger(TimerTrigger())
    self.logger.info("✅ TimerTrigger loaded")

if "weather" in enabled_triggers:
    trigger_manager.add_trigger(WeatherTrigger())
    self.logger.info("✅ WeatherTrigger loaded")
```

### 3. Enable in Configuration

Edit `config.py` to enable your triggers:

```python
TRIGGER_CONFIG = {
    "enabled": True,
    "buffer_duration_seconds": 60,
    "llm_model": "gpt-4.1-mini",
    "enabled_triggers": ["test", "timer", "weather"],  # Add your triggers
    "validation_timeout": 8.0,
}
```

## Step 5: Testing Your Trigger

### Unit Testing

Create `tests/test_your_trigger.py`:

```python
import pytest
from unittest.mock import Mock, patch
from triggers.builtin.timer_trigger import TimerTrigger


class TestTimerTrigger:

    def setup_method(self):
        self.trigger = TimerTrigger()

    def test_keyword_detection(self):
        """Test keyword matching"""
        assert self.trigger.check_keywords("timer de 5 minutos")
        assert self.trigger.check_keywords("alarme em 30 segundos")
        assert not self.trigger.check_keywords("que horas são")

    def test_duration_parsing(self):
        """Test time duration extraction"""
        validation_result = {
            "triggered": True,
            "duration_seconds": 300,  # 5 minutes
            "timer_description": "Café"
        }

        response = self.trigger.action(validation_result)

        assert response["speak"] is True
        assert "5 minuto" in response["text"]

    def test_error_handling(self):
        """Test error scenarios"""
        validation_result = {
            "triggered": True,
            "duration_seconds": 0  # Invalid duration
        }

        response = self.trigger.action(validation_result)

        assert "não consegui entender" in response["text"]

    @patch('time.sleep')
    def test_timer_creation(self, mock_sleep):
        """Test timer creation and completion"""
        timer_id = self.trigger._create_timer(1, "Test Timer")

        assert timer_id in self.trigger.active_timers
        assert self.trigger.active_timers[timer_id]["description"] == "Test Timer"
```

### Integration Testing

Test with the full system:

```python
# Manual testing
python -c "
from triggers.manager import TriggerManager
from triggers.builtin import TimerTrigger

tm = TriggerManager()
tm.add_trigger(TimerTrigger())

# Test keyword detection
triggers = tm._check_keywords('timer de 5 minutos')
print(f'Keyword matches: {len(triggers)}')

# Test full processing
tm.process_transcription('colocar um timer de 2 minutos')
"
```

## Step 6: Best Practices

### Design Principles

1. **Single Responsibility**: Each trigger should handle one specific type of intent
2. **Clear Keywords**: Use unambiguous keywords that clearly indicate intent
3. **Robust Validation**: Provide comprehensive examples for LLM training
4. **Error Handling**: Always handle errors gracefully with user-friendly messages
5. **Performance**: Consider the performance impact of your trigger's actions

### LLM Prompt Optimization

```python
# Good: Specific and comprehensive
positive_examples = [
    "Colocar um timer de 5 minutos para o café",
    "Timer de 30 segundos para os ovos",
    "Me lembrar em 2 horas de ligar para o João",
    "Definir alarme para 10 minutos",
    "Cronômetro de 1 hora e 30 minutos para a reunião"
]

# Bad: Vague and insufficient
positive_examples = [
    "timer",
    "lembrar"
]
```

### Performance Considerations

```python
def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Optimized action implementation"""

    # Cache expensive operations
    if hasattr(self, '_cached_data'):
        data = self._cached_data
    else:
        data = self._expensive_operation()
        self._cached_data = data

    # Use async for I/O operations
    if asyncio.iscoroutinefunction(self._fetch_data):
        # Handle async properly
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self._fetch_data())

    # Return quickly
    return {"text": "Quick response", "speak": True}
```

### Security Considerations

```python
def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Secure action implementation"""

    # Sanitize inputs
    user_input = validation_result.get("user_data", "")
    sanitized_input = self._sanitize_input(user_input)

    # Validate extracted data
    if not self._validate_extracted_data(sanitized_input):
        return {
            "text": "Dados inválidos fornecidos.",
            "speak": True
        }

    # Use safe operations
    try:
        result = self._safe_operation(sanitized_input)
    except SecurityException:
        self.logger.warning("Security violation detected")
        return {
            "text": "Operação não permitida.",
            "speak": True
        }
```

## Troubleshooting Common Issues

### 1. Trigger Not Firing

**Problem**: Trigger doesn't activate when expected

**Solutions**:

- Check keyword list includes all variations
- Verify trigger is enabled in config
- Test keyword matching: `trigger.check_keywords("test phrase")`
- Review LLM validation examples

### 2. False Positives

**Problem**: Trigger fires when it shouldn't

**Solutions**:

- Add more negative examples
- Improve validation criteria specificity
- Increase priority of competing triggers
- Add custom validation logic

### 3. Slow Response Times

**Problem**: Trigger takes too long to respond

**Solutions**:

- Optimize action implementation
- Use async for I/O operations
- Cache expensive computations
- Reduce LLM context size

### 4. Validation Errors

**Problem**: LLM validation fails frequently

**Solutions**:

- Improve prompt examples
- Check response schema format
- Add error handling in validation
- Test with different models

## Advanced Topics

### Custom Template Systems

```python
# Custom Jinja2 templates for complex validation
template_content = """
You are validating a {{ trigger_type }} trigger.

Context: {{ context }}

Examples of valid {{ trigger_type }} requests:
{% for example in positive_examples %}
- {{ example }}
{% endfor %}

Response format: {{ response_schema }}
"""
```

### Event Integration

```python
def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Action with event integration"""

    # Emit start event
    from events import event_bus, EventTypes
    event_bus.emit(EventTypes.TRIGGER_ACTION_START, {
        "trigger": self.__class__.__name__,
        "data": validation_result
    })

    try:
        result = self._execute_action(validation_result)

        # Emit success event
        event_bus.emit(EventTypes.TRIGGER_ACTION_SUCCESS, {
            "trigger": self.__class__.__name__,
            "result": result
        })

        return result

    except Exception as e:
        # Emit error event
        event_bus.emintTypes.TRIGGER_ACTION_ERROR, {
            "trigger": self.__class__.__name__,
            "error": str(e)
        })
        raise
```

### Multi-Language Support

```python
class MultiLanguageTrigger(BaseTrigger):
    """Trigger with multi-language support"""

    def __init__(self, language="pt-BR"):
        super().__init__()
        self.language = language
        self._load_language_data()

    def _load_language_data(self):
        """Load language-specific data"""
        if self.language == "pt-BR":
            self._keywords = ["timer", "alarme", "lembrar"]
            self._examples = ["Timer de 5 minutos", "Alarme em 30 segundos"]
        elif self.language == "en":
            self._keywords = ["timer", "alarm", "remind"]
            self._examples = ["Set timer for 5 minutes", "Alarm in 30 seconds"]

    @property
    def keywords(self) -> List[str]:
        return self._keywords

    @property
    def positive_examples(self) -> List[str]:
        return self._examples
```

This comprehensive guide should enable you to create sophisticated, reliable triggers for the always-on-ai system. Remember to test thoroughly and follow the established patterns for consistency and maintainability.
