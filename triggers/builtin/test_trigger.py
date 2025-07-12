"""
Test trigger for demonstration
"""

from typing import Dict, Any, List, Optional
from ..base import BaseTrigger


class TestTrigger(BaseTrigger):
    """Simple test trigger that fires when 'trigger test' is mentioned"""
    
    description = "Test trigger to validate the trigger system is working"
    language = "pt-BR"
    priority = 70  # Medium-high priority - system command
    
    activation_criteria = [
        "Direct test commands in Portuguese",
        "System validation requests", 
        "Demonstration of trigger functionality",
        "Debug or verification requests"
    ]
    
    positive_examples = [
        "Executar teste do sistema",
        "Fazer um teste para ver se funciona",
        "Testar os gatilhos", 
        "Roda um teste aí"
    ]
    
    negative_examples = [
        "Estou testando meu microfone (testing hardware)",
        "Vou fazer um teste de matemática (academic test)",
        "O teste de COVID deu negativo (medical test)"
    ]
    
    edge_cases = [
        "Distinguish between system tests vs other types of tests",
        "Consider context - is it about THIS system or external testing?",
        "Handle informal commands vs formal requests"
    ]
    
    response_schema = {
        "triggered": "boolean - whether trigger should activate",
        "reason": "string - explanation of why trigger activated",
        "confidence": "float - confidence score 0-1",
        "extracted_intent": "string - categorized intent (system_validation, demo, etc)"
    }
    
    @property
    def keywords(self) -> List[str]:
        return [
            # English
            "trigger", "test", "testing",
            # Portuguese
            "testar", "teste", "testando", "gatilho"
        ]
        
    def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the test trigger action"""
        reason = validation_result.get("reason", "No reason provided")
        print(f"\n🎯 TEST TRIGGER FIRED!")
        print(f"   Reason: {reason}")
        print(f"   This confirms the trigger system is working!\n")
        
        # Return TTS response
        return {
            "text": "Teste executado com sucesso! O sistema de gatilhos está funcionando perfeitamente.",
            "speak": True,
            "voice_settings": {"speed": 1.0}
        }