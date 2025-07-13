import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Zap, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { SystemEvent } from '../hooks/useWebSocket';

interface TriggerPipelineProps {
  events: SystemEvent[];
}

interface TriggerState {
  name: string;
  stage: 'detected' | 'validating' | 'validated' | 'executing' | 'complete' | 'error';
  confidence?: number;
  priority?: number;
  keywords?: string[];
  timestamp: number;
}

const TriggerPipeline: React.FC<TriggerPipelineProps> = ({ events }) => {
  const triggerStates = useMemo(() => {
    const states = new Map<string, TriggerState>();
    
    // Process events in reverse order (oldest first)
    [...events].reverse().forEach(event => {
      const triggerName = event.data?.trigger_name;
      if (!triggerName) return;
      
      switch (event.type) {
        case 'trigger.keyword_match':
          states.set(triggerName, {
            name: triggerName,
            stage: 'detected',
            keywords: event.data.keywords,
            priority: event.data.priority,
            timestamp: event.timestamp
          });
          break;
          
        case 'trigger.validation_start':
          if (states.has(triggerName)) {
            states.get(triggerName)!.stage = 'validating';
          }
          break;
          
        case 'trigger.validation_complete':
          if (states.has(triggerName)) {
            const state = states.get(triggerName)!;
            state.stage = 'validated';
            state.confidence = event.data.confidence;
          }
          break;
          
        case 'trigger.execution_start':
          if (states.has(triggerName)) {
            states.get(triggerName)!.stage = 'executing';
          }
          break;
          
        case 'trigger.execution_complete':
          if (states.has(triggerName)) {
            states.get(triggerName)!.stage = 'complete';
          }
          break;
          
        case 'trigger.execution_error':
          if (states.has(triggerName)) {
            states.get(triggerName)!.stage = 'error';
          }
          break;
      }
    });
    
    // Filter recent triggers (last 30 seconds)
    const now = Date.now() / 1000;
    return Array.from(states.values())
      .filter(state => now - state.timestamp < 30)
      .sort((a, b) => b.timestamp - a.timestamp)
      .slice(0, 5);
  }, [events]);

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Brain className="w-5 h-5 text-primary-400" />
          Trigger Pipeline
        </h2>
        <div className="text-sm text-dark-400">
          Real-time detection & validation
        </div>
      </div>
      
      <div className="space-y-4">
        <AnimatePresence>
          {triggerStates.map((trigger) => (
            <motion.div
              key={`${trigger.name}-${trigger.timestamp}`}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              className="relative"
            >
              <div className="flex items-center space-x-4">
                {/* Stage 1: Keyword Detection */}
                <div className={`flex-1 p-3 rounded-lg border transition-all ${
                  trigger.stage === 'detected' 
                    ? 'border-primary-500 bg-primary-500/10 neon-glow' 
                    : 'border-dark-700 bg-dark-800/50'
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium">{trigger.name}</div>
                      <div className="text-xs text-dark-400">
                        Keywords: {trigger.keywords?.join(', ')}
                      </div>
                    </div>
                    <Zap className={`w-4 h-4 ${
                      trigger.stage === 'detected' ? 'text-primary-400' : 'text-dark-500'
                    }`} />
                  </div>
                </div>
                
                {/* Arrow */}
                <div className="text-dark-600">→</div>
                
                {/* Stage 2: LLM Validation */}
                <div className={`flex-1 p-3 rounded-lg border transition-all ${
                  trigger.stage === 'validating' 
                    ? 'border-blue-500 bg-blue-500/10' 
                    : trigger.stage === 'validated' || trigger.stage === 'executing' || trigger.stage === 'complete'
                    ? 'border-primary-500 bg-primary-500/10'
                    : 'border-dark-700 bg-dark-800/50'
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium">LLM Validation</div>
                      {trigger.confidence !== undefined && (
                        <div className="text-xs text-dark-400">
                          Confidence: {(trigger.confidence * 100).toFixed(0)}%
                        </div>
                      )}
                    </div>
                    {trigger.stage === 'validating' ? (
                      <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
                    ) : trigger.stage === 'validated' || trigger.stage === 'executing' || trigger.stage === 'complete' ? (
                      <CheckCircle className="w-4 h-4 text-primary-400" />
                    ) : (
                      <Brain className="w-4 h-4 text-dark-500" />
                    )}
                  </div>
                </div>
                
                {/* Arrow */}
                <div className="text-dark-600">→</div>
                
                {/* Stage 3: Execution */}
                <div className={`flex-1 p-3 rounded-lg border transition-all ${
                  trigger.stage === 'executing' 
                    ? 'border-yellow-500 bg-yellow-500/10' 
                    : trigger.stage === 'complete'
                    ? 'border-primary-500 bg-primary-500/10'
                    : trigger.stage === 'error'
                    ? 'border-red-500 bg-red-500/10'
                    : 'border-dark-700 bg-dark-800/50'
                }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium">Execution</div>
                      <div className="text-xs text-dark-400">
                        Priority: {trigger.priority || 'N/A'}
                      </div>
                    </div>
                    {trigger.stage === 'executing' ? (
                      <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />
                    ) : trigger.stage === 'complete' ? (
                      <CheckCircle className="w-4 h-4 text-primary-400" />
                    ) : trigger.stage === 'error' ? (
                      <XCircle className="w-4 h-4 text-red-400" />
                    ) : (
                      <Zap className="w-4 h-4 text-dark-500" />
                    )}
                  </div>
                </div>
              </div>
              
              {/* Progress bar */}
              <div className="mt-2 h-1 bg-dark-800 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-primary-500 to-primary-400"
                  initial={{ width: '0%' }}
                  animate={{ 
                    width: 
                      trigger.stage === 'detected' ? '20%' :
                      trigger.stage === 'validating' ? '40%' :
                      trigger.stage === 'validated' ? '60%' :
                      trigger.stage === 'executing' ? '80%' :
                      trigger.stage === 'complete' ? '100%' :
                      trigger.stage === 'error' ? '90%' : '0%'
                  }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        
        {triggerStates.length === 0 && (
          <div className="text-center py-8 text-dark-400">
            <Brain className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>Waiting for triggers...</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TriggerPipeline;