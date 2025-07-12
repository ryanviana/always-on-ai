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
SUPPORTED_LANGUAGES = {
    "portuguese": "pt",  # Portuguese language code
    "english": "en", 
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh",
    "russian": "ru",
    "dutch": "nl",
    "polish": "pl",
    "turkish": "tr",
    "arabic": "ar",
    "hindi": "hi"
}

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
    },
    
    "headphone_patterns": [
        r"headphone", r"airpods", r"beats", r"bose", r"sony", r"audio-technica",
        r"sennheiser", r"jabra", r"plantronics", r"skull", r"jbl", r"marshall",
        r"earbuds", r"earphones", r"in-ear", r"on-ear", r"over-ear", r"bluetooth",
        r"wireless", r"wh-", r"wf-", r"momentum", r"hd ", r"dt ", r"mdm", r"qc",
        r"quietcomfort", r"noise.?cancel", r"anc"
    ],
    "speaker_patterns": [
        r"speaker", r"monitor", r"studio", r"desktop", r"built.?in", r"internal",
        r"system", r"default", r"macbook", r"imac", r"soundbar", r"subwoofer",
        r"satellite", r"bookshelf", r"tower", r"amplifier", r"receiver", r"stereo"
    ]
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

# Session configuration template
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

# Transcription-only configuration - no triggers or TTS
TRANSCRIPTION_ONLY = True

# Conversation management configuration
CONVERSATION_CONFIG = {
    "enabled": True,  # Enable multi-turn conversation support
    "timeout_ms": 2000,  # Max time to wait for follow-up (milliseconds)
    "quick_response_ms": 500,  # Time to wait for seemingly complete queries
    "merge_transcriptions": True,  # Merge related transcriptions
    
    # Portuguese conversation starters and incomplete patterns
    "conversation_starters": [
        "ei", "oi", "olá", "alô", "escuta", "olha", "veja", 
        "me diga", "me fala", "você pode", "boti", "bote", "bot"
    ],
    
    # Incomplete query indicators
    "incomplete_indicators": [
        "hanging_prepositions",  # de, do, da, para, com, etc.
        "question_words_only",   # o que, quem, quando, etc.
        "verb_only",            # é, foi, está, etc.
        "command_without_object" # pesquisa, busca, etc.
    ]
}

# Simplified context management - disabled for transcription-only mode
CONTEXT_CONFIG = {
    "enabled": False
}

# Connection timeout for transcription
CONNECTION_TIMEOUT = 20.0  # Timeout for WebSocket connection in seconds

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