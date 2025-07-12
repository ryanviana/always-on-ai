"""
Context access servers integration
Provides WebSocket and HTTP access to the context manager
"""

from .websocket_server import ContextWebSocketServer
from .rest_api import ContextHTTPServer
import threading
import time
import logging

logger = logging.getLogger(__name__)


class ContextAccessManager:
    """Manages context access servers (WebSocket and HTTP)"""
    
    def __init__(self, context_manager):
        """
        Initialize context access manager
        
        Args:
            context_manager: ContextManager instance
        """
        self.context_manager = context_manager
        
        # Initialize servers
        self.websocket_server = None
        self.http_server = None
        
        # Configuration
        self.websocket_enabled = True
        self.http_enabled = True
        self.websocket_port = 8765
        self.http_port = 8080
        
    def start(self):
        """Start all enabled access servers"""
        try:
            # Start WebSocket server
            if self.websocket_enabled:
                self.websocket_server = ContextWebSocketServer(
                    self.context_manager,
                    port=self.websocket_port
                )
                self.websocket_server.start()
                
                # Hook into context manager for real-time updates
                original_add = self.context_manager.add_transcription
                def hooked_add(text, timestamp=None, speaker="user"):
                    result = original_add(text, timestamp, speaker)
                    # Trigger broadcast
                    if self.websocket_server:
                        self.websocket_server.trigger_broadcast()
                    return result
                self.context_manager.add_transcription = hooked_add
                
                logger.info(f"✅ WebSocket server started on ws://localhost:{self.websocket_port}")
                print(f"🌐 WebSocket context server: ws://localhost:{self.websocket_port}")
                
            # Start HTTP server
            if self.http_enabled:
                self.http_server = ContextHTTPServer(
                    self.context_manager,
                    port=self.http_port
                )
                self.http_server.start()
                logger.info(f"✅ HTTP server started on http://localhost:{self.http_port}")
                print(f"🌐 HTTP context API: http://localhost:{self.http_port}")
                
            # Print web interface URL
            print(f"🖥️  Web interface: Open web_interface.html in your browser")
            print(f"   Or run: python -m http.server 8000 in the project directory")
            print(f"   Then visit: http://localhost:8000/web_interface.html")
            
        except Exception as e:
            logger.error(f"Error starting context access servers: {e}")
            print(f"❌ Failed to start context access servers: {e}")
            
    def stop(self):
        """Stop all access servers"""
        try:
            if self.websocket_server:
                self.websocket_server.stop()
                logger.info("WebSocket server stopped")
                
            if self.http_server:
                self.http_server.stop()
                logger.info("HTTP server stopped")
                
        except Exception as e:
            logger.error(f"Error stopping context access servers: {e}")


def setup_context_access(context_manager):
    """
    Quick setup function to enable context access
    
    Args:
        context_manager: ContextManager instance
        
    Returns:
        ContextAccessManager instance
    """
    access_manager = ContextAccessManager(context_manager)
    access_manager.start()
    return access_manager