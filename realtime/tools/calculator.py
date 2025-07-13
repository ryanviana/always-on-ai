"""
Calculator tool for Realtime API conversations
"""

import math
from typing import Dict, Any, Union
from .base import RealtimeTool


class CalculatorTool(RealtimeTool):
    """Tool for mathematical calculations"""
    
    def __init__(self, config=None):
        super().__init__(config)
    
    @property
    def estimated_duration(self) -> float:
        """Fast calculation"""
        return 0.5
        
    @property
    def feedback_message(self) -> str:
        """User-friendly message in Portuguese"""
        return "Calculando isso..."
        
    @property
    def category(self) -> str:
        """Tool category"""
        return "calculation"
    
    @property
    def schema(self) -> Dict[str, Any]:
        """OpenAI function schema"""
        return {
            "type": "function",
            "name": "calculator",
            "description": "Perform mathematical calculations",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2 + 2', '10 * 5', 'sqrt(16)')"
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["basic", "percentage", "power", "root", "trigonometry"],
                        "description": "Type of operation (optional, auto-detected from expression)"
                    }
                },
                "required": ["expression"]
            }
        }
        
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute calculation"""
        expression = params.get("expression", "").strip()
        
        if not expression:
            return {"error": "Expression is required"}
            
        try:
            # Sanitize and prepare expression
            safe_expr = self._prepare_expression(expression)
            
            # Define safe functions
            safe_dict = {
                "sqrt": math.sqrt,
                "pow": pow,
                "abs": abs,
                "round": round,
                "floor": math.floor,
                "ceil": math.ceil,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "asin": math.asin,
                "acos": math.acos,
                "atan": math.atan,
                "log": math.log,
                "log10": math.log10,
                "exp": math.exp,
                "pi": math.pi,
                "e": math.e
            }
            
            # Evaluate expression
            result = eval(safe_expr, {"__builtins__": {}}, safe_dict)
            
            # Format result
            if isinstance(result, float):
                # Round to reasonable precision
                if result == int(result):
                    result = int(result)
                else:
                    result = round(result, 6)
                    
            return {
                "expression": expression,
                "result": result,
                "formatted": self._format_result(result),
                "type": self._detect_operation_type(expression)
            }
            
        except ZeroDivisionError:
            return {
                "expression": expression,
                "error": "Divisão por zero",
                "error_type": "mathematical"
            }
        except ValueError as e:
            return {
                "expression": expression,
                "error": f"Erro matemático: {str(e)}",
                "error_type": "mathematical"
            }
        except SyntaxError:
            return {
                "expression": expression,
                "error": "Expressão inválida",
                "error_type": "syntax",
                "hint": "Verifique a sintaxe da expressão matemática"
            }
        except Exception as e:
            return {
                "expression": expression,
                "error": f"Erro no cálculo: {str(e)}",
                "error_type": "unknown"
            }
            
    def _prepare_expression(self, expr: str) -> str:
        """Prepare expression for safe evaluation"""
        # Replace common variations
        replacements = {
            "×": "*",
            "÷": "/",
            "²": "**2",
            "³": "**3",
            "√": "sqrt",
            "raiz": "sqrt",
            "potência": "pow",
            "seno": "sin",
            "cosseno": "cos",
            "tangente": "tan",
            " de ": "*",  # "10 de 5" -> "10*5"
            " por ": "*",  # "10 por 5" -> "10*5"
            " mais ": "+",
            " menos ": "-",
            " vezes ": "*",
            " dividido por ": "/",
            "%": "/100"  # Convert percentage
        }
        
        result = expr.lower()
        for old, new in replacements.items():
            result = result.replace(old, new)
            
        # Remove any remaining non-mathematical characters
        allowed = "0123456789+-*/().,^"
        allowed += "".join(["sqrt", "pow", "sin", "cos", "tan", "asin", "acos", 
                          "atan", "log", "exp", "abs", "round", "floor", "ceil",
                          "pi", "e"])
        
        # Basic safety check
        filtered = ""
        i = 0
        while i < len(result):
            if result[i].isalnum() or result[i] in allowed:
                filtered += result[i]
            elif result[i].isspace():
                filtered += " "
            i += 1
            
        return filtered.strip()
        
    def _format_result(self, result: Union[int, float]) -> str:
        """Format result in Portuguese"""
        if isinstance(result, int):
            # Format large numbers with dots as thousand separators
            return f"{result:,}".replace(",", ".")
        else:
            # Format float with comma as decimal separator
            formatted = f"{result:,.6f}".rstrip("0").rstrip(".")
            return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
            
    def _detect_operation_type(self, expression: str) -> str:
        """Detect the type of mathematical operation"""
        expr_lower = expression.lower()
        
        if any(trig in expr_lower for trig in ["sin", "cos", "tan", "seno", "cosseno", "tangente"]):
            return "trigonometry"
        elif any(op in expr_lower for op in ["sqrt", "raiz", "√"]):
            return "root"
        elif any(op in expr_lower for op in ["**", "^", "pow", "potência"]):
            return "power"
        elif "%" in expression:
            return "percentage"
        else:
            return "basic"