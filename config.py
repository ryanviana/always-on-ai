"""
Centralized configuration for all models and settings
"""

import os

# OpenAI Models
TRANSCRIPTION_MODELS = {
    "gpt-4o-transcribe": "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe": "gpt-4o-mini-transcribe", 
    "whisper-1": "whisper-1"
}

CONVERSATION_MODELS = {
    "gpt-4o-realtime": "gpt-4o-realtime-preview-2025-06-03",
    "gpt-4o-mini-realtime": "gpt-4o-mini-realtime-preview-2024-12-17"
}

# Default model selections
DEFAULT_TRANSCRIPTION_MODEL = TRANSCRIPTION_MODELS["gpt-4o-transcribe"]
DEFAULT_CONVERSATION_MODEL = CONVERSATION_MODELS["gpt-4o-realtime"]

# Language settings
DEFAULT_LANGUAGE = "pt"  # Portuguese (includes Brazilian Portuguese)

# Audio settings
AUDIO_CONFIG = {
    "sample_rate": 16000,
    "channels": 1,
    "chunk_size": 1024,
    "input_format": "pcm16"
}

# Audio device detection and feedback prevention settings
AUDIO_DEVICE_CONFIG = {
    "auto_detect_device_type": True,
    "manual_override": None,  # "speakers", "headphones", or None
    "speaker_feedback_prevention": "aggressive",  # "aggressive", "moderate", "off"
    "headphone_interruption_enabled": True,
    
    # Echo prevention timing settings (in seconds)
    "speaker_echo_delay": {
        "min_silence_time": 1.0,      # Minimum silence before resuming input
        "dead_zone_duration": 0.5,    # Ignore input for this duration after resume
        "max_wait_time": 30.0,        # Maximum time to wait for safe conditions before forcing resume
        "check_interval": 0.2         # How often to check if safe to resume
    }
}

# VAD (Voice Activity Detection) settings
VAD_CONFIG = {
    "server_vad": {
        "type": "server_vad",
        "threshold": 0.4,  # Lower threshold for better speech detection
        "silence_duration_ms": 700,  # More time for natural pauses in Portuguese
        "prefix_padding_ms": 400  # Capture more context before speech
    },
    "semantic_vad": {
        "type": "semantic_vad",
        "eagerness": "medium"  # low, medium, high, auto
    }
}

# Default VAD settings for different modes
DEFAULT_VAD = VAD_CONFIG["server_vad"]  # Default for transcription
DEFAULT_CONVERSATION_VAD = VAD_CONFIG["semantic_vad"]  # Default for conversation

# API endpoints
API_ENDPOINTS = {
    "realtime": "wss://api.openai.com/v1/realtime",
    "transcription": "wss://api.openai.com/v1/realtime?intent=transcription"
}

# Noise reduction settings
NOISE_REDUCTION_CONFIG = {
    "near_field": {"type": "near_field"},
    "far_field": {"type": "far_field"},
    "disabled": None
}

DEFAULT_NOISE_REDUCTION = NOISE_REDUCTION_CONFIG["near_field"]

# Headers for API requests
API_HEADERS = {
    "OpenAI-Beta": "realtime=v1"
}

# Display settings
DISPLAY_CONFIG = {
    "colors": {
        "partial": "\033[93m",  # Yellow
        "final": "\033[92m",    # Green
        "error": "\033[91m",    # Red
        "info": "\033[94m",     # Blue
        "reset": "\033[0m"      # Reset
    },
    "emojis": {
        "mic": "🎤",
        "speaker": "🔊",
        "speech": "🗣️",
        "error": "❌",
        "success": "✅",
        "stop": "🛑",
        "rocket": "🚀"
    }
}

# Session configuration functions
def get_transcription_session_config(
    model=None, 
    vad_config=None, 
    noise_reduction=None,
    include_logprobs=False,
    language=None
):
    """Get transcription session configuration"""
    # Try with session wrapper for transcription_session.update
    session_config = {
        "input_audio_format": AUDIO_CONFIG["input_format"],
        "input_audio_transcription": {
            "model": model or DEFAULT_TRANSCRIPTION_MODEL,
            "prompt": "Transcreva o áudio em português brasileiro com precisão. Mantenha pontuação e capitalização apropriadas.",
            "language": language or "pt"
        },
        "turn_detection": vad_config or DEFAULT_VAD,
        "input_audio_noise_reduction": noise_reduction or DEFAULT_NOISE_REDUCTION
    }
    
    # Only add include if logprobs are requested
    if include_logprobs:
        session_config["include"] = ["item.input_audio_transcription.logprobs"]
    
    return {
        "type": "transcription_session.update",
        "session": session_config
    }

def get_conversation_session_config(
    model=None,
    vad_config=None,
    voice="verse"
):
    """Get conversation session configuration"""
    return {
        "type": "session.update",
        "session": {
            "model": model or DEFAULT_CONVERSATION_MODEL,
            "voice": voice,
            "turn_detection": vad_config or DEFAULT_VAD,
            "input_audio_format": AUDIO_CONFIG["input_format"],
            "output_audio_format": AUDIO_CONFIG["input_format"]
        }
    }

