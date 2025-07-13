import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Wrench, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { SystemEvent } from '../hooks/useWebSocket';

interface ToolExecutionsProps {
  events: SystemEvent[];
}

interface ToolExecution {
  name: string;
  status: 'running' | 'complete' | 'error';
  startTime: number;
  endTime?: number;
  duration?: number;
  result?: any;
  error?: string;
}

const ToolExecutions: React.FC<ToolExecutionsProps> = ({ events }) => {
  const toolExecutions = useMemo(() => {
    const executions = new Map<string, ToolExecution>();
    
    // Process events in reverse order (oldest first)
    [...events].reverse().forEach(event => {
      if (event.type === 'tool.call_start' && event.data?.tool_name) {
        const key = `${event.data.tool_name}-${event.timestamp}`;
        executions.set(key, {
          name: event.data.tool_name,
          status: 'running',
          startTime: event.timestamp
        });
      } else if (event.type === 'tool.call_complete' && event.data?.tool_name) {
        // Find the most recent running execution for this tool
        const runningExecution = Array.from(executions.entries())
          .reverse()
          .find(([_, exec]) => exec.name === event.data.tool_name && exec.status === 'running');
        
        if (runningExecution) {
          const [key, exec] = runningExecution;
          executions.set(key, {
            ...exec,
            status: 'complete',
            endTime: event.timestamp,
            duration: event.timestamp - exec.startTime,
            result: event.data.result
          });
        }
      } else if (event.type === 'tool.call_error' && event.data?.tool_name) {
        // Find the most recent running execution for this tool
        const runningExecution = Array.from(executions.entries())
          .reverse()
          .find(([_, exec]) => exec.name === event.data.tool_name && exec.status === 'running');
        
        if (runningExecution) {
          const [key, exec] = runningExecution;
          executions.set(key, {
            ...exec,
            status: 'error',
            endTime: event.timestamp,
            duration: event.timestamp - exec.startTime,
            error: event.data.error
          });
        }
      }
    });
    
    // Get recent executions (last 60 seconds)
    const now = Date.now() / 1000;
    return Array.from(executions.values())
      .filter(exec => now - exec.startTime < 60)
      .sort((a, b) => b.startTime - a.startTime)
      .slice(0, 10);
  }, [events]);

  const formatDuration = (duration?: number) => {
    if (!duration) return '...';
    if (duration < 1) return `${Math.round(duration * 1000)}ms`;
    return `${duration.toFixed(1)}s`;
  };

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Wrench className="w-5 h-5 text-primary-400" />
          Tool Executions
        </h2>
      </div>
      
      <div className="space-y-3">
        {toolExecutions.map((execution, index) => (
          <motion.div
            key={`${execution.name}-${execution.startTime}`}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.05 }}
            className={`p-3 rounded-lg border ${
              execution.status === 'running' 
                ? 'border-yellow-500 bg-yellow-500/10' 
                : execution.status === 'complete'
                ? 'border-primary-500 bg-primary-500/10'
                : 'border-red-500 bg-red-500/10'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {execution.status === 'running' ? (
                  <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />
                ) : execution.status === 'complete' ? (
                  <CheckCircle className="w-4 h-4 text-primary-400" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400" />
                )}
                <span className="font-medium">{execution.name}</span>
              </div>
              
              <div className="flex items-center gap-2 text-sm">
                <Clock className="w-3 h-3 text-dark-400" />
                <span className="text-dark-400">
                  {formatDuration(execution.duration)}
                </span>
              </div>
            </div>
            
            {execution.error && (
              <div className="mt-2 text-sm text-red-400">
                Error: {execution.error}
              </div>
            )}
          </motion.div>
        ))}
        
        {toolExecutions.length === 0 && (
          <div className="text-center py-8 text-dark-400">
            <Wrench className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>No recent tool executions</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ToolExecutions;