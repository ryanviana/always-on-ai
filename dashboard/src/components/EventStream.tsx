import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Filter } from 'lucide-react';
import { SystemEvent } from '../hooks/useWebSocket';
import { format } from 'date-fns';

interface EventStreamProps {
  events: SystemEvent[];
}

const eventTypeColors: Record<string, string> = {
  'trigger.keyword_match': 'text-primary-400',
  'trigger.validation_start': 'text-blue-400',
  'trigger.validation_complete': 'text-primary-400',
  'trigger.execution_start': 'text-yellow-400',
  'trigger.execution_complete': 'text-primary-400',
  'trigger.execution_error': 'text-red-400',
  'tool.call_start': 'text-purple-400',
  'tool.call_complete': 'text-purple-400',
  'tool.call_error': 'text-red-400',
  'assistant.session_start': 'text-blue-400',
  'assistant.session_end': 'text-blue-400',
  'assistant.speaking_start': 'text-blue-400',
  'assistant.speaking_end': 'text-blue-400',
  'audio.microphone_pause': 'text-yellow-400',
  'audio.microphone_resume': 'text-primary-400',
};

const eventTypeIcons: Record<string, string> = {
  'trigger': '🎯',
  'tool': '🔧',
  'assistant': '🤖',
  'audio': '🎙️',
  'context': '📝',
  'transcription': '💬',
  'tts': '🔊',
  'system': '⚙️',
  'websocket': '🌐',
  'performance': '📊',
};

const EventStream: React.FC<EventStreamProps> = ({ events }) => {
  const [filter, setFilter] = useState<string>('all');
  
  const filteredEvents = events.filter(event => {
    // Filter out audio.output_level events as they're too noisy
    if (event.type === 'audio.output_level') return false;
    
    if (filter === 'all') return true;
    return event.type.startsWith(filter);
  });
  
  const getEventIcon = (type: string) => {
    const category = type.split('.')[0];
    return eventTypeIcons[category] || '📌';
  };
  
  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5 text-primary-400" />
          Event Stream
        </h2>
        
        {/* Filter Dropdown */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-dark-400" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-dark-800 border border-dark-700 rounded px-2 py-1 text-sm"
          >
            <option value="all">All Events</option>
            <option value="trigger">Triggers</option>
            <option value="tool">Tools</option>
            <option value="assistant">Assistant</option>
            <option value="audio">Audio</option>
            <option value="context">Context</option>
          </select>
        </div>
      </div>
      
      <div className="space-y-2 max-h-96 overflow-y-auto">
        <AnimatePresence mode="popLayout">
          {filteredEvents.slice(0, 50).map((event, index) => (
            <motion.div
              key={event.id || `${event.type}-${event.timestamp}-${index}`}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="flex items-start gap-3 p-3 bg-dark-800/50 rounded-lg hover:bg-dark-800 transition-colors"
            >
              <div className="text-xl">{getEventIcon(event.type)}</div>
              
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className={`font-medium ${eventTypeColors[event.type] || 'text-gray-400'}`}>
                    {event.type}
                  </span>
                  <span className="text-xs text-dark-400">
                    {format(new Date(event.timestamp * 1000), 'HH:mm:ss.SSS')}
                  </span>
                </div>
                
                {/* Event Data Preview */}
                {event.data && (
                  <div className="mt-1 text-sm text-dark-300">
                    {event.data.trigger_name && (
                      <span className="mr-2">Trigger: {event.data.trigger_name}</span>
                    )}
                    {event.data.tool_name && (
                      <span className="mr-2">Tool: {event.data.tool_name}</span>
                    )}
                    {event.data.confidence !== undefined && (
                      <span className="mr-2">Confidence: {(event.data.confidence * 100).toFixed(0)}%</span>
                    )}
                    {event.data.error && (
                      <span className="text-red-400">Error: {event.data.error}</span>
                    )}
                  </div>
                )}
              </div>
              
              <div className="text-xs text-dark-500">
                {event.source}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        
        {filteredEvents.length === 0 && (
          <div className="text-center py-8 text-dark-400">
            <Activity className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>No events to display</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default EventStream;