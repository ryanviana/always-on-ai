#!/usr/bin/env python3
"""
Monitor script to detect infinite loops in assistant mode
"""

import subprocess
import time
import re
from collections import defaultdict

def monitor_logs():
    """Monitor logs for infinite loop patterns"""
    print("=== Assistant Mode Monitor ===")
    print("Watching for infinite loop patterns...")
    print("Press Ctrl+C to stop\n")
    
    # Track function calls
    function_calls = defaultdict(list)
    last_function_time = defaultdict(float)
    
    # Patterns to watch
    patterns = {
        'function_call': re.compile(r'\[FUNCTION_CALL\] Executing function from response\.done: (\w+)'),
        'tool_error': re.compile(r'Tool call ID .* not found in conversation'),
        'response_created': re.compile(r'\[RESPONSE\] Response created: (\w+)'),
        'infinite_pattern': re.compile(r'call_\w+')
    }
    
    # Start log monitoring
    try:
        with subprocess.Popen(['tail', '-f', 'logs/voice_assistant.log'], 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE,
                            universal_newlines=True) as proc:
            
            for line in proc.stdout:
                line = line.strip()
                
                # Check for function calls
                match = patterns['function_call'].search(line)
                if match:
                    func_name = match.group(1)
                    current_time = time.time()
                    
                    # Check if same function called multiple times quickly
                    if func_name in last_function_time:
                        time_diff = current_time - last_function_time[func_name]
                        if time_diff < 2.0:  # Less than 2 seconds
                            function_calls[func_name].append(current_time)
                            
                            # Alert if more than 3 calls in 10 seconds
                            recent_calls = [t for t in function_calls[func_name] 
                                          if current_time - t < 10.0]
                            if len(recent_calls) > 3:
                                print(f"⚠️  WARNING: Potential infinite loop detected!")
                                print(f"   Function '{func_name}' called {len(recent_calls)} times in 10 seconds")
                                print(f"   Consider stopping the assistant (Ctrl+C)")
                    
                    last_function_time[func_name] = current_time
                    print(f"📞 Function call: {func_name}")
                
                # Check for tool errors
                if patterns['tool_error'].search(line):
                    print(f"❌ Tool error detected: {line}")
                
                # Check for rapid response creation
                if patterns['response_created'].search(line):
                    print(f"📝 Response created")
                    
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        
        # Summary
        print("\n=== Summary ===")
        for func_name, calls in function_calls.items():
            if calls:
                print(f"{func_name}: {len(calls)} rapid calls detected")

if __name__ == "__main__":
    monitor_logs()