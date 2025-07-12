"""
Context persistence for crash recovery and session continuity
"""

import json
import os
import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import gzip


class ContextPersistence:
    """Handles saving and loading context to disk"""
    
    def __init__(self, 
                 storage_dir: str = "./context_storage",
                 max_files: int = 10,
                 compression: bool = True):
        """
        Initialize persistence layer
        
        Args:
            storage_dir: Directory to store context files
            max_files: Maximum number of context files to keep
            compression: Whether to compress saved files
        """
        self.storage_dir = Path(storage_dir)
        self.max_files = max_files
        self.compression = compression
        
        # Create storage directory
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Persistence state
        self.last_save_time = 0
        self.save_count = 0
        
    def save_meeting_session(self, context_manager) -> str:
        """
        Save complete meeting session to disk
        
        Args:
            context_manager: ContextManager instance
            
        Returns:
            Path to saved file
        """
        # Get complete meeting summary
        meeting_data = context_manager.get_meeting_summary()
        
        # Add metadata
        save_data = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "version": "1.0",
            "type": "meeting_session",
            "meeting": meeting_data,
            "manager_state": {
                "window_minutes": context_manager.window_minutes,
                "summary_model": context_manager.summary_model,
                "session_id": context_manager.session_id
            }
        }
        
        # Generate filename with session ID
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"meeting_{context_manager.session_id}_{timestamp_str}.json"
        if self.compression:
            filename += ".gz"
            
        filepath = self.storage_dir / filename
        
        # Save to disk
        try:
            if self.compression:
                # Save compressed
                with gzip.open(filepath, "wt", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
            else:
                # Save uncompressed
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
                    
            self.last_save_time = time.time()
            self.save_count += 1
            
            # Clean up old files
            self._cleanup_old_files()
            
            print(f"📝 Meeting session saved: {filepath}")
            print(f"   Session ID: {meeting_data['session_id']}")
            print(f"   Duration: {meeting_data['session_duration_minutes']:.1f} minutes")
            print(f"   Total entries: {meeting_data['total_entries']}")
            return str(filepath)
            
        except Exception as e:
            print(f"Error saving meeting session: {e}")
            raise

    def save_context(self, context_manager) -> str:
        """
        Save context to disk
        
        Args:
            context_manager: ContextManager instance
            
        Returns:
            Path to saved file
        """
        # Get current context
        context_data = context_manager.get_full_context()
        
        # Add metadata
        save_data = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "version": "1.0",
            "context": {
                "summary": context_data["summary"],
                "recent": context_data["recent"],
                "stats": context_data["stats"]
            },
            "manager_state": {
                "window_minutes": context_manager.window_minutes,
                "summary_model": context_manager.summary_model,
                "total_entries": context_manager.total_entries_count,
                "summaries_created": context_manager.summaries_created_count
            }
        }
        
        # Generate filename
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"context_{timestamp_str}.json"
        if self.compression:
            filename += ".gz"
            
        filepath = self.storage_dir / filename
        
        # Save to disk
        try:
            if self.compression:
                # Save compressed
                with gzip.open(filepath, "wt", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
            else:
                # Save uncompressed
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
                    
            self.last_save_time = time.time()
            self.save_count += 1
            
            # Clean up old files
            self._cleanup_old_files()
            
            print(f"Context saved to: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"Error saving context: {e}")
            raise
            
    def load_latest_context(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent context from disk
        
        Returns:
            Loaded context data or None if no files found
        """
        # Find all context files
        pattern = "context_*.json*"
        context_files = list(self.storage_dir.glob(pattern))
        
        if not context_files:
            print("No saved context files found")
            return None
            
        # Sort by modification time (newest first)
        context_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Try to load the most recent file
        for filepath in context_files:
            try:
                if filepath.suffix == ".gz":
                    # Load compressed
                    with gzip.open(filepath, "rt", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    # Load uncompressed
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                print(f"Loaded context from: {filepath}")
                print(f"  Saved at: {data['datetime']}")
                print(f"  Total entries: {data['manager_state']['total_entries']}")
                
                return data
                
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
                continue
                
        return None
        
    def restore_to_manager(self, context_manager, saved_data: Dict[str, Any]):
        """
        Restore saved context to a context manager
        
        Args:
            context_manager: ContextManager instance
            saved_data: Data loaded from disk
        """
        try:
            # Restore summary
            context_data = saved_data["context"]
            context_manager.conversation_summary = context_data["summary"]
            context_manager.summary_created_at = saved_data["timestamp"]
            
            # Restore recent entries
            for entry_data in context_data["recent"]:
                # Only restore entries that are still within the window
                age_minutes = (time.time() - entry_data["timestamp"]) / 60.0
                if age_minutes <= context_manager.window_minutes:
                    context_manager.add_transcription(
                        text=entry_data["text"],
                        timestamp=entry_data["timestamp"],
                        speaker=entry_data["speaker"]
                    )
                    
            # Restore stats
            manager_state = saved_data["manager_state"]
            context_manager.total_entries_count = manager_state["total_entries"]
            context_manager.summaries_created_count = manager_state.get("summaries_created", manager_state.get("summarizations_performed", 0))
            
            print(f"Context restored successfully")
            print(f"  Summary length: {len(context_manager.conversation_summary)} chars")
            print(f"  Recent entries: {len(context_manager.recent_entries)}")
            
        except Exception as e:
            print(f"Error restoring context: {e}")
            raise
            
    def _cleanup_old_files(self):
        """Remove old context files beyond max_files limit"""
        # Find all context files
        pattern = "context_*.json*"
        context_files = list(self.storage_dir.glob(pattern))
        
        if len(context_files) <= self.max_files:
            return
            
        # Sort by modification time (oldest first)
        context_files.sort(key=lambda p: p.stat().st_mtime)
        
        # Remove oldest files
        files_to_remove = len(context_files) - self.max_files
        for i in range(files_to_remove):
            try:
                context_files[i].unlink()
                print(f"Removed old context file: {context_files[i].name}")
            except Exception as e:
                print(f"Error removing {context_files[i]}: {e}")
                
    def get_storage_info(self) -> Dict[str, Any]:
        """Get information about stored context files"""
        pattern = "context_*.json*"
        context_files = list(self.storage_dir.glob(pattern))
        
        total_size = sum(f.stat().st_size for f in context_files)
        
        return {
            "storage_dir": str(self.storage_dir),
            "file_count": len(context_files),
            "total_size_mb": total_size / (1024 * 1024),
            "max_files": self.max_files,
            "compression_enabled": self.compression,
            "last_save_time": self.last_save_time,
            "save_count": self.save_count
        }


class MeetingSessionManager:
    """Manages meeting sessions - save only on session end"""
    
    def __init__(self, 
                 context_manager,
                 persistence: ContextPersistence):
        """
        Initialize meeting session manager
        
        Args:
            context_manager: ContextManager instance
            persistence: ContextPersistence instance
        """
        self.context_manager = context_manager
        self.persistence = persistence
        
        # Session state
        self.session_active = False
        
        print(f"🏁 Started meeting session: {self.context_manager.session_id}")
        
    def start(self):
        """Start the meeting session"""
        self.session_active = True
        
    def stop(self):
        """End the meeting session and save to disk"""
        if self.session_active:
            self.session_active = False
            # Save the complete meeting session
            try:
                self.persistence.save_meeting_session(self.context_manager)
            except Exception as e:
                print(f"Error saving meeting session: {e}")


class AutoSaveContextManager:
    """Wrapper that adds auto-save functionality to context manager - DEPRECATED for meeting sessions"""
    
    def __init__(self, 
                 context_manager,
                 persistence: ContextPersistence,
                 save_interval: int = 60):
        """
        Initialize auto-save wrapper
        
        Args:
            context_manager: ContextManager instance
            persistence: ContextPersistence instance
            save_interval: Seconds between auto-saves
        """
        self.context_manager = context_manager
        self.persistence = persistence
        self.save_interval = save_interval
        
        # Auto-save state
        self.auto_save_thread = None
        self.running = False
        
    def _restore_previous_session(self):
        """Attempt to restore context from previous session"""
        saved_data = self.persistence.load_latest_context()
        if saved_data:
            try:
                # Check age of saved data
                age_minutes = (time.time() - saved_data["timestamp"]) / 60.0
                
                if age_minutes < 60:  # Only restore if less than 1 hour old
                    self.persistence.restore_to_manager(
                        self.context_manager, 
                        saved_data
                    )
                    print(f"Restored context from {age_minutes:.1f} minutes ago")
                else:
                    print(f"Saved context too old ({age_minutes:.1f} minutes), starting fresh")
                    
            except Exception as e:
                print(f"Failed to restore context: {e}")
                
    def start(self):
        """Start auto-save thread"""
        if not self.running:
            self.running = True
            self.auto_save_thread = threading.Thread(
                target=self._auto_save_worker,
                daemon=True
            )
            self.auto_save_thread.start()
            print(f"Auto-save started (interval: {self.save_interval}s)")
            
    def stop(self):
        """Stop auto-save thread and save final state"""
        self.running = False
        if self.auto_save_thread:
            self.auto_save_thread.join(timeout=2.0)
            
        # Final save
        try:
            self.persistence.save_context(self.context_manager)
        except Exception as e:
            print(f"Error during final save: {e}")
            
    def _auto_save_worker(self):
        """Background worker for auto-saving"""
        last_save = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                if current_time - last_save >= self.save_interval:
                    # Check if there's content to save
                    context_data = self.context_manager.get_full_context()
                    
                    if context_data["recent"] or context_data["summary"]:
                        self.persistence.save_context(self.context_manager)
                        last_save = current_time
                        
                # Sleep briefly
                time.sleep(5.0)
                
            except Exception as e:
                print(f"Error in auto-save worker: {e}")
                time.sleep(10.0)