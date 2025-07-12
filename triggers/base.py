"""
Base trigger class for all triggers
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import os
from pathlib import Path
from jinja2 import Environment
import openai

from .models import TriggerConfig, ValidationResult, TriggerResponse, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS
from .utils import parse_llm_json_response, setup_trigger_logger
from .exceptions import TriggerValidationError, LLMConnectionError


class BaseTrigger(ABC):
    """Abstract base class for all triggers"""
    
    # Class-level OpenAI client cache
    _openai_client = None
    _api_key_checked = False
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.enabled = True
        self.logger = setup_trigger_logger(f"trigger.{self.name}")
        
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
        """
        Action to execute when trigger is validated
        
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
        
    def render_template(self, template_env: Environment, transcription_text: str, 
                       conversation_history: Optional[str] = None) -> str:
        """
        Render the validation prompt using jinja2 template
        
        Args:
            template_env: Jinja2 environment
            transcription_text: Current transcription
            conversation_history: Optional conversation context
            
        Returns:
            Rendered template string
        """
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
    
    @classmethod
    def _get_openai_client(cls):
        """Get or create the shared OpenAI client"""
        # Check if we already have a client
        if cls._openai_client is not None:
            return cls._openai_client
        
        # Check API key only once
        if not cls._api_key_checked:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise LLMConnectionError("OPENAI_API_KEY not found in environment")
            cls._api_key_checked = True
            
            # Create the client once
            cls._openai_client = openai.AsyncOpenAI(api_key=api_key)
        
        return cls._openai_client
        
    async def validate_with_llm(self, context: str, model: str = "gpt-4o-mini", 
                               template_env: Optional[Environment] = None) -> Optional[Dict[str, Any]]:
        """Validate trigger with LLM using conversation context and jinja2 template"""
        try:
            # Get the shared OpenAI client
            client = self._get_openai_client()
            
            self.logger.debug(f"Validating with {model}")
            
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
            self.logger.debug("Calling OpenAI API")
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a trigger validation system. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS
            )
            
            # Parse response
            result_text = response.choices[0].message.content.strip()
            result_dict = parse_llm_json_response(result_text)
            
            # Check if trigger should fire
            triggered = result_dict.get("triggered", False)
            confidence = result_dict.get("confidence", 0.0)
            
            if triggered:
                self.logger.info(f"Validation SUCCESS (confidence: {confidence:.2f})")
                return result_dict
            else:
                self.logger.debug(f"Validation REJECTED (confidence: {confidence:.2f})")
                return None
                
        except Exception as e:
            self.logger.error(f"Validation error: {e}", exc_info=True)
            return None
            
    def __str__(self):
        return f"{self.name}(keywords={self.keywords})"