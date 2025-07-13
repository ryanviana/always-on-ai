import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, Zap, Clock, Activity } from 'lucide-react';

interface SystemMetricsProps {
  eventStats: any;
}

const SystemMetrics: React.FC<SystemMetricsProps> = ({ eventStats }) => {
  if (!eventStats) {
    return (
      <div className="glass rounded-xl p-6">
        <div className="text-center py-8 text-dark-400">
          <Activity className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>Loading metrics...</p>
        </div>
      </div>
    );
  }

  // Prepare data for chart
  const chartData = Object.entries(eventStats.event_types || {})
    .map(([type, count]) => ({
      name: type.split('.').pop() || type,
      count: count as number
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  return (
    <div className="glass rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-primary-400" />
          System Metrics
        </h2>
      </div>
      
      {/* Key Metrics */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-dark-800/50 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-400">Total Events</p>
              <p className="text-2xl font-bold text-primary-400">
                {eventStats.total_events || 0}
              </p>
            </div>
            <Activity className="w-8 h-8 text-primary-400/20" />
          </div>
        </div>
        
        <div className="bg-dark-800/50 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-400">Events/Min</p>
              <p className="text-2xl font-bold text-blue-400">
                {eventStats.events_per_minute?.toFixed(1) || '0.0'}
              </p>
            </div>
            <Zap className="w-8 h-8 text-blue-400/20" />
          </div>
        </div>
      </div>
      
      {/* Event Types Chart */}
      <div className="mb-4">
        <h3 className="text-sm font-medium text-dark-300 mb-3">Event Distribution</h3>
        <div style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis 
                dataKey="name" 
                tick={{ fill: '#71717a', fontSize: 12 }}
                angle={-45}
                textAnchor="end"
                height={60}
              />
              <YAxis tick={{ fill: '#71717a', fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#18181b', 
                  border: '1px solid #27272a',
                  borderRadius: '8px'
                }}
              />
              <Bar dataKey="count" fill="#22c55e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      
      {/* Performance Stats */}
      <div className="grid grid-cols-2 gap-4">
        <div className="text-center p-3 bg-dark-800/50 rounded-lg">
          <Clock className="w-5 h-5 mx-auto mb-1 text-yellow-400" />
          <p className="text-xs text-dark-400">Uptime</p>
          <p className="text-sm font-bold">
            {Math.floor((eventStats.uptime_seconds || 0) / 60)}m
          </p>
        </div>
        
        <div className="text-center p-3 bg-dark-800/50 rounded-lg">
          <TrendingUp className="w-5 h-5 mx-auto mb-1 text-primary-400" />
          <p className="text-xs text-dark-400">Peak Rate</p>
          <p className="text-sm font-bold">
            {eventStats.peak_events_per_minute?.toFixed(0) || '0'}/min
          </p>
        </div>
      </div>
    </div>
  );
};

export default SystemMetrics;