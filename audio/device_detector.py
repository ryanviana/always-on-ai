"""
Audio device detector for speaker/headphone detection and feedback prevention
"""

import pyaudio
import re
from typing import Optional, Dict, Any, List
from enum import Enum


class DeviceType(Enum):
    """Audio device types for feedback prevention"""
    SPEAKERS = "speakers"
    HEADPHONES = "headphones"
    UNKNOWN = "unknown"


class AudioDeviceDetector:
    """Detects audio device types to enable intelligent feedback prevention"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize audio device detector
        
        Args:
            config: Configuration dictionary with device detection settings
        """
        self.config = config or {}
        self.audio = pyaudio.PyAudio()
        
        # Device name patterns for classification
        self.headphone_patterns = self.config.get("headphone_patterns", [
            r"headphone", r"airpods", r"beats", r"bose", r"sony", r"audio-technica",
            r"sennheiser", r"jabra", r"plantronics", r"skull", r"jbl", r"marshall",
            r"earbuds", r"earphones", r"in-ear", r"on-ear", r"over-ear", r"bluetooth",
            r"wireless", r"wh-", r"wf-", r"momentum", r"hd ", r"dt ", r"mdm", r"qc",
            r"quietcomfort", r"noise.?cancel", r"anc"
        ])
        
        self.speaker_patterns = self.config.get("speaker_patterns", [
            r"speaker", r"monitor", r"studio", r"desktop", r"built.?in", r"internal",
            r"system", r"default", r"macbook", r"imac", r"soundbar", r"subwoofer",
            r"satellite", r"bookshelf", r"tower", r"amplifier", r"receiver", r"stereo"
        ])
        
        # Manual override from config
        self.manual_override = self.config.get("manual_override")
        
        # Cache for device info
        self._device_cache = {}
        self._current_output_device = None
        self._current_device_type = None
        
    def get_available_devices(self) -> List[Dict[str, Any]]:
        """Get list of all available audio devices"""
        devices = []
        
        try:
            device_count = self.audio.get_device_count()
            
            for i in range(device_count):
                try:
                    info = self.audio.get_device_info_by_index(i)
                    devices.append({
                        "index": i,
                        "name": info.get("name", "Unknown"),
                        "max_input_channels": info.get("maxInputChannels", 0),
                        "max_output_channels": info.get("maxOutputChannels", 0),
                        "default_sample_rate": info.get("defaultSampleRate", 0),
                        "host_api": info.get("hostApi", 0),
                        "device_type": self._classify_device(info.get("name", ""))
                    })
                except Exception as e:
                    # Skip devices that can't be queried
                    continue
                    
        except Exception as e:
            print(f"Error getting audio devices: {e}")
            
        return devices
    
    def get_current_output_device(self) -> Optional[Dict[str, Any]]:
        """Get information about the current output device"""
        try:
            # Try to get the default output device
            default_info = self.audio.get_default_output_device_info()
            
            device_info = {
                "index": default_info.get("index", -1),
                "name": default_info.get("name", "Unknown"),
                "max_output_channels": default_info.get("maxOutputChannels", 0),
                "default_sample_rate": default_info.get("defaultSampleRate", 0),
                "device_type": self._classify_device(default_info.get("name", ""))
            }
            
            self._current_output_device = device_info
            return device_info
            
        except Exception as e:
            print(f"Error getting current output device: {e}")
            return None
    
    def get_current_device_type(self) -> DeviceType:
        """Get the type of the current output device"""
        
        # Check for manual override first
        if self.manual_override:
            if self.manual_override.lower() == "speakers":
                return DeviceType.SPEAKERS
            elif self.manual_override.lower() == "headphones":
                return DeviceType.HEADPHONES
        
        # Get current device info
        current_device = self.get_current_output_device()
        if not current_device:
            return DeviceType.UNKNOWN
            
        device_type = current_device.get("device_type", DeviceType.UNKNOWN)
        self._current_device_type = device_type
        return device_type
    
    def _classify_device(self, device_name: str) -> DeviceType:
        """Classify device type based on name patterns"""
        if not device_name:
            return DeviceType.UNKNOWN
            
        device_name_lower = device_name.lower()
        
        # Check headphone patterns first (more specific)
        for pattern in self.headphone_patterns:
            if re.search(pattern, device_name_lower):
                return DeviceType.HEADPHONES
        
        # Check speaker patterns
        for pattern in self.speaker_patterns:
            if re.search(pattern, device_name_lower):
                return DeviceType.SPEAKERS
                
        return DeviceType.UNKNOWN
    
    def is_feedback_prevention_needed(self) -> bool:
        """
        Determine if aggressive feedback prevention is needed
        
        Returns:
            True if using speakers and feedback prevention should be enabled
        """
        device_type = self.get_current_device_type()
        
        if device_type == DeviceType.SPEAKERS:
            return True
        elif device_type == DeviceType.HEADPHONES:
            return False
        else:
            # Unknown device type - be conservative and enable feedback prevention
            return True
    
    def should_allow_interruption(self) -> bool:
        """
        Determine if microphone interruption should be allowed
        
        Returns:
            True if using headphones and interruption is safe
        """
        device_type = self.get_current_device_type()
        
        if device_type == DeviceType.HEADPHONES:
            return True
        elif device_type == DeviceType.SPEAKERS:
            return False
        else:
            # Unknown device type - be conservative and disable interruption
            return False
    
    def get_device_recommendations(self) -> Dict[str, Any]:
        """Get recommendations for optimal audio setup"""
        device_type = self.get_current_device_type()
        current_device = self.get_current_output_device()
        
        recommendations = {
            "current_device": current_device,
            "device_type": device_type.value,
            "feedback_prevention_needed": self.is_feedback_prevention_needed(),
            "interruption_allowed": self.should_allow_interruption(),
            "recommendations": [],
            "warnings": []
        }
        
        if device_type == DeviceType.SPEAKERS:
            recommendations["warnings"].append(
                "Using speakers - feedback prevention enabled, interruption disabled"
            )
            recommendations["recommendations"].append(
                "Consider using headphones for best experience with interruption support"
            )
        elif device_type == DeviceType.HEADPHONES:
            recommendations["recommendations"].append(
                "Using headphones - optimal setup with interruption support enabled"
            )
        else:
            recommendations["warnings"].append(
                "Could not determine device type - using conservative feedback prevention"
            )
            recommendations["recommendations"].append(
                "Try using clearly named headphones or speakers for better detection"
            )
        
        return recommendations
    
    def detect_headphones(self) -> List[Dict[str, Any]]:
        """Get list of detected headphone devices"""
        devices = self.get_available_devices()
        return [d for d in devices if d["device_type"] == DeviceType.HEADPHONES]
    
    def detect_speakers(self) -> List[Dict[str, Any]]:
        """Get list of detected speaker devices"""
        devices = self.get_available_devices()
        return [d for d in devices if d["device_type"] == DeviceType.SPEAKERS]
    
    def set_manual_override(self, device_type: Optional[str]):
        """
        Set manual device type override
        
        Args:
            device_type: "speakers", "headphones", or None to disable override
        """
        if device_type and device_type.lower() not in ["speakers", "headphones"]:
            raise ValueError("device_type must be 'speakers', 'headphones', or None")
        
        self.manual_override = device_type
        self._current_device_type = None  # Clear cache
    
    def __del__(self):
        """Clean up PyAudio instance"""
        try:
            if hasattr(self, 'audio'):
                self.audio.terminate()
        except Exception as e:
            # Suppress exceptions in destructor but log for debugging
            try:
                print(f"Warning: Error terminating audio in destructor: {e}")
            except:
                # Even logging failed, just pass silently
                pass