import React, { useEffect, useState, useRef } from 'react';
import { SystemEvent } from '../hooks/useWebSocket';

interface VoiceOrbProps {
  events: SystemEvent[];
}

// Session states
enum OrbState {
  IDLE = 'idle',
  SESSION_ACTIVE = 'session_active',
  SESSION_ENDING = 'session_ending'
}

const VoiceOrb: React.FC<VoiceOrbProps> = ({ events }) => {
  // State machine
  const [orbState, setOrbState] = useState<OrbState>(OrbState.IDLE);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  
  // Audio visualization
  const [audioLevel, setAudioLevel] = useState(0);
  const currentLevelRef = useRef(0);
  const targetLevelRef = useRef(0);
  const animationFrameRef = useRef<number>();
  
  // Timers and validation
  const hideTimerRef = useRef<any>();
  const sessionValidationRef = useRef<{ sessionId: string; timestamp: number } | null>(null);
  const processedSessionEndsRef = useRef<Set<string>>(new Set());
  
  // Animation phases
  const pulsePhaseRef = useRef(0);
  const floatPhaseRef = useRef(0);
  
  // Smooth animation loop
  useEffect(() => {
    const animate = () => {
      const now = Date.now() / 1000;
      
      // Update animation phases
      pulsePhaseRef.current = now * 2;
      floatPhaseRef.current = now * 0.5;
      
      // Smooth level transitions
      const diff = targetLevelRef.current - currentLevelRef.current;
      currentLevelRef.current += diff * 0.3;
      
      // Apply breathing animation when idle
      let displayLevel = currentLevelRef.current;
      if (orbState === OrbState.SESSION_ACTIVE && displayLevel < 0.1) {
        // Gentle breathing when no audio
        const breathing = (Math.sin(pulsePhaseRef.current) + 1) * 0.03 + 0.05;
        displayLevel = Math.max(displayLevel, breathing);
      }
      
      // Apply visual effects
      const orb = document.getElementById('voice-orb-main');
      if (orb) {
        const scale = 1 + displayLevel * 0.5;
        const brightness = 1 + displayLevel * 0.4;
        const glow = displayLevel * 120;
        
        orb.style.transform = `scale(${scale}) translateY(${Math.sin(floatPhaseRef.current) * 8}px)`;
        orb.style.filter = `brightness(${brightness})`;
        orb.style.boxShadow = `
          0 0 ${glow}px rgba(59, 130, 246, 0.8),
          0 0 ${glow * 1.5}px rgba(59, 130, 246, 0.5),
          inset 0 0 ${glow * 0.3}px rgba(255, 255, 255, 0.4)
        `;
      }
      
      animationFrameRef.current = requestAnimationFrame(animate);
    };
    
    animate();
    
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [orbState]);
  
  // Process events
  useEffect(() => {
    // Process only recent events to avoid performance issues
    const recentEvents = events.slice(0, 20);
    
    // Debug: Log current state when processing events
    console.log(`[VoiceOrb] 🔍 Processing ${recentEvents.length} events. Current state: orbState=${orbState}, sessionId=${currentSessionId}`);
    
    // Debug: Log all session-related events
    const sessionEvents = recentEvents.filter(e => 
      e.type === 'assistant.session_start' || 
      e.type === 'assistant.session_end' ||
      e.type === 'state.transition'
    );
    if (sessionEvents.length > 0) {
      console.log(`[VoiceOrb] 📋 Session events in batch:`, sessionEvents.map(e => ({
        type: e.type,
        session_id: e.data?.session_id,
        reason: e.data?.reason,
        timestamp: e.timestamp
      })));
    }
    
    for (const event of recentEvents) {
      // Session start - MUST have valid session ID
      if (event.type === 'assistant.session_start' && event.data?.session_id) {
        // Only start if we're idle or if this is a new session
        if (orbState === OrbState.IDLE || event.data.session_id !== currentSessionId) {
          console.log(`[VoiceOrb] ✅ Session started: ${event.data.session_id}`);
          setOrbState(OrbState.SESSION_ACTIVE);
          setCurrentSessionId(event.data.session_id);
          targetLevelRef.current = 0;
          
          // Record session validation info
          sessionValidationRef.current = {
            sessionId: event.data.session_id,
            timestamp: Date.now()
          };
          
          // Clear any pending hide timer and reset processed events
          if (hideTimerRef.current) {
            clearTimeout(hideTimerRef.current);
            hideTimerRef.current = undefined;
          }
          processedSessionEndsRef.current.clear();
        }
      }
      
      // Session end events - log all for debugging
      else if (event.type === 'assistant.session_end') {
        console.log(`[VoiceOrb] 📬 Session end event received: session=${event.data?.session_id}, reason=${event.data?.reason}, current=${currentSessionId}, state=${orbState}`);
        
        // Only process if conditions match
        if (event.data?.session_id === currentSessionId && orbState === OrbState.SESSION_ACTIVE) {
        
        console.log(`[VoiceOrb] 📥 Processing session end event: session=${event.data.session_id}, reason=${event.data?.reason}, current=${currentSessionId}, state=${orbState}`);
        
        // Simple approach: hide the orb when session ends
        console.log(`[VoiceOrb] 🔴 Session ending: ${event.data.session_id} (reason: ${event.data?.reason})`);
        setOrbState(OrbState.SESSION_ENDING);
        
        // Hide after 2 seconds
        console.log(`[VoiceOrb] ⏱️ Setting hide timer for 2 seconds...`);
        if (hideTimerRef.current) {
          clearTimeout(hideTimerRef.current);
        }
        hideTimerRef.current = setTimeout(() => {
          console.log('[VoiceOrb] ⏰ Timer fired! Hiding orb');
          setOrbState(OrbState.IDLE);
          setCurrentSessionId(null);
          targetLevelRef.current = 0;
          sessionValidationRef.current = null;
          processedSessionEndsRef.current.clear();
          console.log('[VoiceOrb] ✅ Hide complete - orb should be gone');
        }, 2000);
        } else {
          console.log(`[VoiceOrb] ⚠️ Session end event doesn't match current session or state`);
        }
      }
      
      // Audio levels - only from realtime assistant, during active session
      else if (event.type === 'audio.output_level' && 
               event.data?.source === 'realtime_assistant' &&
               event.data?.is_playing &&
               orbState === OrbState.SESSION_ACTIVE) {
        const level = event.data.level || 0;
        if (level > 0) {
          targetLevelRef.current = Math.min(1, level * 1.2); // Amplify for visibility
          setAudioLevel(level);
        }
      }
    }
    
    // Decay audio level when no recent updates
    if (orbState === OrbState.SESSION_ACTIVE) {
      targetLevelRef.current *= 0.95;
    }
  }, [events, orbState, currentSessionId]);
  
  // Debug effect to log state changes
  useEffect(() => {
    console.log(`[VoiceOrb] 🔄 State changed: orbState=${orbState}, sessionId=${currentSessionId}, hideTimer=${!!hideTimerRef.current}`);
  }, [orbState, currentSessionId]);
  
  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      console.log('[VoiceOrb] 🧹 Component unmounting - cleaning up timers');
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
      }
      sessionValidationRef.current = null;
      processedSessionEndsRef.current.clear();
    };
  }, []);
  
  // Don't render if idle
  if (orbState === OrbState.IDLE) {
    console.log('[VoiceOrb] 🚫 Not rendering - orbState is IDLE');
    return null;
  }
  
  console.log(`[VoiceOrb] 🎨 Rendering orb - orbState=${orbState}`);
  
  
  return (
    <div className="fixed inset-0 pointer-events-none flex items-center justify-center z-50">
      <div className="relative">
        {/* Outer glow */}
        <div 
          className="absolute -inset-32 rounded-full"
          style={{
            background: 'radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 60%)',
            filter: 'blur(60px)',
            opacity: orbState === OrbState.SESSION_ENDING ? 0.5 : 1,
            transition: 'opacity 1s ease-out'
          }}
        />
        
        {/* Ripples */}
        {orbState === OrbState.SESSION_ACTIVE && audioLevel > 0.2 && (
          <>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-32 h-32 rounded-full border border-blue-400/30 animate-ping" />
            </div>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-32 h-32 rounded-full border border-blue-400/20 animate-ping" 
                   style={{ animationDelay: '0.3s' }} />
            </div>
          </>
        )}
        
        {/* Main orb */}
        <div
          id="voice-orb-main"
          className="relative w-28 h-28 rounded-full"
          style={{
            background: 'radial-gradient(circle at 35% 35%, #93c5fd, #3b82f6, #1d4ed8)',
            transition: 'transform 0.1s ease-out, filter 0.1s ease-out',
            opacity: orbState === OrbState.SESSION_ENDING ? 0.7 : 1,
          }}
        >
          {/* Inner shine */}
          <div className="absolute top-3 left-3 w-12 h-12 rounded-full bg-white/25 blur-md" />
          
          {/* Glass effect */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-transparent via-white/10 to-transparent" />
        </div>
      </div>
    </div>
  );
};

export default VoiceOrb;