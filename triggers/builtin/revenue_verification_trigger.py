"""
Revenue verification trigger for validating business data during discussions
"""

from typing import Dict, Any, List, Optional
import aiohttp
import asyncio
import json
from ..base import BaseTrigger


class RevenueVerificationTrigger(BaseTrigger):
    """Trigger for verifying revenue and business data in conversations"""
    
    description = "Verify revenue and business data accuracy during discussions"
    language = "pt-BR"
    priority = 85  # High priority for business critical data
    
    activation_criteria = [
        "Discussion about revenue, faturamento, or financial metrics",
        "Mentioning specific revenue numbers or percentages",
        "Talking about sales performance or financial results",
        "Discussing business metrics that involve money"
    ]
    
    positive_examples = [
        "Nosso faturamento esse mês foi de 150 mil",
        "Tivemos um crescimento de 30% no faturamento",
        "A receita mensal está em 200 mil reais",
        "Vendemos 50 mil em produtos ontem",
        "O ticket médio subiu para 5 mil",
        "Nossa margem de lucro é 40%",
        "Faturamos 2 milhões esse ano",
        "A meta de vendas é 300 mil por mês"
    ]
    
    negative_examples = [
        "Vamos falar sobre faturamento depois",  # Not discussing actual numbers
        "Como calcular o faturamento?",  # Question about process, not data
        "O sistema de faturamento está lento",  # About system, not numbers
        "Preciso revisar a planilha",  # No specific data mentioned
        "Qual foi nosso resultado?",  # Asking, not stating data
    ]
    
    edge_cases = [
        "Only trigger when specific numbers are mentioned",
        "Must be a statement about revenue, not a question",
        "Should detect various formats: 150k, 150 mil, 150.000",
        "Consider percentage claims about growth or margins"
    ]
    
    response_schema = {
        "triggered": "boolean - true if revenue data needs verification",
        "revenue_claim": "string - the specific revenue claim made",
        "data_type": "string - type of data (revenue, growth, margin, etc)",
        "needs_verification": "boolean - whether to call verify_data API"
    }
    
    def __init__(self):
        super().__init__()
        self.verify_endpoint = "http://localhost:3001/verify-data"
        self.request_timeout = 10.0
    
    @property
    def keywords(self) -> List[str]:
        """Keywords that trigger initial detection"""
        return [
            # Revenue terms
            "faturamento", "faturamos", "faturou", "faturando",
            "receita", "receitas", "recebemos",
            "vendas", "vendemos", "vendeu", "venda",
            "lucro", "lucramos", "lucrou", "margem",
            # Currency
            "real", "reais", "r$",
            # Portuguese number words
            "mil", "milhão", "milhões", "bilhão", "bilhões",
            "cem", "duzentos", "trezentos", "quatrocentos", "quinhentos",
            "seiscentos", "setecentos", "oitocentos", "novecentos",
            # Growth terms
            "crescimento", "cresceu", "aumentou",
            "caiu", "diminuiu", "reduziu",
            # Percentage terms
            "por cento", "%", "porcento", "percentual",
            # Financial metrics
            "ticket médio", "valor médio", "média",
            "meta", "objetivo", "target",
            # Business terms
            "negócio", "empresa", "companhia",
            "cliente", "clientes", "contrato", "contratos"
        ]
        
    # Remove the check_keywords override to use the simpler base class implementation
    # The base class already checks if any keyword is in the text, which is more flexible
        
    async def validate_with_llm(self, context: str, model: str = "gpt-4o-mini", 
                               template_env = None) -> Optional[Dict[str, Any]]:
        """Validate if revenue data needs verification"""
        result = await super().validate_with_llm(context, model, template_env)
        
        if result and result.get("triggered"):
            # Extract the specific claim for verification
            context_lines = context.strip().split('\n')
            current_text = context_lines[-1] if context_lines else context
            
            result["_original_text"] = current_text
            result["needs_verification"] = True
            
        return result
        
    async def _verify_data(self, revenue_claim: str, data_type: str) -> Dict[str, Any]:
        """Call the verify_data API endpoint"""
        try:
            # Format the request to match backend expectations
            request_data = {
                "context": f"Verificação de dados de {data_type}",
                "prompt": f"""Alguém afirmou: "{revenue_claim}"
                
Por favor, verifique se essa informação está correta com base nos dados do HubSpot.
Se estiver INCORRETA, responda APENAS com:
INCORRETO: [explicação breve do valor correto]

Se estiver CORRETA ou não puder verificar, responda APENAS com:
CORRETO

Seja extremamente objetivo na resposta."""
            }
            
            timeout_config = aiohttp.ClientTimeout(total=self.request_timeout)
            
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.post(
                    self.verify_endpoint,
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        llm_response = result.get("response", "").strip()
                        
                        # Parse the LLM response to determine if correction is needed
                        if llm_response.startswith("INCORRETO:"):
                            correction_text = llm_response.replace("INCORRETO:", "").strip()
                            return {
                                "verified": False,
                                "correction": correction_text
                            }
                        else:
                            return {
                                "verified": True,
                                "correction": None
                            }
                    else:
                        return {
                            "verified": False,
                            "error": f"API returned status {response.status}",
                            "correction": None
                        }
                        
        except aiohttp.ClientConnectorError:
            return {
                "verified": False,
                "error": "Verify API not available",
                "correction": None
            }
        except Exception as e:
            return {
                "verified": False,
                "error": str(e),
                "correction": None
            }
    
    def action(self, validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute verification and return TTS response if needed"""
        revenue_claim = validation_result.get("revenue_claim", "")
        data_type = validation_result.get("data_type", "revenue")
        
        print(f"\n💰 REVENUE VERIFICATION TRIGGER ACTIVATED!")
        print(f"   Claim: {revenue_claim}")
        print(f"   Type: {data_type}")
        
        # Run verification synchronously in a thread to avoid event loop conflicts
        import concurrent.futures
        import threading
        
        verification_result = None
        error = None
        
        def run_verify():
            nonlocal verification_result, error
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                verification_result = loop.run_until_complete(
                    self._verify_data(revenue_claim, data_type)
                )
            except Exception as e:
                error = e
            finally:
                loop.close()
        
        # Run in thread
        thread = threading.Thread(target=run_verify)
        thread.start()
        thread.join(timeout=10.0)  # Wait up to 10 seconds
        
        if error:
            print(f"   Error during verification: {error}")
            return {
                "action": "no_response",
                "metadata": {
                    "error": str(error)
                }
            }
            
        if not verification_result:
            print("   Verification timed out")
            return {
                "action": "no_response",
                "metadata": {
                    "error": "Verification timed out"
                }
            }
            
        # If data is incorrect, prepare TTS response
        if not verification_result.get("verified") and verification_result.get("correction"):
            correction = verification_result["correction"]
            
            response_text = f"Só uma correção: {correction}"
            
            return {
                "text": response_text,
                "speak": True,  # Enable TTS
                "voice_settings": {
                    "voice": "nova",  # Professional voice
                    "speed": 0.95    # Slightly slower for clarity
                },
                "metadata": {
                    "original_claim": revenue_claim,
                    "correction": correction,
                    "data_type": data_type
                }
            }
        else:
            # Data is correct or couldn't be verified
            print(f"   Verification: {'✓ Correct' if verification_result.get('verified') else '? Could not verify'}")
            return {
                "action": "no_response",  # Don't interrupt if data is correct
                "metadata": {
                    "verification_result": verification_result
                }
            }