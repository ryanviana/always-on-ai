import React from 'react';
import { FileText, Clock, Hash } from 'lucide-react';
import { ContextData } from '../hooks/useWebSocket';
import { format } from 'date-fns';

interface ContextViewerProps {
  context: ContextData | null;
}

const ContextViewer: React.FC<ContextViewerProps> = ({ context }) => {
  if (!context) {
    return (
      <div className="glass rounded-xl p-6">
        <div className="text-center py-8 text-dark-400">
          <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>No context available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary-400" />
          Conversation Context
        </h2>
        <div className="flex items-center gap-4 text-sm text-dark-400">
          <div className="flex items-center gap-1">
            <Hash className="w-3 h-3" />
            <span>{context.stats.total_entries} entries</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            <span>{Math.round(context.stats.summary_age_minutes)}m ago</span>
          </div>
        </div>
      </div>
      
      {/* Summary */}
      <div className="mb-6">
        <h3 className="text-sm font-medium text-dark-300 mb-2">Summary</h3>
        <div className="bg-dark-800/50 rounded-lg p-4">
          <p className="text-sm whitespace-pre-wrap">{context.summary || 'No summary available'}</p>
        </div>
      </div>
      
      {/* Recent Conversation */}
      <div>
        <h3 className="text-sm font-medium text-dark-300 mb-2">Recent Conversation</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {context.recent.map((entry, index) => (
            <div
              key={`${entry.timestamp}-${index}`}
              className={`p-3 rounded-lg ${
                entry.speaker === 'assistant' 
                  ? 'bg-blue-500/10 border border-blue-500/20' 
                  : 'bg-dark-800/50 border border-dark-700'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${
                  entry.speaker === 'assistant' ? 'text-blue-400' : 'text-primary-400'
                }`}>
                  {entry.speaker}
                </span>
                <span className="text-xs text-dark-400">
                  {format(new Date(entry.timestamp * 1000), 'HH:mm:ss')}
                </span>
              </div>
              <p className="text-sm">{entry.text}</p>
            </div>
          ))}
        </div>
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-dark-700">
        <div className="text-center">
          <div className="text-lg font-bold text-primary-400">
            {context.stats.recent_count}
          </div>
          <div className="text-xs text-dark-400">Recent</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-primary-400">
            {context.stats.summarizations}
          </div>
          <div className="text-xs text-dark-400">Summaries</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold text-primary-400">
            {context.stats.total_entries}
          </div>
          <div className="text-xs text-dark-400">Total</div>
        </div>
      </div>
    </div>
  );
};

export default ContextViewer;