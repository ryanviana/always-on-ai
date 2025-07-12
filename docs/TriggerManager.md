# TriggerManager Documentation

## Overview

The TriggerManager is the core orchestrator of the proactive trigger system in always-on-ai. It implements a sophisticated two-stage processing pipeline that efficiently handles voice transcriptions and executes appropriate actions based on detected user intents.

## Architecture

### Two-Stage Processing Pipeline

```
Input Transcription
        ↓
┌─────────────────┐
│  Stage 1:       │  ← Fast keyword matching
│  Keyword Filter │    (< 1ms response time)
└─────────────────┘
        ↓
┌─────────────────┐
│  Stage 2:       │  ← LLM validation with context
│  LLM Validation │    (2-8s response time)
└─────────────────┘
        ↓
┌─────────────────┐
│  Action         │  ← Execute trigger action
│  Execution      │    (immediate response)
└─────────────────┘
```

### Core Components

```
TriggerManager
├── TranscriptionBuffer    # Rolling buffer of conversation context
├── Keyword Detection      # Fast initial filtering
├── LLM Validation        # Intelligent intent validation  
├── Action Execution      # Trigger action orchestration
└── Request Management    # Async processing coordination
```

## Key Features

### 1. Intelligent Buffering
- **Context-Aware**: Maintains rolling window of conversation context
- **Smart Timing**: Buffers transcriptions to provide complete context
- **Memory Efficient**: Automatically manages buffer size and cleanup

### 2. Fast Keyword Detection
- **Sub-millisecond Response**: Initial keyword filtering is extremely fast
- **Flexible Matching**: Supports exact matches, partial matches, and fuzzy matching
- **Multi-language Support**: Handles keywords in multiple languages simultaneously

### 3. LLM-Powered Validation
- **Context Understanding**: Uses conversation context for accurate intent detection
- **False Positive Reduction**: Sophisticated validation reduces incorrect triggers
- **Structured Output**: Returns structured data for precise action execution

### 4. Asynchronous Processing
- **Non-blocking**: Doesn't block audio processing pipeline
- **Concurrent Validation**: Multiple triggers can be validated simultaneously
- **Request Ordering**: Ensures responses are processed in correct order

## Core Classes

### TriggerManager

```python
class TriggerManager:
    """Manages triggers and processes transcriptions through two-stage pipeline"""
    
    def __init__(self, 
                 buffer_duration: int = 60,
                 llm_model: str = "gpt-4.1-mini", 
                 tts_callback: Optional[Callable] = None,
                 validation_timeout: float = 8.0):
```

**Key Methods:**

#### Trigger Management
```python
def add_trigger(self, trigger: BaseTrigger) -> None:
    """Add a trigger to the system"""

def remove_trigger(self, trigger_class: type) -> bool:
    """Remove a trigger by class type"""

def get_triggers(self) -> List[BaseTrigger]:
    """Get all registered triggers"""
```

#### Processing Pipeline
```python
def process_transcription(self, text: str) -> None:
    """Main entry point for processing new transcriptions"""

def _check_keywords(self, text: str) -> List[BaseTrigger]:
    """Stage 1: Fast keyword detection"""

def _validate_triggers(self, triggers: List[BaseTrigger], context: str) -> None:
    """Stage 2: LLM validation with context"""
```

### TranscriptionBuffer

```python
class TranscriptionBuffer:
    """Manages rolling buffer of transcription context"""
    
    def __init__(self, duration_seconds: int = 60):
        self.duration_seconds = duration_seconds
        self.buffer: deque = deque()
```

**Key Methods:**
```python
def add_transcription(self, text: str) -> None:
    """Add new transcription to buffer"""

def get_context(self, max_chars: int = 2000) -> str:
    """Get current context window"""

def cleanup_old_entries(self) -> None:
    """Remove expired entries from buffer"""
```

## Configuration

### Core Configuration Options

```python
TRIGGER_CONFIG = {
    "enabled": True,                    # Enable/disable trigger system
    "buffer_duration_seconds": 60,      # Context buffer duration
    "llm_model": "gpt-4.1-mini",       # Model for validation
    "enabled_triggers": ["test"],       # List of enabled triggers
    "validation_timeout": 8.0,         # LLM validation timeout
    "max_concurrent_validations": 3,   # Max parallel validations
    "keyword_sensitivity": "normal",    # Keyword matching sensitivity
    "context_max_chars": 2000,         # Maximum context characters
}
```

### Performance Tuning

```python
# Memory optimization
TRIGGER_CONFIG.update({
    "buffer_cleanup_interval": 30,     # Cleanup frequency (seconds)
    "max_buffer_entries": 100,         # Maximum buffer entries
    "context_compression": True,       # Enable context compression
})

# Validation optimization  
TRIGGER_CONFIG.update({
    "validation_batch_size": 3,        # Batch multiple validations
    "validation_cache_size": 100,      # Cache validation results
    "fast_validation_mode": False,     # Skip context for simple triggers
})
```

