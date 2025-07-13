import React, { useEffect, useRef } from 'react';

interface WaveformVisualizerProps {
  isActive: boolean;
  isSpeaking: boolean;
  color: string;
}

const WaveformVisualizer: React.FC<WaveformVisualizerProps> = ({ isActive, isSpeaking, color }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number>();
  const barsRef = useRef<number[]>([]);
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Initialize bars if empty
    if (barsRef.current.length === 0) {
      const barCount = 40;
      barsRef.current = new Array(barCount).fill(0).map(() => 0.1);
    }
    
    const draw = () => {
      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);
      
      const barWidth = width / barsRef.current.length;
      const centerY = height / 2;
      
      // Update bars
      barsRef.current = barsRef.current.map((bar, i) => {
        if (isActive && (isSpeaking || Math.random() > 0.7)) {
          // Active: random movement
          const target = Math.random() * 0.8 + 0.2;
          return bar + (target - bar) * 0.3;
        } else {
          // Inactive: gentle wave
          const time = Date.now() / 1000;
          return 0.1 + Math.sin(time * 2 + i * 0.2) * 0.05;
        }
      });
      
      // Draw bars
      barsRef.current.forEach((barHeight, i) => {
        const x = i * barWidth;
        const height = barHeight * centerY;
        
        // Create gradient
        const gradient = ctx.createLinearGradient(0, centerY - height, 0, centerY + height);
        gradient.addColorStop(0, `${color}40`);
        gradient.addColorStop(0.5, color);
        gradient.addColorStop(1, `${color}40`);
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x, centerY - height, barWidth - 2, height * 2);
      });
      
      animationFrameRef.current = requestAnimationFrame(draw);
    };
    
    // Handle canvas resize
    const resizeCanvas = () => {
      if (!canvas) return;
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width;
        canvas.height = rect.height;
      }
    };
    
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    draw();
    
    return () => {
      window.removeEventListener('resize', resizeCanvas);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isActive, isSpeaking, color]);
  
  return (
    <canvas 
      ref={canvasRef}
      className="w-full h-full"
      style={{ opacity: isActive ? 1 : 0.3 }}
    />
  );
};

export default WaveformVisualizer;