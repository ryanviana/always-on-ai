"""
Assistant Mode trigger for speech-to-speech conversations
"""

from typing import Dict, Any, List, Optional
from ..base import BaseTrigger
from config import ASSISTANT_MODE_CONFIG


class AssistantTrigger(BaseTrigger):
    """Assistant Mode trigger that activates speech-to-speech conversations"""
    
    description = "Activate Assistant Mode for speech-to-speech conversations"
    language = "pt-BR"
    priority = 95  # Very high priority - should override most other triggers
    
    activation_criteria = [
        "Direct assistant wake phrases in Portuguese or English",
        "Clear intent to start a conversation with the AI assistant",
        "Natural conversational requests for assistance",
        "Voice commands that expect interactive responses"
    ]
    
    positive_examples = [
        "Assistente, me ajuda com uma coisa?",
        "Hey assistente, qual é a previsão do tempo?",
        "Olá assistente, você pode me explicar algo?",
        "Assistant, can you help me?",
        "Ei assistente, preciso de ajuda",
        "Assistente, o que você sabe sobre...",
        "Hey assistant, what's the weather like?"
    ]
    
    negative_examples = [
        "Vou assistir um filme (watching, not assistant)",
        "O assistente social vai vir (social worker, not AI)",
        "Preciso de um assistente administrativo (human assistant)",
        "Assistant manager position (job title)",
        "Research assistant job (human role)",
        "Assistente de palco (stage assistant)"
    ]
    
    edge_cases = [
        "Distinguish between AI assistant vs human assistant contexts",
        "Recognize wake phrases even with background noise or interruptions",
        "Handle variations in pronunciation or accents",
        "Consider context - is this about THIS AI assistant or something else?",
        "Detect intent even if wake phrase is embedded in longer sentence"
    ]
    
    response_schema = {
        "triggered": "boolean - whether assistant mode should activate",
        "reason": "string - explanation of why assistant mode was triggered",
        "confidence": "float - confidence score 0-1",
        "wake_phrase": "string - the specific wake phrase detected",
        "intent": "string - categorized user intent (help_request, question, conversation_start, etc)",
        "context_summary": "string - brief summary of what the user seems to want"
    }
    
    @property
    def keywords(self) -> List[str]:
        """Wake phrases that trigger assistant mode"""
        return ASSISTANT_MODE_CONFIG.get("wake_phrases", [
            # Default wake phrases if config is not available
            "assistente", "assistant", "ei assistente", "hey assistant"
        ])
        
    def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the assistant mode trigger action"""
        wake_phrase = validation_result.get("wake_phrase", "assistente")
        intent = validation_result.get("intent", "conversation_start")
        reason = validation_result.get("reason", "Assistant wake phrase detected")
        
        self.logger.info("🎯 ASSISTANT MODE TRIGGER FIRED!")
        self.logger.info(f"Wake phrase: {wake_phrase}")
        self.logger.info(f"Intent: {intent}")
        self.logger.info(f"Reason: {reason}")
        
        # Return special response that signals to start conversation mode
        return {
            "text": None,  # No TTS response - conversation mode will handle audio
            "speak": False,
            "action_type": "start_conversation",  # Special action type
            "conversation_data": {
                "wake_phrase": wake_phrase,
                "intent": intent,
                "validation_result": validation_result
            }
        }