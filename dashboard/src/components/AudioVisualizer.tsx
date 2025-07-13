import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Mic, MicOff, Volume2, VolumeX } from 'lucide-react';
import { SystemEvent } from '../hooks/useWebSocket';
import VoiceOrb from './VoiceOrb';
import WaveformVisualizer from './WaveformVisualizer';

interface AudioVisualizerProps {
  events: SystemEvent[];
}

const AudioVisualizer: React.FC<AudioVisualizerProps> = ({ events }) => {
  const audioState = useMemo(() => {
    const recentEvents = events.slice(0, 50);
    
    // Sort events by timestamp (newest first, but process in reverse for correct state)
    const sortedEvents = [...recentEvents].sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    
    // Start with unknown states and derive from events
    let microphoneActive: boolean | null = null;
    let assistantSpeaking = false;
    let sessionActive = false;
    let foundSessionState = false;
    
    // Process events from oldest to newest to build correct state
    for (let i = sortedEvents.length - 1; i >= 0; i--) {
      const event = sortedEvents[i];
      
      // Track microphone state - remove restrictive conditions
      if (event.type === 'audio.microphone_pause') {
        microphoneActive = false;
        console.log(`[AudioVisualizer] 🔇 Microphone paused at ${new Date(event.timestamp || 0).toLocaleTimeString()}`);
      } else if (event.type === 'audio.microphone_resume') {
        microphoneActive = true;
        console.log(`[AudioVisualizer] 🎤 Microphone resumed at ${new Date(event.timestamp || 0).toLocaleTimeString()}`);
      } else if (event.type === 'audio.microphone_state') {
        // Direct state broadcast from backend - use this as authoritative source
        microphoneActive = !event.data?.is_paused;
        console.log(`[AudioVisualizer] 📡 State sync: microphone ${microphoneActive ? 'active' : 'paused'} (${event.data?.consumers_count} consumers)`);
      }
      
      // Track assistant speaking state
      if (event.type === 'assistant.speaking_start') {
        assistantSpeaking = true;
      } else if (event.type === 'assistant.speaking_end') {
        assistantSpeaking = false;
      }
      
      // Track session state - only process the most recent session event
      if (!foundSessionState) {
        if (event.type === 'assistant.session_start' && event.data?.session_id) {
          sessionActive = true;
          foundSessionState = true;
        } else if (event.type === 'assistant.session_end') {
          sessionActive = false;
          foundSessionState = true;
        } else if (event.type === 'state.transition') {
          // Backup: track state transitions
          if (event.data?.to_state === 'assistant_active') {
            sessionActive = true;
            foundSessionState = true;
          } else if (event.data?.from_state === 'assistant_active' && event.data?.to_state === 'listening') {
            sessionActive = false;
            foundSessionState = true;
          }
        }
      }
    }
    
    // Default to active if no microphone events found (assume system starts listening)
    if (microphoneActive === null) {
      microphoneActive = true;
      console.log('[AudioVisualizer] 🎤 No microphone events found, defaulting to active');
    }
    
    const state = { microphoneActive, assistantSpeaking, sessionActive };
    console.log(`[AudioVisualizer] Current state:`, state);
    
    return state;
  }, [events]);
  
  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Volume2 className="w-5 h-5 text-primary-400" />
          Audio Activity
        </h2>
        <div className="flex items-center gap-4">
          {/* Microphone Status */}
          <motion.div
            animate={{ 
              scale: audioState.microphoneActive ? [1, 1.1, 1] : 1,
              opacity: audioState.microphoneActive ? 1 : 0.5
            }}
            transition={{ 
              scale: { repeat: Infinity, duration: 2 },
              opacity: { duration: 0.3 }
            }}
            className={`flex items-center gap-2 px-3 py-1 rounded-full ${
              audioState.microphoneActive 
                ? 'bg-primary-500/20' 
                : 'bg-dark-700'
            }`}
          >
            {audioState.microphoneActive ? (
              <>
                <Mic className="w-4 h-4 text-primary-400" />
                <span className="text-sm text-primary-400">Active</span>
              </>
            ) : (
              <>
                <MicOff className="w-4 h-4 text-dark-400" />
                <span className="text-sm text-dark-400">Paused</span>
              </>
            )}
          </motion.div>
          
          {/* Assistant Status */}
          {audioState.sessionActive && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className={`flex items-center gap-2 px-3 py-1 rounded-full ${
                audioState.assistantSpeaking 
                  ? 'bg-blue-500/20' 
                  : 'bg-dark-700'
              }`}
            >
              <div className={`w-2 h-2 rounded-full ${
                audioState.assistantSpeaking 
                  ? 'bg-blue-400 animate-pulse' 
                  : 'bg-dark-500'
              }`} />
              <span className={`text-sm ${
                audioState.assistantSpeaking 
                  ? 'text-blue-400' 
                  : 'text-dark-400'
              }`}>
                Assistant
              </span>
            </motion.div>
          )}
        </div>
      </div>
      
      {/* Visualization Area */}
      <div className="relative bg-dark-900/50 rounded-lg overflow-hidden" style={{ height: audioState.sessionActive ? '20rem' : '8rem' }}>
        {audioState.sessionActive ? (
          // Show Voice Orb in assistant mode
          <VoiceOrb events={events} />
        ) : (
          // Show Waveform in normal mode
          <WaveformVisualizer 
            isActive={audioState.microphoneActive}
            isSpeaking={false}
            color="#22c55e"
          />
        )}
        
        {/* Echo Prevention Indicator */}
        {!audioState.microphoneActive && audioState.assistantSpeaking && (
          <div className="absolute top-4 right-4 flex items-center gap-2 bg-dark-900/80 px-3 py-2 rounded-lg">
            <VolumeX className="w-4 h-4 text-yellow-400" />
            <p className="text-sm text-yellow-400">Echo Prevention Active</p>
          </div>
        )}
      </div>
      
      {/* Audio Stats */}
      <div className="grid grid-cols-3 gap-4 mt-4">
        <div className="text-center">
          <div className="text-2xl font-bold text-primary-400">
            {audioState.microphoneActive ? 'ON' : 'OFF'}
          </div>
          <div className="text-xs text-dark-400">Microphone</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-blue-400">
            {audioState.sessionActive ? 'ACTIVE' : 'IDLE'}
          </div>
          <div className="text-xs text-dark-400">Assistant</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-yellow-400">
            {!audioState.microphoneActive && audioState.assistantSpeaking ? 'ON' : 'OFF'}
          </div>
          <div className="text-xs text-dark-400">Echo Guard</div>
        </div>
      </div>
    </div>
  );
};

export default AudioVisualizer;