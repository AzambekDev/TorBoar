import threading
from collections import deque
from datetime import datetime

class EngineLogger:
    def __init__(self, max_len=200):
        self.logs = deque(maxlen=max_len)
        self.lock = threading.Lock()
        # Keep track of the index so the GUI can request only new logs
        self.current_index = 0

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        with self.lock:
            self.logs.append((self.current_index, formatted))
            self.current_index += 1

    def get_new_logs(self, last_index: int) -> list:
        """Returns logs that have an index > last_index, and the highest index found."""
        with self.lock:
            new_logs = []
            highest_idx = last_index
            for idx, msg in self.logs:
                if idx > last_index:
                    new_logs.append(msg)
                    highest_idx = idx
            return new_logs, highest_idx

# Global instance
global_logger = EngineLogger()

def log(message: str):
    global_logger.log(message)
