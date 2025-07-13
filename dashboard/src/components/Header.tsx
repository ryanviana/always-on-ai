import React from 'react';
import { Mic, Wifi, WifiOff } from 'lucide-react';

interface HeaderProps {
  isConnected: boolean;
}

const Header: React.FC<HeaderProps> = ({ isConnected }) => {
  return (
    <header className="glass border-b border-dark-800">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-primary-500/20 rounded-lg">
              <Mic className="w-6 h-6 text-primary-400" />
            </div>
            <h1 className="text-2xl font-bold text-glow">Voice Assistant Dashboard</h1>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className={`flex items-center space-x-2 px-3 py-1 rounded-full ${
              isConnected ? 'bg-primary-500/20' : 'bg-red-500/20'
            }`}>
              {isConnected ? (
                <>
                  <Wifi className="w-4 h-4 text-primary-400" />
                  <span className="text-sm text-primary-400">Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-4 h-4 text-red-400" />
                  <span className="text-sm text-red-400">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;