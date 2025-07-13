"""
Analysis API tool for integrating with HubSpot/Notion backend
"""

import aiohttp
import asyncio
from typing import Dict, Any
from .base import RealtimeTool


class AnalysisApiTool(RealtimeTool):
    """Tool for calling the Always-On AI Tools API for business analysis"""
    
    def __init__(self, config=None):
        super().__init__(config)
        # Override the automatic name generation to use underscore
        self.name = "analysis_api"
        self.default_endpoint = "http://localhost:3001/dashboard/data"
        self.request_timeout = 15.0  # 15 second timeout for LLM processing
        
    @property
    def estimated_duration(self) -> float:
        """API calls take longer due to LLM processing"""
        return 8.0
        
    @property
    def feedback_message(self) -> str:
        """User-friendly message in Portuguese"""
        return "Analisando dados do HubSpot e Notion..."
        
    @property
    def category(self) -> str:
        """Tool category"""
        return "business_intelligence"
        
    @property
    def configuration_schema(self) -> Dict[str, Any]:
        """Configuration schema for the tool"""
        return {
            "type": "object",
            "properties": {
                "endpoint_url": {
                    "type": "string",
                    "description": "Custom endpoint URL for the analysis API"
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds",
                    "minimum": 1,
                    "maximum": 30
                }
            }
        }
        
    @property
    def schema(self) -> Dict[str, Any]:
        """OpenAI function schema"""
        return {
            "type": "function",
            "name": "analysis_api",
            "description": "REQUIRED: Use this tool when user asks for business analysis of contacts, leads, marketing insights, or data from HubSpot/Notion. Examples: 'analise meus contatos', 'identifique leads promissores', 'que segmentos temos', 'sugira estratégia de marketing'",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Context for the analysis (e.g., 'análise de leads', 'segmentação de contatos', 'estratégia de marketing')"
                    },
                    "prompt": {
                        "type": "string", 
                        "description": "Specific analytical request or question (e.g., 'Identifique os 3 leads mais promissores', 'Que segmentos de empresa estão representados?', 'Sugira conteúdo para cada segmento')"
                    },
                    "endpoint_url": {
                        "type": "string",
                        "description": "Optional custom endpoint URL (defaults to localhost:3001)"
                    }
                },
                "required": ["context", "prompt"]
            }
        }
        
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute analysis API call"""
        context = params.get("context", "").strip()
        prompt = params.get("prompt", "").strip()
        endpoint_url = params.get("endpoint_url", "").strip() or self.get_config("endpoint_url", self.default_endpoint)
        timeout = self.get_config("timeout", self.request_timeout)
        
        # Validate required parameters
        if not context:
            return {"error": "Context é obrigatório para a análise"}
            
        if not prompt:
            return {"error": "Prompt é obrigatório para especificar o que analisar"}
            
        # Prepare request data
        request_data = {
            "context": context,
            "prompt": prompt
        }
        
        try:
            # Create timeout for the request
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.post(
                    endpoint_url,
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    # Check if request was successful
                    if response.status == 200:
                        response_data = await response.json()
                        return self._format_analysis_response(response_data, context, prompt)
                    
                    elif response.status == 404:
                        return self._mock_analysis_response(context, prompt, "Backend não encontrado na porta 3001")
                    
                    elif response.status == 500:
                        error_text = await response.text()
                        return {"error": f"Erro interno do servidor de análise: {error_text[:200]}"}
                    
                    else:
                        return {"error": f"Erro da API de análise: HTTP {response.status}"}
                        
        except aiohttp.ClientConnectorError:
            # Backend is not running - provide mock response
            return self._mock_analysis_response(context, prompt, "Backend não está rodando")
            
        except asyncio.TimeoutError:
            return {"error": f"Timeout na API de análise (limite: {timeout}s). Backend pode estar sobrecarregado."}
            
        except aiohttp.ClientError as e:
            return {"error": f"Erro de conexão com API de análise: {str(e)}"}
            
        except Exception as e:
            return {"error": f"Erro inesperado na análise: {str(e)}"}
            
    def _format_analysis_response(self, response_data: Dict[str, Any], 
                                context: str, prompt: str) -> Dict[str, Any]:
        """Format the API response for better presentation"""
        try:
            # Extract main components
            llm_response = response_data.get("llm_response", "")
            hubspot_contacts = response_data.get("hubspot_contacts", [])
            notion_page_text = response_data.get("notion_page_text", "")
            
            # Process contacts data
            contact_count = len(hubspot_contacts) if isinstance(hubspot_contacts, list) else 0
            
            # Build summary
            summary = {
                "analysis_context": context,
                "analysis_prompt": prompt,
                "llm_analysis": llm_response,
                "data_summary": {
                    "total_contacts": contact_count,
                    "has_notion_data": bool(notion_page_text.strip()),
                    "notion_content_length": len(notion_page_text) if notion_page_text else 0
                }
            }
            
            # Add contact details if available and reasonable number
            if hubspot_contacts and contact_count <= 10:
                summary["contact_details"] = []
                for contact in hubspot_contacts:
                    if isinstance(contact, dict):
                        contact_info = {
                            "name": contact.get("firstname", "") + " " + contact.get("lastname", ""),
                            "email": contact.get("email", ""),
                            "company": contact.get("company", ""),
                            "status": contact.get("hs_lead_status", "")
                        }
                        # Only add if it has meaningful data
                        if any(contact_info.values()):
                            summary["contact_details"].append(contact_info)
            
            # Add notion content if reasonable size
            if notion_page_text and len(notion_page_text) <= 1000:
                summary["notion_content"] = notion_page_text
            elif notion_page_text:
                summary["notion_content_preview"] = notion_page_text[:500] + "..."
                
            return summary
            
        except Exception as e:
            # If formatting fails, return raw response with error note
            return {
                "analysis_context": context,
                "analysis_prompt": prompt,
                "raw_response": response_data,
                "formatting_note": f"Resposta recebida mas houve erro na formatação: {str(e)}"
            }
            
    def _mock_analysis_response(self, context: str, prompt: str, reason: str) -> Dict[str, Any]:
        """Generate a mock response when the backend is unavailable"""
        return {
            "analysis_context": context,
            "analysis_prompt": prompt,
            "llm_analysis": f"""
**Análise Mock para: {prompt}**

Esta é uma resposta simulada porque {reason}.

**Insights Simulados:**
• Lead mais promissor: João Silva (joao@empresa.com) - Empresa ABC Tech
• Segmento principal: Tecnologia (45% dos contatos)
• Oportunidade: Upsell para clientes existentes no setor de SaaS
• Recomendação: Criar campanha focada em automação para PMEs

**Próximos Passos:**
1. Verificar se o backend está rodando na porta 3001
2. Configurar APIs do HubSpot e Notion
3. Re-executar análise com dados reais

Para dados reais, certifique-se de que o backend Always-On AI Tools esteja rodando.
            """.strip(),
            "data_summary": {
                "total_contacts": 0,
                "has_notion_data": False,
                "notion_content_length": 0,
                "mock_data": True,
                "reason": reason
            },
            "note": f"Dados simulados - {reason}. Configure o backend na porta 3001 para análises reais."
        }