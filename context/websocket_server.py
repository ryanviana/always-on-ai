"""
WebSocket server for context access
"""

import asyncio
import websockets
import json
import threading
import sys
import os
from typing import Set, Optional
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from events import event_bus, EventTypes, SystemEvent

logger = logging.getLogger(__name__)


class ContextWebSocketServer:
    def __init__(self, context_manager, port=8765):
        self.context_manager = context_manager
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.clients_lock = threading.Lock()  # Thread safety for client set
        self.server = None
        self.loop = None
        self.thread = None
        
        # Subscribe to all events
        event_bus.on_all(self._handle_system_event)
        
    async def handle_client(self, websocket, path=None):
        """Handle a WebSocket client connection"""
        # Register client with thread safety
        with self.clients_lock:
            self.clients.add(websocket)
            client_count = len(self.clients)
        logger.info(f"Client connected: {websocket.remote_address} (Total: {client_count})")
        
        try:
            # Send initial context
            context = self.context_manager.get_full_context()
            await websocket.send(json.dumps({
                "type": "initial_context",
                "data": context
            }))
            
            # Trigger immediate microphone state broadcast for new connections
            # Use event bus to request current state
            from events import event_bus, EventTypes
            event_bus.emit(EventTypes.REQUEST_MICROPHONE_STATE, {
                "source": "websocket_connection"
            }, source="WebSocketServer")
            
            # Handle messages from client
            async for message in websocket:
                try:
                    data = json.loads(message)
                    command = data.get("command")
                    
                    if command == "get_context":
                        context = self.context_manager.get_full_context()
                        await websocket.send(json.dumps({
                            "type": "context_response",
                            "data": context
                        }))
                    elif command == "get_stats":
                        stats = self.context_manager.get_stats()
                        await websocket.send(json.dumps({
                            "type": "stats_response",
                            "data": stats
                        }))
                    elif command == "get_events":
                        # Get recent events
                        count = data.get("count", 50)
                        event_type = data.get("event_type")
                        events = event_bus.get_recent_events(count, event_type)
                        await websocket.send(json.dumps({
                            "type": "events_response",
                            "data": events
                        }))
                    elif command == "get_event_stats":
                        # Get event statistics
                        stats = event_bus.get_stats()
                        await websocket.send(json.dumps({
                            "type": "event_stats_response",
                            "data": stats
                        }))
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from client: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            # Unregister client with thread safety
            with self.clients_lock:
                self.clients.discard(websocket)
                client_count = len(self.clients)
            logger.info(f"Client disconnected (Total: {client_count})")
            
    async def broadcast_update(self):
        """Broadcast context update to all clients"""
        # Get a snapshot of clients with thread safety
        with self.clients_lock:
            if not self.clients:
                return
            clients_snapshot = list(self.clients)
            
        context = self.context_manager.get_full_context()
        message = json.dumps({
            "type": "context_update",
            "data": context
        })
        
        # Send to all clients
        disconnected = []
        for client in clients_snapshot:
            try:
                await client.send(message)
            except (websockets.ConnectionClosed, websockets.InvalidState, OSError) as e:
                disconnected.append(client)
                
        # Remove disconnected clients with thread safety
        if disconnected:
            with self.clients_lock:
                for client in disconnected:
                    self.clients.discard(client)
            
    async def start_server(self):
        """Start the WebSocket server"""
        logger.info(f"Starting WebSocket server on port {self.port}")
        
        # Start server - websockets.serve expects handler(websocket, path) or handler(websocket)
        async with websockets.serve(self.handle_client, "localhost", self.port) as server:
            logger.info(f"WebSocket server running on ws://localhost:{self.port}")
            
            # Keep running
            await asyncio.Future()
            
    def run_in_thread(self):
        """Run the server in a separate thread"""
        self.loop = None
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.start_server())
        except Exception as e:
            logger.error(f"WebSocket server error: {e}")
        finally:
            # Always close the loop to prevent resource leaks
            if self.loop and not self.loop.is_closed():
                self.loop.close()
                self.loop = None
            
    def start(self):
        """Start the WebSocket server in a background thread"""
        if self.thread and self.thread.is_alive():
            return
            
        self.thread = threading.Thread(target=self.run_in_thread, daemon=True)
        self.thread.start()
        logger.info("WebSocket server thread started")
        
    def stop(self):
        """Stop the WebSocket server"""
        logger.info("Stopping WebSocket server...")
        
        # Stop the event loop gracefully
        if self.loop and self.loop.is_running():
            # Schedule loop shutdown in the event loop thread
            future = asyncio.run_coroutine_threadsafe(
                self._shutdown_server(), self.loop
            )
            try:
                future.result(timeout=3.0)
            except Exception as e:
                logger.error(f"Error during server shutdown: {e}")
                # Force stop the loop if graceful shutdown fails
                self.loop.call_soon_threadsafe(self.loop.stop)
        
        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            if self.thread.is_alive():
                logger.warning("WebSocket server thread did not stop gracefully")
        
        logger.info("WebSocket server stopped")
    
    async def _shutdown_server(self):
        """Gracefully shutdown the WebSocket server"""
        # Close all client connections with thread safety
        clients_to_close = []
        with self.clients_lock:
            if self.clients:
                logger.info(f"Closing {len(self.clients)} client connections")
                clients_to_close = list(self.clients)
                self.clients.clear()  # Clear all clients at once
        
        # Close connections outside the lock to avoid blocking
        for client in clients_to_close:
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing client connection: {e}")
        
        # Stop the event loop
        self.loop.stop()
    
    def trigger_broadcast(self):
        """Trigger a broadcast from outside the async loop"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_update(), self.loop)
    
    def _handle_system_event(self, event: SystemEvent):
        """Handle system events and broadcast to clients"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._broadcast_event(event), 
                self.loop
            )
    
    async def _broadcast_event(self, event: SystemEvent):
        """Broadcast event to all connected clients"""
        # Get a snapshot of clients with thread safety
        with self.clients_lock:
            if not self.clients:
                return
            clients_snapshot = list(self.clients)
            
        # Convert event to dict for JSON serialization
        message = json.dumps({
            "type": "system_event",
            "event": event.to_dict()
        })
        
        # Send to all clients
        disconnected = []
        for client in clients_snapshot:
            try:
                await client.send(message)
            except (websockets.ConnectionClosed, websockets.InvalidState, OSError):
                disconnected.append(client)
                
        # Remove disconnected clients with thread safety
        if disconnected:
            with self.clients_lock:
                for client in disconnected:
                    self.clients.discard(client)