# Trigger system configuration
TRIGGER_CONFIG = {
    "enabled": True,
    "buffer_duration_seconds": 60,
    "llm_model": "gpt-4o-mini",  # Model for validation
    "enabled_triggers": ["assistant", "test"],  # Assistant and test triggers enabled
    "async_validation": True,
    "validation_timeout": 8.0  # seconds
}

# TTS system configuration - Using OpenAI client library (NOT Realtime API)
TTS_CONFIG = {
    "enabled": True,
    "provider": "openai",  # Using OpenAI client library for TTS
    "model": "tts-1",  # OpenAI TTS model (tts-1 or tts-1-hd)
    "voice": "alloy",  # Available voices: alloy, echo, fable, onyx, nova, shimmer
    "speed": 1.0,  # Speech speed (0.25 to 4.0)
    "language": "pt-BR",  # Portuguese (Brazil)
    "output_audio_format": "pcm",  # Raw PCM format
    "output_sample_rate": 24000,  # Native 24kHz output
    
    # Queue and processing settings
    "queue_size": 10,
    "playback_chunk_size": 2048,  # Larger chunks for 24kHz
    "mixing_enabled": True,  # Allow overlapping TTS responses
    
    # Interruption settings
    "allow_interruption": True,  # Enable/disable TTS interruption
    "interruption_fade_ms": 50,  # Fade duration in ms to avoid audio pop
    "interruption_debounce_ms": 100,  # Debounce to prevent false triggers
    
    # Echo prevention settings
    "hardware_latency_delay": 0.3  # Additional delay after playback completes
}

# Conversation management configuration
CONVERSATION_CONFIG = {
    "enabled": True,  # Enable multi-turn conversation support
    "timeout_ms": 2000,  # Max time to wait for follow-up (milliseconds)
    "quick_response_ms": 500,  # Time to wait for seemingly complete queries
    "merge_transcriptions": True  # Merge related transcriptions
}

# Enhanced context management configuration
CONTEXT_CONFIG = {
    "enabled": True,
    "raw_window_minutes": 5,  # Minutes to keep in raw format
    "summarization_model": "gpt-4o-mini",  # Model for summarization
    "persistence": {
        "enabled": True,
        "directory": "./context",
        "max_file_size_mb": 10,
        "auto_save_interval": 30  # Seconds
    }
}

# Tool system configuration
TOOL_CONFIG = {
    "enabled_tools": ["datetime", "analysis_api"],  # DateTime and Analysis API tools enabled
    "tool_directories": ["./realtime/tools"],  # Where to look for tools
    "auto_discover": True  # Auto-discover tools from directories
}

# Assistant mode configuration
ASSISTANT_CONFIG = {
    "enabled": True,
    "activation_phrases": [
        "hey bot", "fala bot", "ei bot", "oi bot", 
        "alô bot", "olá bot", "ok bot", "hi bot", "hello bot"
    ],
    "end_phrases": [
        "obrigado bot", "obrigada bot", "thank you bot", "thanks bot",
        "tchau bot", "bye bot", "até logo bot", "goodbye bot",
        "encerrar conversa", "end conversation", "terminar sessão"
    ],
    "session_timeout": 300,  # Maximum session duration in seconds (5 minutes)
    "model": "gpt-4o-realtime-preview-2025-06-03",  # Realtime model for assistant
    "voice": "alloy",  # Voice for assistant responses
    "tools_enabled": ["datetime", "calculator", "search", "weather", "analysis_api"],  # All available tools
    "auto_end_silence": 30,  # Seconds of silence before auto-ending session
    "vad_mode": "server_vad",  # VAD mode for assistant sessions
    "vad_config": {
        "type": "server_vad",
        "threshold": 0.4,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 700
    }
}

# Realtime API configuration
REALTIME_CONFIG = {
    "api_endpoint": "wss://api.openai.com/v1/realtime",
    "api_version": "v1",
    "audio_format": "pcm16",  # Audio format for input/output
    "sample_rate": 24000,  # Native sample rate for Realtime API
    "connection_timeout": 20.0,  # Timeout for WebSocket connection in seconds
    "vad_config": {
        "type": "server_vad",
        "threshold": 0.4,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 700
    }
}

# Logging configuration
LOGGING_CONFIG = {
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
    "log_dir": os.getenv("LOG_DIR", "./logs"),
    "enable_file_logging": os.getenv("ENABLE_FILE_LOGGING", "true").lower() == "true",
    "enable_console_logging": os.getenv("ENABLE_CONSOLE_LOGGING", "true").lower() == "true", 
    "structured_logging": os.getenv("ENVIRONMENT", "development").lower() == "production",
    "max_log_size_mb": int(os.getenv("MAX_LOG_SIZE_MB", "10")),
    "backup_count": int(os.getenv("LOG_BACKUP_COUNT", "5")),
}