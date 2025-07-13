# Voice Assistant Dashboard

An ultra-impressive real-time dashboard for monitoring your Portuguese voice assistant system. Built with React, TypeScript, and modern visualization libraries.

## Features

- **Real-time Trigger Pipeline Visualization**: See triggers flow through detection, validation, and execution stages
- **Live Audio Waveform**: Monitor microphone activity and echo prevention in real-time
- **Event Stream**: Track all system events with filtering and categorization
- **Tool Execution Monitor**: Visualize tool calls with execution times and results
- **Conversation Context**: View current conversation with summarization
- **System Metrics**: Performance charts and statistics

## Setup

1. Install dependencies:
```bash
cd dashboard
npm install
```

2. Make sure the voice assistant is running with WebSocket server enabled on port 8765

3. Start the dashboard:
```bash
npm run dev
```

4. Open your browser to http://localhost:3000

## Architecture

The dashboard connects to the voice assistant's WebSocket server to receive real-time events. It uses:

- **React 18** with TypeScript for the UI
- **Framer Motion** for smooth animations
- **Recharts** for data visualization
- **Tailwind CSS** for styling with custom glassmorphism effects
- **WebSocket** for real-time event streaming

## Visual Features

- Glassmorphism design with dark theme
- Neon glow effects for active states
- Smooth animations and transitions
- Real-time waveform visualization
- Animated trigger pipeline flow
- Color-coded event types
- Performance metric charts

## Development

The dashboard automatically reconnects if the WebSocket connection is lost. All components are fully typed with TypeScript for better development experience.