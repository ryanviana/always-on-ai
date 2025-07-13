"""
Base trigger class for all triggers
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json
import openai
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

load_dotenv()


class BaseTrigger(ABC):
    """Abstract base class for all triggers"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.enabled = True
        
    @property
    @abstractmethod
    def keywords(self) -> List[str]:
        """Keywords that trigger initial detection"""
        pass
        
    # Class variables for validation (override in subclasses)
    language: str = "pt-BR"
    priority: int = 50  # Default priority (0-100, higher = more priority)
    activation_criteria: List[str] = []
    positive_examples: List[str] = []
    negative_examples: List[str] = []
    edge_cases: List[str] = []
    response_schema: Dict[str, str] = {}
        
    @abstractmethod
    def action(self, validation_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Action to execute when trigger is validated
        
        Returns:
            Optional dict with:
                - text: The text response
                - speak: Whether to speak the response (default True)
                - voice_settings: Optional voice settings override
        """
        pass
        
    def check_keywords(self, text: str) -> bool:
        """Check if any trigger keywords are present in the text"""
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)
        
    def render_template(self, template_env: Environment, transcription_text: str, conversation_history: str = None) -> str:
        """Render the validation prompt using jinja2 template"""
        template = template_env.get_template("trigger_validation.j2")
        
        # Build context from class variables
        context = {
            "trigger_name": self.name,
            "keywords": self.keywords,
            "description": getattr(self, 'description', f"{self.name} trigger"),
            "transcription_text": transcription_text,
            "conversation_history": conversation_history,
            "trigger_language": self.language,
            "activation_criteria": self.activation_criteria,
            "positive_examples": self.positive_examples,
            "negative_examples": self.negative_examples,
            "edge_cases": self.edge_cases,
            "response_schema": self.response_schema
        }
        
        return template.render(**context)
        
    async def validate_with_llm(self, context: str, model: str = "gpt-4o-mini", template_env: Environment = None) -> Optional[Dict[str, Any]]:
        """Validate trigger with LLM using conversation context and jinja2 template"""
        try:
            # Create OpenAI client
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Render prompt using template
            if template_env:
                # Split context to get current transcription and history
                context_lines = context.strip().split('\n')
                current_transcription = context_lines[-1] if context_lines else context
                conversation_history = '\n'.join(context_lines[:-1]) if len(context_lines) > 1 else None
                
                prompt = self.render_template(template_env, current_transcription, conversation_history)
            else:
                # Fallback to basic prompt if no template environment
                prompt = f"Analyze this transcription for trigger '{self.name}': {context}"
            
            # Call OpenAI API
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a trigger validation system. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            # Parse response
            result_text = response.choices[0].message.content.strip()
            
            # Try to extract JSON from the response
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
                
            result = json.loads(result_text)
            
            # Check if trigger should fire
            if result.get("triggered", False):
                return result
            else:
                return None
                
        except Exception as e:
            print(f"Error validating trigger {self.name}: {e}")
            return None
            
    def __str__(self):
        return f"{self.name}(keywords={self.keywords})"