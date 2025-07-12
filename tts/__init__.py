"""
TTS (Text-to-Speech) module for voice output
"""

from .openai_tts_simple import OpenAITTSService
from .audio_output import AudioOutputManager

__all__ = ['OpenAITTSService', 'AudioOutputManager']