## Processing Pipeline Details

### Stage 1: Keyword Detection

```python
def _check_keywords(self, text: str) -> List[BaseTrigger]:
    """Fast keyword filtering - typically < 1ms"""
    matching_triggers = []
    text_lower = text.lower()
    
    for trigger in self.triggers:
        if trigger.check_keywords(text_lower):
            matching_triggers.append(trigger)
            
    return matching_triggers
```

**Performance Characteristics:**
- **Speed**: Sub-millisecond response time
- **Memory**: Minimal memory usage
- **Accuracy**: High recall, moderate precision

### Stage 2: LLM Validation

```python
async def _validate_with_context(self, trigger: BaseTrigger, context: str) -> Optional[Dict]:
    """LLM-powered validation with conversation context"""
    
    # Build validation prompt with context
    prompt = self._build_validation_prompt(trigger, context)
    
    # Call LLM for validation
    response = await self._call_llm(prompt, model=self.llm_model)
    
    # Parse and validate response
    return self._parse_validation_response(response)
```

**Performance Characteristics:**
- **Speed**: 2-8 seconds depending on model and context
- **Accuracy**: High precision, high recall
- **Cost**: Moderate token usage per validation

### Stage 3: Action Execution

```python
def _execute_action(self, trigger: BaseTrigger, validation_result: Dict) -> None:
    """Execute validated trigger action"""
    
    try:
        # Execute trigger action
        response = trigger.action(validation_result)
        
        # Handle TTS response
        if response.get("speak") and self.tts_callback:
            self.tts_callback(response["text"], response.get("voice_settings", {}))
            
        # Emit events
        event_bus.emit(EventTypes.TRIGGER_EXECUTED, {
            "trigger": trigger.__class__.__name__,
            "response": response
        })
        
    except Exception as e:
        self.logger.error(f"Error executing trigger {trigger.__class__.__name__}: {e}")
```

## Usage Examples

### Basic Setup

```python
from triggers.manager import TriggerManager
from triggers.builtin import TestTrigger

# Create TriggerManager
trigger_manager = TriggerManager(
    buffer_duration=60,
    llm_model="gpt-4.1-mini",
    validation_timeout=8.0
)

# Add triggers
trigger_manager.add_trigger(TestTrigger())

# Process transcriptions
trigger_manager.process_transcription("Execute test command")
```

### Advanced Configuration

```python
# Custom TTS callback
def custom_tts_callback(text: str, voice_settings: Dict[str, Any]):
    print(f"TTS: {text}")
    # Implement your TTS logic here

# Create with custom configuration
trigger_manager = TriggerManager(
    buffer_duration=120,               # 2-minute context window
    llm_model="gpt-4o-mini",          # Use faster model
    tts_callback=custom_tts_callback,
    validation_timeout=5.0             # Faster timeout
)

# Add multiple triggers with priorities
trigger_manager.add_trigger(AssistantTrigger())    # Priority: 95
trigger_manager.add_trigger(WeatherTrigger())      # Priority: 80  
trigger_manager.add_trigger(SearchTrigger())       # Priority: 60
trigger_manager.add_trigger(TestTrigger())         # Priority: 70
```

### Event-Driven Processing

```python
from events import event_bus, EventTypes

# Listen for trigger events
@event_bus.on(EventTypes.TRIGGER_KEYWORD_MATCH)
def on_keyword_match(data):
    print(f"Keyword match: {data['trigger']}")

@event_bus.on(EventTypes.TRIGGER_VALIDATED)  
def on_trigger_validated(data):
    print(f"Trigger validated: {data['trigger']}")

@event_bus.on(EventTypes.TRIGGER_EXECUTED)
def on_trigger_executed(data):
    print(f"Trigger executed: {data['trigger']}")
```

## Integration with Audio Pipeline

### Real-time Processing

```python
# Integration with audio transcription
class AudioProcessor:
    def __init__(self):
        self.trigger_manager = TriggerManager()
    
    def on_transcription_ready(self, text: str):
        """Called when new transcription is available"""
        # Feed to trigger system
        self.trigger_manager.process_transcription(text)
    
    def on_transcription_partial(self, partial_text: str):
        """Called for partial transcriptions"""
        # Optionally process partial transcriptions for fast triggers
        if len(partial_text) > 10:  # Minimum length threshold
            self.trigger_manager.process_transcription(partial_text)
```

### TTS Integration

```python
def create_tts_callback(tts_service, audio_manager):
    """Create TTS callback with proper audio management"""
    
    def tts_callback(text: str, voice_settings: Dict[str, Any]):
        # Pause microphone to prevent feedback
        audio_manager.pause_microphone()
        
        try:
            # Synthesize speech
            tts_service.synthesize(
                text=text,
                voice=voice_settings.get("voice", "nova"),
                speed=voice_settings.get("speed", 1.0)
            )
        finally:
            # Resume microphone after playback
            audio_manager.resume_microphone()
    
    return tts_callback
```

