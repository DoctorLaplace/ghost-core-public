# agent/kernel/tracer.py
import os
import json
import uuid
import contextvars
from datetime import datetime

class ActiveTraceStorageCompat:
    """Compatibility wrapper that acts like active_trace_storage and holds trace_id globally."""
    def __init__(self):
        self._trace_id = None
        
    @property
    def trace_id(self):
        return self._trace_id
        
    @trace_id.setter
    def trace_id(self, value):
        self._trace_id = value

active_trace_storage = ActiveTraceStorageCompat()

class Tracer:
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.traces_dir = os.path.join(current_dir, "..", "..", "data", "traces")
        else:
            self.traces_dir = os.path.join(base_dir, "data", "traces")
        
    def start_trace(self, task_id: str) -> str:
        """Starts a trace, registers it in thread-local storage, and returns a unique trace_id."""
        try:
            os.makedirs(self.traces_dir, exist_ok=True)
        except Exception:
            pass
        
        unique_suffix = uuid.uuid4().hex[:8]
        trace_id = f"{task_id}_{unique_suffix}"
        
        active_trace_storage.trace_id = trace_id
        
        # Log the start event
        self.log_event(trace_id, "trace_started", {"task_id": task_id})
        return trace_id

    def log_event(self, trace_id: str, event_type: str, payload: dict) -> None:
        """Appends a single JSON event line to data/traces/{trace_id}.jsonl."""
        if not trace_id:
            # Fallback to active thread-local trace if not explicitly passed
            trace_id = getattr(active_trace_storage, "trace_id", None)
            if not trace_id:
                return  # Cannot log without a trace ID
                
        event = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "payload": payload
        }
        trace_file = os.path.join(self.traces_dir, f"{trace_id}.jsonl")
        try:
            os.makedirs(self.traces_dir, exist_ok=True)
            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

    def end_trace(self, trace_id: str, outcome: str) -> None:
        """Logs the final trace event and finishes the trace."""
        self.log_event(trace_id, "trace_ended", {"outcome": outcome})
        if getattr(active_trace_storage, "trace_id", None) == trace_id:
            active_trace_storage.trace_id = None
