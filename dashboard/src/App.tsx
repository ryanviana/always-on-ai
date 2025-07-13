import React from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import Header from './components/Header';
import TriggerPipeline from './components/TriggerPipeline';
import EventStream from './components/EventStream';
import AudioVisualizer from './components/AudioVisualizer';
import ContextViewer from './components/ContextViewer';
import SystemMetrics from './components/SystemMetrics';
import ToolExecutions from './components/ToolExecutions';

function App() {
  const { isConnected, context, events, eventStats } = useWebSocket('ws://localhost:8765');

  return (
    <div className="min-h-screen bg-dark-950">
      <Header isConnected={isConnected} />
      
      <main className="container mx-auto px-4 py-6 space-y-6">
        {/* Top Row - Key Visualizations */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TriggerPipeline events={events} />
          <AudioVisualizer events={events} />
        </div>
        
        {/* Middle Row - Activity Streams */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <EventStream events={events} />
          </div>
          <div>
            <ToolExecutions events={events} />
          </div>
        </div>
        
        {/* Bottom Row - Context and Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ContextViewer context={context} />
          <SystemMetrics eventStats={eventStats} />
        </div>
      </main>
    </div>
  );
}

export default App;