## Performance Monitoring

### Metrics Collection

```python
# Get performance metrics
metrics = trigger_manager.get_metrics()

print(f"Total transcriptions processed: {metrics['total_processed']}")
print(f"Keyword matches: {metrics['keyword_matches']}")
print(f"Successful validations: {metrics['successful_validations']}")
print(f"Average validation time: {metrics['avg_validation_time']}ms")
print(f"Buffer utilization: {metrics['buffer_utilization']}%")
```

### Performance Optimization

```python
# Optimize for speed
trigger_manager.optimize_for_speed(
    reduce_context=True,        # Use shorter context
    enable_caching=True,        # Cache validation results
    fast_keyword_mode=True      # Skip complex keyword matching
)

# Optimize for accuracy
trigger_manager.optimize_for_accuracy(
    increase_context=True,      # Use longer context
    slower_model=True,          # Use more accurate model
    multiple_validations=True   # Run multiple validation passes
)
```

## Error Handling

### Common Error Scenarios

```python
try:
    trigger_manager.process_transcription(text)
except TriggerValidationTimeout:
    # Handle validation timeout
    logger.warning("Trigger validation timed out")
except TriggerExecutionError as e:
    # Handle trigger execution error
    logger.error(f"Trigger execution failed: {e}")
except LLMConnectionError:
    # Handle LLM connection issues
    logger.error("Unable to connect to LLM service")
```

### Recovery Mechanisms

```python
# Configure automatic recovery
trigger_manager.configure_recovery(
    max_retries=3,                    # Retry failed validations
    fallback_mode=True,               # Use simple keyword matching as fallback
    error_cooldown=30,                # Wait before retrying failed triggers
    graceful_degradation=True         # Continue with reduced functionality
)
```

## Advanced Features

### Custom Validation Templates

```python
# Custom Jinja2 templates for trigger validation
trigger_manager.load_custom_templates("/path/to/templates/")

# Per-trigger template customization
trigger_manager.set_trigger_template("WeatherTrigger", "weather_validation.j2")
```

### Trigger Chaining

```python
# Chain triggers for complex workflows
trigger_manager.create_trigger_chain([
    ("AssistantTrigger", "start_conversation"),
    ("WeatherTrigger", "get_weather"),
    ("SearchTrigger", "web_search")
])
```

### Context-Aware Processing

```python
# Configure context awareness
trigger_manager.configure_context(
    include_previous_responses=True,  # Include previous trigger responses
    context_window_sliding=True,      # Use sliding context window
    context_relevance_scoring=True,   # Score context relevance
    smart_context_selection=True      # Intelligently select relevant context
)
```

## Debugging and Troubleshooting

### Debug Mode

```python
# Enable debug mode
trigger_manager.set_debug_mode(True)

# Debug specific trigger
trigger_manager.debug_trigger("TestTrigger", text="test command")

# Trace processing pipeline
trigger_manager.trace_processing(text="example input")
```

### Common Issues and Solutions

| Issue | Symptoms | Solution |
|-------|----------|----------|
| High false positives | Triggers firing incorrectly | Improve keyword specificity, adjust validation prompts |
| High false negatives | Triggers not firing when expected | Add more keywords, reduce validation strictness |
| Slow response times | Long delays before action | Reduce context size, use faster LLM model |
| Memory leaks | Increasing memory usage | Enable buffer cleanup, reduce buffer duration |
| Validation timeouts | Frequent timeout errors | Increase timeout, optimize validation prompts |

### Performance Profiling

```python
# Profile trigger performance
profiler = trigger_manager.create_profiler()
profiler.start()

# Process sample data
trigger_manager.process_transcription("sample text")

# Get profiling results
results = profiler.stop()
print(f"Keyword detection: {results['keyword_time']}ms")
print(f"LLM validation: {results['validation_time']}ms") 
print(f"Action execution: {results['execution_time']}ms")
```

## Best Practices

1. **Trigger Priority**: Set appropriate priorities to avoid conflicts
2. **Context Management**: Configure buffer duration based on your use case
3. **Error Handling**: Implement comprehensive error handling and recovery
4. **Performance Monitoring**: Regular monitoring of system performance
5. **Testing**: Thorough testing of triggers with various inputs
6. **Documentation**: Document custom triggers and configuration changes

## Security Considerations

1. **Input Sanitization**: All transcriptions are sanitized before processing
2. **LLM Prompt Injection**: Validation prompts are protected against injection attacks
3. **Rate Limiting**: Built-in rate limiting for LLM API calls
4. **Privacy**: No sensitive data is logged or stored in validation context