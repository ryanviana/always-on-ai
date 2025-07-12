"""
HTTP server for REST API access to context
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ContextHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for context API"""
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        
        # Enable CORS
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
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
                # Root endpoint - show API documentation
                api_info = {
                    "service": "Context Management API",
                    "status": "running",
                    "endpoints": {
                        "/context": "Get full context",
                        "/context/formatted": "Get formatted context",
                        "/recent": "Get recent entries",
                        "/summary": "Get conversation summary",
                        "/stats": "Get statistics"
                    },
                    "websocket": "ws://localhost:8765"
                }
                self.wfile.write(json.dumps(api_info, indent=2).encode())
                
            else:
                # Unknown endpoint
                self.send_response(404)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not found"}).encode())
                
        except Exception as e:
            logger.error(f"Error handling GET request: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            
    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        
        # Enable CORS
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
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
                self.send_response(404)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not found"}).encode())
                
        except Exception as e:
            logger.error(f"Error handling POST request: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
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