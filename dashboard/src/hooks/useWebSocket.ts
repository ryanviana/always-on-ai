import { useEffect, useRef, useState, useCallback } from 'react';

export interface SystemEvent {
  id: string;
  type: string;
  data: any;
  source: string;
  timestamp: number;
  datetime: string;
}

export interface ContextData {
  summary: string;
  recent: Array<{
    text: string;
    timestamp: number;
    speaker: string;
  }>;
  stats: {
    total_entries: number;
    recent_count: number;
    summarizations: number;
    summary_age_minutes: number;
  };
}

interface WebSocketMessage {
  type: string;
  data?: any;
  event?: SystemEvent;
}

export const useWebSocket = (url: string) => {
  const ws = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [context, setContext] = useState<ContextData | null>(null);
  const [events, setEvents] = useState<SystemEvent[]>([]);
  const [eventStats, setEventStats] = useState<any>(null);
  const reconnectTimeout = useRef<any>();

  const connect = useCallback(() => {
    try {
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        
        // Request initial data
        if (ws.current?.readyState === WebSocket.OPEN) {
          ws.current.send(JSON.stringify({ command: 'get_context' }));
          ws.current.send(JSON.stringify({ command: 'get_events', count: 100 }));
          ws.current.send(JSON.stringify({ command: 'get_event_stats' }));
        }
      };

      ws.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          
          switch (message.type) {
            case 'initial_context':
            case 'context_update':
            case 'context_response':
              setContext(message.data);
              break;
              
            case 'system_event':
              if (message.event) {
                setEvents(prev => {
                  // Check if event already exists to prevent duplicates
                  const exists = prev.some(e => e.id === message.event!.id);
                  if (exists) {
                    return prev;
                  }
                  // Add new event and maintain max size
                  return [message.event!, ...prev].slice(0, 500);
                });
              }
              break;
              
            case 'events_response':
              // When receiving bulk events, merge with existing to avoid duplicates
              setEvents(prev => {
                const newEvents = message.data || [];
                const existingIds = new Set(prev.map(e => e.id));
                
                // Filter out any duplicates from new events
                const uniqueNewEvents = newEvents.filter((e: any) => !existingIds.has(e.id));
                
                // Combine and sort by timestamp (newest first)
                const combined = [...uniqueNewEvents, ...prev]
                  .sort((a, b) => b.timestamp - a.timestamp)
                  .slice(0, 500);
                
                return combined;
              });
              break;
              
            case 'event_stats_response':
              setEventStats(message.data);
              break;
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.current.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        
        // Reconnect after 3 seconds
        reconnectTimeout.current = setTimeout(() => {
          connect();
        }, 3000);
      };
    } catch (error) {
      console.error('Error connecting WebSocket:', error);
    }
  }, [url]);

  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }
    
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const sendCommand = useCallback((command: string, data?: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ command, ...data }));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  // Periodic stats update
  useEffect(() => {
    const interval = setInterval(() => {
      sendCommand('get_event_stats');
    }, 5000);
    
    return () => clearInterval(interval);
  }, [sendCommand]);

  return {
    isConnected,
    context,
    events,
    eventStats,
    sendCommand
  };
};