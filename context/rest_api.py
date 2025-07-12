"""
HTTP server for REST API access to context
"""

import json
import threading
import time
import os
import hashlib
import secrets
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 100  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_STORAGE = defaultdict(lambda: {"count": 0, "window_start": time.time()})

# Authentication configuration
API_KEY_HEADER = "X-API-Key"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")

# Generate or load API key
API_KEY_FILE = os.path.join(os.path.dirname(__file__), ".api_key")
if os.path.exists(API_KEY_FILE):
    with open(API_KEY_FILE, 'r') as f:
        API_KEY = f.read().strip()
else:
    API_KEY = secrets.token_urlsafe(32)
    with open(API_KEY_FILE, 'w') as f:
        f.write(API_KEY)
    logger.info(f"Generated new API key: {API_KEY}")


class ContextHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for context API"""
    
    def _check_rate_limit(self, client_ip: str) -> bool:
        """Check if client has exceeded rate limit"""
        current_time = time.time()
        client_data = RATE_LIMIT_STORAGE[client_ip]
        
        # Reset window if needed
        if current_time - client_data["window_start"] > RATE_LIMIT_WINDOW:
            client_data["count"] = 0
            client_data["window_start"] = current_time
        
        # Check limit
        if client_data["count"] >= RATE_LIMIT_REQUESTS:
            return False
        
        client_data["count"] += 1
        return True
    
    def _check_auth(self) -> bool:
        """Check if request has valid authentication"""
        # Check API key header
        api_key = self.headers.get(API_KEY_HEADER)
        if not api_key:
            return False
        
        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(api_key, API_KEY)
    
    def _get_allowed_origin(self) -> str:
        """Get allowed origin for CORS"""
        origin = self.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS:
            return origin
        return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else 'null'
    
    def _send_error_response(self, code: int, message: str):
        """Send error response without exposing internal details"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', self._get_allowed_origin())
        self.end_headers()
        
        error_response = {
            "error": message,
            "status": code
        }
        self.wfile.write(json.dumps(error_response).encode())
    
    def do_GET(self):
        """Handle GET requests"""
        # Rate limiting
        client_ip = self.client_address[0]
        if not self._check_rate_limit(client_ip):
            self._send_error_response(429, "Rate limit exceeded")
            return
        
        # Authentication (skip for root endpoint)
        parsed_path = urlparse(self.path)
        if parsed_path.path != '/' and not self._check_auth():
            self._send_error_response(401, "Unauthorized")
            return
        
        # Set CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', self._get_allowed_origin())
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', f'Content-Type, {API_KEY_HEADER}')
        self.end_headers()
        
        try:
            if parsed_path.path == '/context':
                # Get full context
                context = self.server.context_manager.get_full_context()
                self.wfile.write(json.dumps(context, indent=2).encode())
                
            elif parsed_path.path == '/context/formatted':
                # Get formatted context (ready for display)
                context = self.server.context_manager.get_full_context()
                response = {
                    "formatted": context.get("formatted", ""),
                    "timestamp": context.get("stats", {}).get("summary_age_minutes", 0)
                }
                self.wfile.write(json.dumps(response, indent=2).encode())
                
            elif parsed_path.path == '/stats':
                # Get statistics
                stats = self.server.context_manager.get_stats()
                self.wfile.write(json.dumps(stats, indent=2).encode())
                
            elif parsed_path.path == '/recent':
                # Get only recent entries
                context = self.server.context_manager.get_full_context()
                recent = context.get("recent", [])
                self.wfile.write(json.dumps(recent, indent=2).encode())
                
            elif parsed_path.path == '/summary':
                # Get only summary
                context = self.server.context_manager.get_full_context()
                summary = {
                    "summary": context.get("summary", ""),
                    "age_minutes": context.get("stats", {}).get("summary_age_minutes", 0)
                }
                self.wfile.write(json.dumps(summary, indent=2).encode())
                
            elif parsed_path.path == '/':
                # Root endpoint - show API documentation (no auth required)
                api_info = {
                    "service": "Context Management API",
                    "status": "running",
                    "authentication": {
                        "required": True,
                        "type": "API Key",
                        "header": API_KEY_HEADER,
                        "note": "API key required for all endpoints except this one"
                    },
                    "rate_limit": {
                        "requests": RATE_LIMIT_REQUESTS,
                        "window_seconds": RATE_LIMIT_WINDOW
                    },
                    "endpoints": {
                        "/context": "Get full context (requires auth)",
                        "/context/formatted": "Get formatted context (requires auth)",
                        "/recent": "Get recent entries (requires auth)",
                        "/summary": "Get conversation summary (requires auth)",
                        "/stats": "Get statistics (requires auth)",
                        "/clear": "Clear all context [POST] (requires auth)",
                        "/summarize": "Force summarization [POST] (requires auth)"
                    },
                    "websocket": "ws://localhost:8765"
                }
                self.wfile.write(json.dumps(api_info, indent=2).encode())
                
            else:
                # Unknown endpoint
                self._send_error_response(404, "Not found")
                
        except Exception as e:
            logger.error(f"Error handling GET request: {e}")
            # Don't expose internal error details
            self._send_error_response(500, "Internal server error")
            
    def do_POST(self):
        """Handle POST requests"""
        # Rate limiting
        client_ip = self.client_address[0]
        if not self._check_rate_limit(client_ip):
            self._send_error_response(429, "Rate limit exceeded")
            return
        
        # Authentication required for all POST endpoints
        if not self._check_auth():
            self._send_error_response(401, "Unauthorized")
            return
        
        parsed_path = urlparse(self.path)
        
        # Set CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', self._get_allowed_origin())
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', f'Content-Type, {API_KEY_HEADER}')
        self.end_headers()
        
        try:
            if parsed_path.path == '/clear':
                # Clear context
                self.server.context_manager.clear_all_context()
                self.wfile.write(json.dumps({"success": True}).encode())
                
            elif parsed_path.path == '/summarize':
                # Trigger summarization
                self.server.context_manager.force_summary_creation()
                self.wfile.write(json.dumps({"success": True}).encode())
                
            else:
                # Unknown endpoint
                self._send_error_response(404, "Not found")
                
        except Exception as e:
            logger.error(f"Error handling POST request: {e}")
            # Don't expose internal error details
            self._send_error_response(500, "Internal server error")
            
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        # Rate limiting even for OPTIONS to prevent abuse
        client_ip = self.client_address[0]
        if not self._check_rate_limit(client_ip):
            self._send_error_response(429, "Rate limit exceeded")
            return
        
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', self._get_allowed_origin())
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', f'Content-Type, {API_KEY_HEADER}')
        self.send_header('Access-Control-Max-Age', '3600')  # Cache preflight for 1 hour
        self.end_headers()
        
    def log_message(self, format, *args):
        """Override to use logger instead of print"""
        logger.info(f"{self.address_string()} - {format % args}")


class ContextHTTPServer:
    """HTTP server for context API"""
    
    def __init__(self, context_manager, host: str = "localhost", port: int = 8080):
        """
        Initialize HTTP server
        
        Args:
            context_manager: ContextManager instance
            host: Host to bind to
            port: Port to listen on
        """
        self.context_manager = context_manager
        self.host = host
        self.port = port
        
        self.server = None
        self.server_thread = None
        self.running = False
        
    def start(self):
        """Start the HTTP server in a background thread"""
        if self.running:
            return
            
        self.running = True
        
        # Create server
        self.server = HTTPServer((self.host, self.port), ContextHTTPHandler)
        self.server.context_manager = self.context_manager
        
        # Start server in thread
        def run_server():
            logger.info(f"HTTP server listening on http://{self.host}:{self.port}")
            self.server.serve_forever()
            
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        logger.info("HTTP server thread started")
        
    def stop(self):
        """Stop the HTTP server"""
        self.running = False
        
        if self.server:
            self.server.shutdown()
            logger.info("HTTP server stopped")