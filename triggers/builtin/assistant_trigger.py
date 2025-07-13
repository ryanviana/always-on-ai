"""
Assistant trigger for activating speech-to-speech conversation mode
"""

from typing import Dict, Any, List, Optional
from ..base import BaseTrigger


class AssistantTrigger(BaseTrigger):
    """Trigger for activating the AI assistant mode"""
    
    description = "Activate speech-to-speech conversation with AI assistant"
    language = "pt-BR"
    priority = 95  # Highest priority - overrides all other triggers
    
    # Direct activation without LLM validation for fast response
    activation_criteria = [
        "Direct activation phrases like 'Hey Bot', 'Fala Bot'",
        "Assistant wake words in Portuguese or English",
        "Clear intent to start conversation with the assistant"
    ]
    
    positive_examples = [
        "AlwaysOn",
        "Always On",
        "Hey bot",
        "Fala bot", 
        "Ei bot",
        "Oi bot",
        "Alô bot",
        "Ok bot",
        "Fala sócio",
        "Ei sócio", 
        "Oi sócio",
        "Meu sócio",
        "Olá assistente",
        "Bot, você está aí?",
        "Preciso falar com o bot",
        "Ativar assistente"
    ]
    
    negative_examples = [
        "O bot disse que...",  # Talking about the bot
        "Esse chatbot é útil",  # Mentioning bots in general
        "Robot processador",  # Different context
        "Botão vermelho",  # Different word
        "Boto cor de rosa"  # Different word (dolphin)
    ]
    
    edge_cases = [
        "Consider exact phrase matching for wake words",
        "Handle variations in pronunciation",
        "Distinguish from mentions of 'bot' in conversation",
        "React quickly without waiting for full sentence"
    ]
    
    response_schema = {
        "triggered": "boolean - always true for direct activation",
        "action": "string - always 'start_assistant'",
        "confidence": "float - 1.0 for exact matches",
        "matched_phrase": "string - which activation phrase was detected"
    }
    
    @property
    def keywords(self) -> List[str]:
        """Keywords that trigger initial detection"""
        return [
            # AlwaysOn wake word
            "alwayson", "always on",
            # Portuguese - Bot variations
            "hey bot", "fala bot", "ei bot", "oi bot", 
            "alô bot", "olá bot", "ok bot",
            # Portuguese - Sócio variations  
            "fala sócio", "ei sócio", "oi sócio", "meu sócio",
            "alô sócio", "olá sócio", "hey sócio",
            # Portuguese - Assistant
            "assistente", "ativar assistente",
            # English  
            "hey bot", "hi bot", "hello bot", "ok bot",
            "activate assistant", "assistant"
        ]
        
    def check_keywords(self, text: str) -> bool:
        """Override to do flexible phrase matching with common variations"""
        import re
        
        if not text:
            return False
            
        # Normalize text: lowercase, remove punctuation, normalize spaces
        text_normalized = re.sub(r'[,!?.:;]+', ' ', text.lower()).strip()
        text_normalized = re.sub(r'\s+', ' ', text_normalized)
        
        # Also check for common mistranscriptions
        # "bot" can be transcribed as "bote", "bort", "bots", "bats"
        text_variations = [text_normalized]
        if 'bote' in text_normalized:
            text_variations.append(text_normalized.replace('bote', 'bot'))
        if 'bort' in text_normalized:
            text_variations.append(text_normalized.replace('bort', 'bot'))
        if 'bots' in text_normalized:
            text_variations.append(text_normalized.replace('bots', 'bot'))
        if 'bats' in text_normalized:
            text_variations.append(text_normalized.replace('bats', 'bot'))
            
        # All wake word phrases (must match validate_with_llm)
        wake_phrases = [
            # AlwaysOn wake word
            "alwayson", "always on",
            # Bot variations
            "hey bot", "fala bot", "ei bot", "oi bot", "alô bot", "olá bot", "ok bot", 
            "hi bot", "hello bot",
            # Sócio variations
            "fala sócio", "ei sócio", "oi sócio", "meu sócio", "alô sócio", "olá sócio", "hey sócio",
            # Assistant variations
            "assistente", "ativar assistente"
        ]
        
        # Check all variations using simple substring search  
        print(f"[KEYWORDS] Checking: '{text_normalized}' -> variations: {text_variations}")
        for text_var in text_variations:
            for phrase in wake_phrases:
                # Simple substring search - much more reliable
                if phrase in text_var:
                    print(f"[KEYWORDS] ✓ Found '{phrase}' in '{text_var}'")
                    return True
                    
        # Check for other activation patterns
        activation_patterns = [
            "ativar assistente",
            "ativar o assistente", 
            "ativa o bot",
            "preciso falar com o bot",
            "quero falar com o assistente"
        ]
        
        for text_var in text_variations:
            for pattern in activation_patterns:
                if pattern in text_var:
                    return True
                    
        return False
        
    async def validate_with_llm(self, context: str, model: str = "gpt-4o-mini", 
                               template_env = None) -> Optional[Dict[str, Any]]:
        """Override to skip LLM validation for instant activation"""
        import re
        
        # Extract the current transcription
        context_lines = context.strip().split('\n')
        current_text = context_lines[-1] if context_lines else context
        
        # Normalize text: lowercase, remove punctuation, normalize spaces
        text_normalized = re.sub(r'[,!?.:;]+', ' ', current_text.lower())
        text_normalized = re.sub(r'\s+', ' ', text_normalized)
        text_normalized = text_normalized.strip()
        
        # Also check for common mistranscriptions (same logic as check_keywords)
        text_variations = [text_normalized]
        if 'bote' in text_normalized:
            text_variations.append(text_normalized.replace('bote', 'bot'))
        if 'bort' in text_normalized:
            text_variations.append(text_normalized.replace('bort', 'bot'))
        if 'bots' in text_normalized:
            text_variations.append(text_normalized.replace('bots', 'bot'))
        if 'bats' in text_normalized:
            text_variations.append(text_normalized.replace('bats', 'bot'))
            
        # All wake phrases - simplified list
        wake_phrases = [
            # AlwaysOn wake word
            "alwayson", "always on",
            # Bot variations
            "hey bot", "fala bot", "ei bot", "oi bot", "alô bot", "olá bot", "ok bot", 
            "hi bot", "hello bot",
            # Sócio variations
            "fala sócio", "ei sócio", "oi sócio", "meu sócio", "alô sócio", "olá sócio", "hey sócio",
            # Assistant variations
            "assistente", "ativar assistente"
        ]
        
        # Simple check - if any wake phrase appears anywhere in the text, activate
        matched_phrase = None
        print(f"[ASSISTANT DEBUG] Checking text: '{text_normalized}'")
        
        for text_var in text_variations:
            for phrase in wake_phrases:
                # Simple substring search - much more reliable
                if phrase in text_var:
                    matched_phrase = phrase
                    print(f"[ASSISTANT DEBUG] ✓ Matched! Found '{phrase}' in '{text_var}'")
                    break
            if matched_phrase:
                break
                
        if matched_phrase:
            return {
                "triggered": True,
                "action": "start_assistant",
                "confidence": 1.0,
                "matched_phrase": matched_phrase
            }
            
        # Check for other clear activation intents
        activation_patterns = [
            "ativar assistente", "ativar o assistente",
            "ativa o bot", "preciso falar com o bot"
        ]
        
        for pattern in activation_patterns:
            if pattern in text_normalized:
                return {
                    "triggered": True,
                    "action": "start_assistant", 
                    "confidence": 0.9,
                    "matched_phrase": current_text
                }
            
        return None
        
    def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action when trigger is validated"""
        matched_phrase = validation_result.get("matched_phrase", "")
        
        print(f"\n🤖 ASSISTANT TRIGGER ACTIVATED!")
        print(f"   Matched: {matched_phrase}")
        print(f"   Action: Starting speech-to-speech session")
        
        # Return special action type that signals to start assistant mode
        return {
            "action": "start_assistant",
            "speak": False,  # Don't use TTS, we're starting realtime session
            "metadata": {
                "activation_phrase": matched_phrase,
                "confidence": validation_result.get("confidence", 1.0)
            }
        }