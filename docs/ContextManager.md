# ContextManager Documentation

## Overview

The ContextManager is a core component of the always-on-ai system responsible for managing conversation context, maintaining conversation history, and providing intelligent context switching for different interaction modes.

## Architecture

### Core Components

```
ContextManager
├── ConversationContext     # Individual conversation sessions
├── ContextBuffer          # Rolling context window management
├── ContextSwitcher        # Mode transition logic
└── MemoryManager          # Long-term memory persistence
```

## Key Features

### 1. Context Buffering
- **Rolling Window**: Maintains a configurable time-based window of conversation history
- **Memory Optimization**: Automatically trims old context to prevent memory bloat
- **Context Preservation**: Ensures important context is retained across interactions

### 2. Session Management
- **Session Tracking**: Each conversation gets a unique session ID
- **Session Persistence**: Context can be saved and restored across system restarts
- **Multi-Session Support**: Handle multiple concurrent conversation contexts

### 3. Context Switching
- **Mode Detection**: Automatically detects when to switch between different interaction modes
- **Seamless Transitions**: Maintains context continuity during mode switches
- **State Preservation**: Preserves relevant state when switching contexts

## Core Classes

### ConversationContext

```python
class ConversationContext:
    """Represents a single conversation session with context management"""
    
    def __init__(self, session_id: str, language: str = "pt-BR"):
        self.session_id = session_id
        self.language = language
        self.messages: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
```

**Key Methods:**
- `add_message(role, content, metadata=None)`: Add new message to context
- `get_recent_messages(count=10)`: Retrieve recent messages
- `get_context_summary()`: Generate summary of conversation context
- `clear_context()`: Reset conversation context

### ContextBuffer

```python
class ContextBuffer:
    """Manages rolling window of conversation context"""
    
    def __init__(self, max_duration: int = 300, max_messages: int = 50):
        self.max_duration = max_duration  # seconds
        self.max_messages = max_messages
        self.buffer: deque = deque(maxlen=max_messages)
```

**Key Methods:**
- `add_context(context_item)`: Add new context item to buffer
- `get_active_context()`: Get current active context window
- `trim_old_context()`: Remove expired context items
- `get_context_for_timeframe(start_time, end_time)`: Get context for specific time range

## Configuration

### Environment Variables

```python
CONTEXT_CONFIG = {
    "max_context_duration": 300,      # Maximum context window in seconds
    "max_context_messages": 50,       # Maximum number of messages to retain
    "context_save_interval": 60,      # Auto-save interval in seconds
    "enable_context_persistence": True, # Enable saving context to disk
    "context_storage_path": "./data/contexts/",
    "context_compression": True,       # Compress stored context
}
```

## Usage Examples

### Basic Context Management

```python
from context import ContextManager

# Initialize context manager
context_manager = ContextManager(
    max_duration=300,
    max_messages=50
)

# Create new conversation session
session_id = context_manager.create_session(language="pt-BR")

# Add messages to context
context_manager.add_user_message(session_id, "Olá, como você está?")
context_manager.add_assistant_message(session_id, "Olá! Estou bem, obrigado por perguntar.")

# Get context for AI processing
context = context_manager.get_context(session_id)
print(f"Context messages: {len(context.messages)}")
```

### Context Switching

```python
# Switch from voice conversation to text mode
context_manager.switch_mode(
    session_id=session_id,
    from_mode="voice_conversation", 
    to_mode="text_interaction",
    preserve_context=True
)

# Get context summary for mode transition
summary = context_manager.get_transition_summary(session_id)
```

### Context Persistence

```python
# Save context to persistent storage
context_manager.save_context(session_id)

# Load context from storage
context_manager.load_context(session_id)

# Auto-save configuration
context_manager.enable_auto_save(interval=60)  # Save every 60 seconds
```

## Advanced Features

### 1. Context Summarization

The ContextManager can automatically generate summaries of long conversations:

```python
# Generate context summary using LLM
summary = context_manager.generate_summary(
    session_id=session_id,
    max_length=200,
    focus_areas=["main_topics", "user_preferences", "action_items"]
)
```

### 2. Context Search

Search through conversation history:

```python
# Search for specific topics in context
results = context_manager.search_context(
    session_id=session_id,
    query="timer configuration",
    max_results=5
)
```

### 3. Context Analytics

Track conversation patterns and metrics:

```python
# Get conversation analytics
analytics = context_manager.get_analytics(session_id)
print(f"Total messages: {analytics['message_count']}")
print(f"Average response time: {analytics['avg_response_time']}")
print(f"Most discussed topics: {analytics['top_topics']}")
```

## Integration with Other Components

### TriggerManager Integration

```python
# Context is automatically provided to triggers
def trigger_validation(self, context: str, model: str) -> Dict[str, Any]:
    # Context includes recent conversation history
    # Triggers can use this for better validation
    pass
```

### Memory System Integration

```python
# Long-term memory integration
context_manager.integrate_memory_system(memory_manager)

# Context influences memory formation
memory_manager.process_context(context_manager.get_context(session_id))
```

## Performance Considerations

### Memory Management
- **Automatic Cleanup**: Old context is automatically removed based on time and message limits
- **Compression**: Context can be compressed for storage efficiency
- **Lazy Loading**: Context is loaded on-demand to reduce memory usage

### Optimization Tips
1. **Configure Appropriate Limits**: Set `max_context_duration` and `max_context_messages` based on your use case
2. **Enable Compression**: Use context compression for long-term storage
3. **Regular Cleanup**: Implement periodic cleanup of old sessions
4. **Monitor Memory Usage**: Track context manager memory consumption

## Error Handling

### Common Scenarios

```python
try:
    context = context_manager.get_context(session_id)
except ContextNotFoundError:
    # Handle missing context
    context = context_manager.create_session()
except ContextCorruptedError:
    # Handle corrupted context data
    context_manager.reset_context(session_id)
except ContextStorageError:
    # Handle storage issues
    logger.error("Context storage unavailable")
```

### Recovery Mechanisms
- **Automatic Recovery**: System attempts to recover from corrupted context
- **Fallback Context**: Uses minimal context if full context is unavailable
- **Graceful Degradation**: System continues functioning with reduced context

## Debugging and Monitoring

### Logging

```python
# Enable detailed context logging
context_manager.set_log_level("DEBUG")

# Monitor context operations
logger.info(f"Context added for session {session_id}")
logger.debug(f"Context buffer size: {context_manager.get_buffer_size()}")
```

### Metrics

```python
# Get context manager metrics
metrics = context_manager.get_metrics()
print(f"Active sessions: {metrics['active_sessions']}")
print(f"Total messages processed: {metrics['total_messages']}")
print(f"Average context size: {metrics['avg_context_size']}")
```

## Best Practices

1. **Session Lifecycle Management**: Always clean up inactive sessions
2. **Context Relevance**: Only include relevant context for current interaction
3. **Privacy Considerations**: Implement context anonymization for sensitive data
4. **Performance Monitoring**: Regular monitoring of context manager performance
5. **Graceful Shutdown**: Ensure context is properly saved during system shutdown

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| High memory usage | Context not being cleaned up | Reduce `max_context_duration` or `max_context_messages` |
| Context not persisting | Storage permissions issue | Check write permissions for `context_storage_path` |
| Context corruption | Unexpected shutdown | Enable auto-save with shorter intervals |
| Slow context retrieval | Large context size | Enable context compression |

### Debug Commands

```python
# Debug context state
context_manager.debug_session(session_id)

# Validate context integrity
context_manager.validate_context(session_id)

# Reset corrupted context
context_manager.reset_context(session_id, backup=True)
```