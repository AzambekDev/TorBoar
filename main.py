import sys
import queue
import argparse
from PyQt6.QtWidgets import QApplication
from engine.engine_runner import EngineRunner
from gui.main_window import MainWindow

def main():
    parser = argparse.ArgumentParser(description="Antigravity BitTorrent Client")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    # Thread-safe queue for UI -> Engine commands
    command_queue = queue.Queue()
    
    # Setup GUI
    main_window = MainWindow(command_queue)
    
    # The callback to route engine snapshots to the GUI main thread
    # In PyQt, signals emitted from background threads are thread-safe 
    # and properly queued for the main thread event loop.
    def on_snapshot(snapshot):
        main_window.snapshot_received.emit(snapshot)
        
    # Setup Background Engine
    engine = EngineRunner(command_queue, on_snapshot)
    engine.start()
    
    # Show GUI
    main_window.show()
    
    # Start Event Loop
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
